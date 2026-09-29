"""Daily missed-sweep background scheduler for the API service.

The API service has no Home Assistant, so nobody re-fires the
integration's day-rollover listener for it: this module owns the API
plane's own background job.  One :class:`MissedSweepScheduler` per app
(installed on ``app.state`` by the lifespan) sleeps until the
configured ``day_rollover_time`` — read fresh from the settings store
at the top of EVERY cycle, so an admin's settings change applies on
the next scheduling decision without a restart — then runs the
HA-free core's :func:`nestquest_core.sweep.run_missed_sweep` for the
household-local date (the stored ``timezone`` setting; the API host's
local date when unset) and publishes each returned
``nestquest_quest_missed`` event on the app's ONE transition publisher
(the same SSE stream every route publishes through).

A household zone adopted from Home Assistant while the loop is asleep
must not leave it waiting for the OLD zone's rollover (a UTC host would
otherwise sweep at UTC midnight — 20:00 in New York — marking quests
missed hours early).  :meth:`MissedSweepScheduler.settings_changed`
wakes the sleeping loop to re-plan whenever the zone or rollover time
it planned with has moved, and the loop re-reads the settings before
sweeping and re-plans instead if they no longer match its plan.

Guarantee: no sweep runs for a plan a committed adoption has replaced.
An adopting writer holds :attr:`MissedSweepScheduler.settings_lock`
across its write AND its :meth:`~MissedSweepScheduler.settings_changed`
call; the loop holds the same lock across its plan read (read, record
the plan, clear the wake flag) and across the pre-sweep re-read plus
the sweep itself.  So an adoption commits either before a plan read
(which then sees it), after one (``settings_changed`` compares against
that exact plan and wakes the wait), or after the sweep — never between
a read and what the loop does with it.  The lock is never held across
the wait, and the loop takes nothing else before it, so a waiting
panel request cannot deadlock: it is delayed at most by one settings
read or one sweep.

All sweep policy lives in the core (the watermark, the
``[watermark, today)`` window, the no-completion-event rule): this
scheduler only decides WHEN.  A same-night rerun — e.g. two workers,
or a settings change moving the rollover past itself — fires nothing:
the core's watermark makes the run an empty no-op.

Testability: ``clock`` (an aware-now callable) and ``sleep`` (an
awaitable delay) are injectable, so tests pin the time, fast-forward
through the wait, and observe the computed delays without waiting a
real day.  Cancellation: :meth:`stop` cancels the loop task and waits
for it, so the lifespan's shutdown is clean and a mid-run sweep is
interrupted before the connection closes.  A failed iteration (a
database hiccup, a rejected setting) is logged and retried after a
fixed backoff rather than silently killing the job.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

from api.nestquest_core import core_settings_store, core_sweep

LOGGER = logging.getLogger(__name__)

#: Backoff after a failed scheduling cycle (settings read or sweep
#: error), so a persistent failure retries every minute instead of
#: spinning or dying.
_RETRY_BACKOFF_SECONDS = 60.0


#: Upper bound on the minute-by-minute search past a nonexistent wall
#: time; real DST gaps are an hour, the largest ever skipped a day.
_MAX_GAP_MINUTES = 2 * 24 * 60


def _resolve_wall_time(
    day: datetime.date, target: datetime.time, zone: datetime.tzinfo
) -> datetime.datetime:
    """The aware instant ``target`` (``HH:MM``) names on ``day`` in ``zone``.

    A nonexistent wall time (inside a spring-forward gap) resolves to
    the first valid wall minute at/after it — the gap's end, e.g. 02:30
    on a 02:00→03:00 day becomes 03:00.  An ambiguous wall time (the
    repeated fall-back hour) resolves to its FIRST occurrence
    (``fold=0``).
    """
    wall = datetime.datetime.combine(
        day, datetime.time(target.hour, target.minute)
    )
    for _ in range(_MAX_GAP_MINUTES):
        candidate = wall.replace(tzinfo=zone)
        round_trip = candidate.astimezone(datetime.timezone.utc).astimezone(
            zone
        )
        if round_trip.replace(tzinfo=None) == wall:
            return candidate
        wall += datetime.timedelta(minutes=1)
    raise ValueError(f"no valid wall time at/after {target} on {day}")


def _delay_seconds(target: datetime.time, now: datetime.datetime) -> float:
    """Real seconds from ``now`` until the next occurrence of ``target``.

    ``target`` is a plain ``HH:MM`` household time of day, resolved in
    ``now``'s zone by :func:`_resolve_wall_time` (nonexistent → first
    valid instant after the gap; ambiguous → first occurrence).  The
    result is the next such instant strictly AFTER ``now`` (an equal
    time schedules for tomorrow, so the just-run sweep is never
    instantly re-run).  Both instants are compared and subtracted in
    UTC: same-``tzinfo`` aware arithmetic is wall-clock arithmetic and
    would be an hour off across a DST transition.
    """
    now_utc = now.astimezone(datetime.timezone.utc)
    day = now.date()
    while True:
        scheduled = _resolve_wall_time(day, target, now.tzinfo)
        scheduled_utc = scheduled.astimezone(datetime.timezone.utc)
        if scheduled_utc > now_utc:
            return (scheduled_utc - now_utc).total_seconds()
        day += datetime.timedelta(days=1)


class MissedSweepScheduler:
    """Run the missed sweep once per day at ``day_rollover_time``."""

    def __init__(
        self,
        database: object,
        *,
        publisher: object | None = None,
        clock: object | None = None,
        sleep: object | None = None,
    ) -> None:
        """Create the scheduler (not yet running).

        ``database`` is the app's live :class:`~api.database.NestQuestDatabase`.
        ``publisher`` is the app's ONE
        :class:`~api.events.TransitionPublisher` (publishing is skipped
        when ``None``).  ``clock`` defaults to the API host's local
        aware now (``datetime.datetime.now().astimezone()``) — the same
        single-clock discipline the routes' ``_local_now`` uses;
        ``sleep`` defaults to :func:`asyncio.sleep`.
        """
        self._database = database
        self._publisher = publisher
        self._clock = clock if clock is not None else (
            lambda: datetime.datetime.now().astimezone()
        )
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._task: asyncio.Task | None = None
        #: ``(timezone, day_rollover_time)`` the pending sweep was
        #: planned with; ``None`` until the first plan.
        self._planned: tuple[str, str] | None = None
        #: Set by :meth:`settings_changed` to cut the current wait short.
        self._wake = asyncio.Event()
        #: Serialises settings adoption with planning and sweeping (see
        #: the module docstring's guarantee).
        self.settings_lock = asyncio.Lock()

    def start(self) -> None:
        """Start the background loop (idempotent: a running one stays)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(
                self._run_forever(), name="nestquest-missed-sweep"
            )

    async def stop(self) -> None:
        """Cancel the loop and wait for it to finish (safe if never started)."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def settings_changed(self, settings: object) -> None:
        """Re-plan the pending sweep if ``settings`` moved its rollover.

        Called with freshly stored settings (e.g. a zone adopted from
        Home Assistant), with :attr:`settings_lock` held across the write
        and this call so the comparison is against the loop's current
        plan, never a read still in flight.  A differing ``timezone`` or
        ``day_rollover_time`` wakes the sleeping loop, which reloads the
        settings and schedules the next sweep for the new household
        rollover; an unchanged plan is left sleeping.
        """
        if (settings.timezone, settings.day_rollover_time) != self._planned:
            self._wake.set()

    @property
    def running(self) -> bool:
        """Whether the background loop task is alive."""
        return self._task is not None and not self._task.done()

    async def _run_forever(self) -> None:
        """Schedule → sweep → repeat, forever (until cancelled)."""
        while True:
            try:
                # Under the lock no adoption can commit between this read
                # and the recorded plan, so any later one wakes the wait.
                async with self.settings_lock:
                    self._wake.clear()
                    settings = await core_settings_store.load_settings(
                        self._database
                    )
                    rollover = datetime.time.fromisoformat(
                        settings.day_rollover_time
                    )
                    plan = (settings.timezone, settings.day_rollover_time)
                    self._planned = plan
            except Exception:
                # Not silent: the failure is logged and retried after
                # the backoff, so one bad settings document or a
                # transient database error never kills the scheduler.
                LOGGER.exception(
                    "NestQuest missed-sweep scheduler failed to resolve "
                    "the day rollover time; retrying in %gs",
                    _RETRY_BACKOFF_SECONDS,
                )
                await self._sleep(_RETRY_BACKOFF_SECONDS)
                continue
            # The host may run UTC: the rollover is a household wall-clock
            # time, so the clock read is re-expressed in the stored zone.
            delay = _delay_seconds(
                rollover, settings.household_now(self._clock())
            )
            LOGGER.info(
                "NestQuest missed sweep scheduled for %s (%.0fs from now)",
                settings.day_rollover_time,
                delay,
            )
            try:
                if not await self._sleep_unless_woken(delay):
                    continue
                # Re-read before sweeping: a zone or rollover change the
                # wake-up missed means this is not the household's
                # rollover any more, so re-plan instead of sweeping.  The
                # lock keeps an adoption from committing between this
                # check and the sweep.
                async with self.settings_lock:
                    settings = await core_settings_store.load_settings(
                        self._database
                    )
                    if (
                        settings.timezone,
                        settings.day_rollover_time,
                    ) != plan:
                        continue
                    await self._run_once(
                        settings.household_now(self._clock()).date()
                    )
            except Exception:
                # Not silent either: a failed wait or sweep is logged and
                # the loop backs off before the next cycle, whose
                # watermark re-read makes an already-swept day a no-op.
                LOGGER.exception(
                    "NestQuest scheduled missed sweep failed; retrying in "
                    "%gs",
                    _RETRY_BACKOFF_SECONDS,
                )
                await self._sleep(_RETRY_BACKOFF_SECONDS)

    async def _sleep_unless_woken(self, delay: float) -> bool:
        """Wait ``delay``; ``False`` if :meth:`settings_changed` woke it.

        Both children are cancelled AND awaited before returning (or
        before a cancellation propagates), so none outlives :meth:`stop`;
        a sleep that failed re-raises its exception here for the loop's
        retry policy.
        """
        sleeper = asyncio.ensure_future(self._sleep(delay))
        waker = asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait(
                {sleeper, waker}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            slept = sleeper.done()
            sleeper.cancel()
            waker.cancel()
            await asyncio.gather(sleeper, waker, return_exceptions=True)
        if slept:
            sleeper.result()
        return slept

    async def _run_once(self, today: datetime.date) -> None:
        """Run ONE sweep for ``today`` and publish what it built.

        A failure propagates to :meth:`_run_forever`, which logs it and
        backs off before the next cycle; the watermark makes a re-run
        of an already-swept day announce nothing twice.
        """
        events = await core_sweep.run_missed_sweep(
            self._database, today=today
        )
        for event_type, payload in events:
            if self._publisher is not None:
                self._publisher.publish(event_type, payload)
        LOGGER.info(
            "NestQuest scheduled missed sweep for %s published %d event(s)",
            today.isoformat(),
            len(events),
        )


__all__ = ["MissedSweepScheduler"]
