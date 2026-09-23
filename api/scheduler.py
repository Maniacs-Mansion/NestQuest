"""Daily missed-sweep background scheduler for the API service.

The API service has no Home Assistant, so nobody re-fires the
integration's day-rollover listener for it: this module owns the API
plane's own background job.  One :class:`MissedSweepScheduler` per app
(installed on ``app.state`` by the lifespan) sleeps until the
configured ``day_rollover_time`` — read fresh from the settings store
at the top of EVERY cycle, so an admin's settings change applies on
the next scheduling decision without a restart — then runs the
HA-free core's :func:`nestquest_core.sweep.run_missed_sweep` for the
API host's local date and publishes each returned
``nestquest_quest_missed`` event on the app's ONE transition publisher
(the same SSE stream every route publishes through).

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


def _delay_seconds(target: datetime.time, now: datetime.datetime) -> float:
    """Seconds from ``now`` until the next occurrence of ``target``.

    ``target`` is a plain ``HH:MM`` time of day: the next wall-clock
    occurrence strictly AFTER ``now`` (an equal time schedules for
    tomorrow, so the just-run sweep is never instantly re-run).
    """
    scheduled = now.replace(
        hour=target.hour, minute=target.minute, second=0, microsecond=0
    )
    if scheduled <= now:
        scheduled += datetime.timedelta(days=1)
    return (scheduled - now).total_seconds()


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

    @property
    def running(self) -> bool:
        """Whether the background loop task is alive."""
        return self._task is not None and not self._task.done()

    async def _run_forever(self) -> None:
        """Schedule → sweep → repeat, forever (until cancelled)."""
        while True:
            try:
                settings = await core_settings_store.load_settings(
                    self._database
                )
                rollover = datetime.time.fromisoformat(
                    settings.day_rollover_time
                )
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
            delay = _delay_seconds(rollover, self._clock())
            LOGGER.info(
                "NestQuest missed sweep scheduled for %s (%.0fs from now)",
                settings.day_rollover_time,
                delay,
            )
            await self._sleep(delay)
            try:
                await self._run_once(self._clock().date())
            except Exception:
                # Not silent either: the sweep error is logged and the
                # loop backs off before the next cycle, whose watermark
                # re-read makes an already-swept day a no-op.
                LOGGER.exception(
                    "NestQuest scheduled missed sweep failed; retrying in "
                    "%gs",
                    _RETRY_BACKOFF_SECONDS,
                )
                await self._sleep(_RETRY_BACKOFF_SECONDS)

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