# Panel empty & error states — design addendum

Closes the gap DESIGN-HANDOFF.md lists under "Open questions": *"Empty and error
states are unspecified by request (child with no quests, everyone away, integration
unconfigured, DB unreachable). Panel must not render a blank parchment — decide
before shipping the card."*

All decisions below reuse PANEL-SPEC.md's approved aesthetic — parchment ground,
double frame, dock, panel tokens, no text below 22px, no alpha-muted ink — and add
one shared component per card: a **notice panel** (radius 20px, `--nq-p-card-panel`,
2px `--nq-p-panel-border`, `--nq-p-panel-shadow`, centred icon + headline + body).
The frame, wordmark row, kicker and dock always render; only the content area
changes. **No state renders a blank parchment.**

## 1. What the data can say

The cards read `sensor.nestquest_<child>_quests_due_today` (plus siblings). One of
four things comes back, and the card must tell them apart:

| Backend condition | What the card sees | Card's interpretation |
|---|---|---|
| Resolving (DB fine) | numeric state + attributes (`child_name`, `present`, `instances`) | normal, all states below |
| Integration not configured | entity does not exist at all | **not set up** |
| Backend unreachable (DB locked, refresh failed) | state `unavailable` | **records unreachable** |
| Child deactivated / absent from snapshot | state `unknown` | **records unreachable** (same panel voice: the records do not answer) |

An away child (presence `present: false`, from the due-sensor attributes with the
presence binary sensor as fallback) is *not* an error: it is a first-class panel
state ("On travels"). Away children get no instances (materialiser skips them), so
away is detected from the presence flag, never from a zero quest count.

## 2. Quest log — state priority

`nestquest-quest-log-card` resolves exactly one state, in this order:

1. **No adventurer in the path** (direct navigation to a URL with no child slug —
   misconfigured `board_path`/`quest_log_path`) → notice *"No adventurer chosen"*,
   body *"Open The Party and tap your crest to open your quest log."*
2. **Not set up** (entity missing) → notice *"NestQuest is not set up yet"*, body
   *"A parent needs to finish setting up NestQuest."*
3. **Records unreachable** (`unavailable`/`unknown`) → notice *"The records cannot
   be reached"*, body *"The party's records are quiet right now. NestQuest will
   return shortly."*
4. **Away** (present flag false) → away notice: dashed muted panel (the away-plate
   gradient), tent icon, *"<Name> is on travels"*, *"The quest log unlocks when
   they return."* and, when `next_present` is known, *"Returns <weekday>, <Mon D>"*.
   Direct navigation is the one path that can reach this state (the board's away
   plate is not tappable); the log answers it honestly instead of showing an empty
   column set. Header renders with the crest in away colours and the sub line
   `… · On travels`; the remaining-count block is hidden (it is meaningless while
   away).
5. **No quests today** (present, due = 0) → all-clear notice, sun icon, *"No quests
   today"*, body *"Nothing was posted for today, <Name>. Enjoy the day's rest!"* —
   never three bare empty columns. The header and remaining block stay (0 quests
   left, party progress), so the log still reads like the log.
6. **All quests done** (due > 0, remaining = 0) → the fallback celebration that
   shows until the 1c quest-complete screen takes over: centred wax-seal mark (the
   `--nq-p-seal` tokens at 78px, check glyph, −6°) with headline *"Quest complete"*
   — the same phrase screen 1c uses — and body *"Every quest is claimed, <Name>.
   The seal is set for today. Returning to The Party shortly."* The idle return
   (§3.5) is what actually navigates back; 1c remains the designed takeover.
7. **Normal** → the three-window column layout of PANEL-SPEC §3.1 unchanged. A
   window with no quests still renders its head alone, exactly as the spec says.

Notices sit in the columns' content area, vertically centred. Error notices (states
1–3) replace the header entirely — there is no honest name to headline when the
records do not answer — while states 4–6 keep the full header.

## 3. Party board — state priority

`nestquest-party-board-card` resolves per configured child, then at board level:

1. **No children configured** (`child_order` empty) → board notice *"NestQuest is
   not set up yet"*, body *"A parent needs to finish setting up NestQuest before
   the party can gather."*
2. **Every configured child unresolvable** → one board notice instead of a grid of
   broken plates: *"NestQuest is not set up yet"* when the entities are missing,
   *"The records cannot be reached"* when they answer `unavailable`/`unknown`.
3. **Partial** (some children resolve, some do not) → the board still renders the
   resolving plates; an unresolvable child renders a muted, dashed plate in the
   away geometry with a compass icon and the pill label **"Unknown"**, progress
   line `—`, empty bar, **not tappable**. It must not claim "Home today" (0 of 0)
   and must not lie "On travels": the records simply do not say.
4. **Normal** → the plates grid of PANEL-SPEC §2 unchanged (present + away plates).

The hint line ("Tap your crest…") is hidden in board-level notice states — there
is nothing to tap.

## 4. Shared rules

- **Never a blank parchment.** Every render path emits the frames, wordmark,
  kicker, dock, and either content or a notice panel. The dock already degrades to
  date + time when weather is unset (PANEL-SPEC §2.3); that behaviour is unchanged.
- **Notice panel type scale:** icon 46px, headline 40px/700 Cinzel
  (`--nq-p-font-heading`, `--nq-p-ink`), body 24px/600 Nunito
  (`--nq-p-ink-secondary`), `role="status"` so assistive tech announces it.
- **Tone.** The panel speaks tabletop (PANEL-SPEC vocabulary) but never lies: an
  error says the records cannot be reached, not that everything is fine. Error
  copy names the actor who can fix it (a parent) or promises the return of the
  data — no stack traces, no entity IDs.
- **No interaction in error/away states.** No confirm dialog, no idle return
  changes, no navigation attempts. Notices are static.
- Both cards implement the same resolution rules, so the board and the log never
  disagree about whether the integration is up.
