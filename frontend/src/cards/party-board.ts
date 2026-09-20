import { LitElement, css, html, nothing, unsafeCSS, type TemplateResult } from "lit";
import panelTokens from "../../../custom_components/nestquest/www/nestquest-panel-tokens.css?inline";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

type StateObject = {
  state: unknown;
  attributes?: Record<string, unknown> | null;
};

type ChildPlate = {
  slug: string;
  name: string;
  initial: string;
  present: boolean;
  completed: number;
  due: number;
  pct: number;
  returns: string | null;
  /** Set when the child's sensors cannot resolve; the plate shows "Unknown". */
  unresolved: "missing" | "stale" | null;
};

type BoardNotice = {
  icon: TemplateResult;
  headline: string;
  body: string;
};

type DockWeather = {
  condition: string;
  temperature: number | null;
  high: number | null;
  low: number | null;
};

const FORMATTER_CACHE = new Map<string, Intl.DateTimeFormat>();

function zonedFormatter(
  timeZone: string | undefined,
  options: Intl.DateTimeFormatOptions
): Intl.DateTimeFormat {
  const key = `${timeZone ?? "local"}|${JSON.stringify(options)}`;
  const cached = FORMATTER_CACHE.get(key);
  if (cached) {
    return cached;
  }
  let formatter: Intl.DateTimeFormat;
  try {
    formatter = new Intl.DateTimeFormat("en-US", {
      ...options,
      ...(timeZone ? { timeZone } : {}),
    });
  } catch {
    formatter = new Intl.DateTimeFormat("en-US", options);
  }
  FORMATTER_CACHE.set(key, formatter);
  return formatter;
}

function hassTimeZone(hass: HassLike | undefined): string | undefined {
  const config = hass?.config;
  if (!config || typeof config !== "object") {
    return undefined;
  }
  const timeZone = (config as Record<string, unknown>).time_zone;
  return typeof timeZone === "string" && timeZone.trim()
    ? timeZone.trim()
    : undefined;
}

function formatDay(date: Date, timeZone: string | undefined): string {
  return `${zonedFormatter(timeZone, { weekday: "long" }).format(date)}, ${zonedFormatter(timeZone, { month: "short", day: "numeric" }).format(date)}`;
}

function formatTime(date: Date, timeZone: string | undefined): string {
  return zonedFormatter(timeZone, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

const CONDITION_LABELS: Record<string, string> = {
  "clear-night": "Clear",
  cloudy: "Cloudy",
  exceptional: "Clear",
  fog: "Foggy",
  hail: "Hail",
  lightning: "Storms",
  "lightning-rimmed": "Storms",
  partlycloudy: "Partly cloudy",
  pouring: "Heavy rain",
  rainy: "Rain",
  snowy: "Snow",
  "snowy-rainy": "Sleet",
  sunny: "Sunny",
  windy: "Windy",
  "windy-variant": "Windy",
};

const CONDITION_PHRASES: Record<string, string> = {
  "clear-night": "Clear night skies",
  cloudy: "Grey skies today",
  exceptional: "A striking day",
  fog: "Mist on the road",
  hail: "Ice from the sky",
  lightning: "Storms may roll in",
  "lightning-rimmed": "Storms may roll in",
  partlycloudy: "Sun between clouds",
  pouring: "Heavy rain outside",
  rainy: "Rain on the walls",
  snowy: "Snow on the peaks",
  "snowy-rainy": "Sleet may fall",
  sunny: "Clear skies today",
  windy: "A blustery day",
  "windy-variant": "A blustery day",
};

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asNumber(value: unknown, fallback: number): number {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value));
}

function clampCount(value: number): number {
  return Math.max(0, Math.round(value));
}

function titleCaseSlug(slug: string): string {
  return slug
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function zoneOffsetMs(instant: number, timeZone: string): number {
  const parts = zonedFormatter(timeZone, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(instant));
  const read = (type: Intl.DateTimeFormatPartTypes): number => {
    const part = parts.find((entry) => entry.type === type);
    return part ? Number(part.value) : Number.NaN;
  };
  const asUtc = Date.UTC(
    read("year"),
    read("month") - 1,
    read("day"),
    read("hour"),
    read("minute"),
    read("second")
  );
  return Number.isFinite(asUtc) ? asUtc - instant : 0;
}

function parseIsoDate(value: unknown, timeZone?: string): Date | null {
  if (typeof value !== "string") {
    return null;
  }
  const parts = value.split("-");
  if (parts.length !== 3) {
    return null;
  }
  const [year, month, day] = parts.map((part) => Number(part));
  if (!year || !month || !day) {
    return null;
  }
  if (!timeZone) {
    const local = new Date(year, month - 1, day);
    return Number.isNaN(local.getTime()) ? null : local;
  }
  const utcMs = Date.UTC(year, month - 1, day);
  const date = new Date(utcMs - zoneOffsetMs(utcMs, timeZone));
  return Number.isNaN(date.getTime()) ? null : date;
}

function conditionLabel(condition: string): string {
  const known = CONDITION_LABELS[condition];
  if (known) {
    return known;
  }
  return condition.charAt(0).toUpperCase() + condition.slice(1);
}

function conditionPhrase(condition: string, label: string): string {
  return CONDITION_PHRASES[condition] ?? label;
}

const SHIELD_CLIP = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)";
const HEXAGON_CLIP =
  "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)";

const boardStyles = css`
  * {
    box-sizing: border-box;
  }

  :host {
    display: block;
    height: 100%;
    --nq-brand-gradient-h: linear-gradient(
      90deg,
      var(--nq-brand-blue),
      var(--nq-brand-purple)
    );
  }

  .board {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 1080px;
    padding: 0;
    overflow: hidden;
    background: var(--nq-p-parchment);
    box-shadow: var(--nq-p-vignette);
    font-family: var(--nq-p-font-body);
  }

  .frame {
    position: absolute;
    pointer-events: none;
  }

  .frame-outer {
    inset: 26px;
    border: var(--nq-p-frame-outer);
    border-radius: 14px;
  }

  .frame-inner {
    inset: 36px;
    border: var(--nq-p-frame-inner);
    border-radius: 8px;
  }

  .wordmark-row {
    position: absolute;
    top: 64px;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 26px;
    width: 100%;
  }

  .rule {
    flex: 1 1 0;
    max-width: 340px;
    height: 2px;
    border-radius: 1px;
    background: rgba(92, 62, 26, 0.35);
  }

  .d20 {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    clip-path: ${unsafeCSS(HEXAGON_CLIP)};
    background: var(--nq-brand-gradient);
  }

  .d20-numeral {
    font-family: var(--nq-p-font-heading);
    font-size: 15px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .wordmark {
    font-family: var(--nq-p-font-display);
    font-size: var(--nq-p-size-wordmark);
    font-weight: 900;
    line-height: 1.15;
    background: var(--nq-brand-gradient);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    -webkit-text-fill-color: transparent;
  }

  .kicker {
    position: absolute;
    top: 154px;
    left: 0;
    right: 0;
    font-family: var(--nq-p-font-heading);
    font-size: 22px;
    font-weight: 600;
    letter-spacing: var(--nq-p-track-kicker);
    text-transform: uppercase;
    line-height: 1.2;
    text-align: center;
    color: var(--nq-p-ink-secondary);
  }

  .plates {
    position: absolute;
    top: 262px;
    left: 110px;
    right: 110px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 56px;
  }

  .plate {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 26px;
    height: 600px;
    padding: 44px 28px 40px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: var(--nq-p-radius-panel);
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    font: inherit;
  }

  button.plate {
    width: 100%;
    color: inherit;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  button.plate:active {
    transform: scale(0.98);
  }

  button.plate:focus-visible {
    outline: 3px solid var(--nq-brand-purple);
    outline-offset: 4px;
  }

  .plate.away {
    border: 2px dashed var(--nq-p-panel-border);
    background: linear-gradient(#f2ecdd, #e6dcc6);
    box-shadow: none;
  }

  .crest {
    position: relative;
    flex: none;
    width: 188px;
    height: 214px;
    padding: 4px;
    clip-path: ${unsafeCSS(SHIELD_CLIP)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 70px;
    clip-path: ${unsafeCSS(SHIELD_CLIP)};
    background: var(--nq-p-crest);
  }

  .crest.away .crest-face {
    background: var(--nq-p-crest-away);
  }

  .crest .initial {
    font-family: var(--nq-p-font-display);
    font-size: 82px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .name {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-name);
    font-weight: 700;
    letter-spacing: 0.02em;
    line-height: 1.1;
    color: var(--nq-p-ink);
  }

  .plate.away .name {
    color: var(--nq-p-ink-away);
  }

  .pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 8px 20px;
    border-radius: var(--nq-p-radius-pill);
    background: rgba(22, 120, 60, 0.35);
    font-family: var(--nq-p-font-heading);
    font-size: 22px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    line-height: 1;
    color: #146b36;
  }

  .pill svg {
    width: 22px;
    height: 22px;
    color: #157a3c;
  }

  .pill.away {
    background: rgba(92, 62, 26, 0.16);
    color: var(--nq-p-ink-away);
  }

  .pill.away svg {
    color: var(--nq-p-ink-away);
  }

  .progress-line {
    font-family: var(--nq-p-font-heading);
    font-size: 24px;
    font-weight: 700;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .bar {
    width: 100%;
    height: 16px;
    border: 1px solid rgba(92, 62, 26, 0.35);
    border-radius: var(--nq-p-radius-pill);
    background: rgba(92, 62, 26, 0.18);
    overflow: hidden;
  }

  .bar .fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--nq-brand-gradient-h);
  }

  .hint {
    position: absolute;
    top: 930px;
    left: 0;
    right: 0;
    font-family: var(--nq-p-font-body);
    font-size: 24px;
    font-weight: 600;
    line-height: 1.4;
    text-align: center;
    color: var(--nq-p-ink-secondary);
  }

  .plate.unknown {
    border: 2px dashed var(--nq-p-panel-border);
    background: linear-gradient(#f2ecdd, #e6dcc6);
    box-shadow: none;
  }

  .notice-wrap {
    position: absolute;
    top: 262px;
    left: 110px;
    right: 110px;
    bottom: 190px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .notice {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    width: 100%;
    max-width: 980px;
    padding: 56px 64px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: var(--nq-p-radius-panel);
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    text-align: center;
  }

  .notice svg {
    width: 46px;
    height: 46px;
    color: var(--nq-p-ink-secondary);
  }

  .notice-headline {
    font-family: var(--nq-p-font-heading);
    font-size: 40px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--nq-p-ink);
  }

  .notice-body {
    margin: 0;
    font-family: var(--nq-p-font-body);
    font-size: 24px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--nq-p-ink-secondary);
  }

  .spacer {
    flex: 1 1 0;
  }

  .dock {
    position: absolute;
    left: 46px;
    right: 46px;
    bottom: 46px;
    height: var(--nq-p-dock-height);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    padding: 0 40px;
    border-radius: 14px;
    background: var(--nq-p-dock-bg);
    pointer-events: none;
    user-select: none;
    color: var(--nq-p-dock-ink);
  }

  .dock svg {
    flex: none;
    width: 40px;
    height: 40px;
    color: var(--nq-p-dock-ink);
  }

  .dock .divider {
    flex: none;
    width: 1px;
    height: 40px;
    background: var(--nq-p-dock-divider);
  }

  .dock .temp {
    font-family: var(--nq-p-font-body);
    font-size: 38px;
    font-weight: 800;
    line-height: 1;
  }

  .dock .condition {
    font-family: var(--nq-p-font-body);
    font-size: 26px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-dock-ink-secondary);
  }

  .dock .date {
    font-family: var(--nq-p-font-body);
    font-size: 26px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-dock-ink-secondary);
  }

  .dock .clock {
    font-family: var(--nq-p-font-body);
    font-size: 38px;
    font-weight: 800;
    line-height: 1;
  }
`;

const ICON_CHECK_CIRCLE = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <circle cx="12" cy="12" r="10"></circle>
  <path d="m9 12 2 2 4-4"></path>
</svg>`;

const ICON_TENT = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M3.5 21 12 3.5 20.5 21"></path>
  <path d="M9 21l3-8 3 8"></path>
</svg>`;

const ICON_COMPASS = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <circle cx="12" cy="12" r="10"></circle>
  <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
</svg>`;

const ICON_ALERT = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path>
  <path d="M12 9v4"></path>
  <path d="M12 17h.01"></path>
</svg>`;

const ICON_CLOUD_OFF = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"></path>
  <path d="m2 2 20 20"></path>
</svg>`;

const BOARD_NOTICE_NOT_SET_UP: BoardNotice = {
  icon: ICON_ALERT,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest before the party can gather.",
};

const BOARD_NOTICE_UNREACHABLE: BoardNotice = {
  icon: ICON_CLOUD_OFF,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly.",
};

const ICON_CLOUD_SUN = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 2v2"></path>
  <path d="m4.93 4.93 1.41 1.41"></path>
  <path d="M20 12h2"></path>
  <path d="m19.07 4.93-1.41 1.41"></path>
  <path d="M15.947 12.65a4 4 0 0 0-5.925-4.128"></path>
  <path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"></path>
</svg>`;

export class NestQuestPartyBoardCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _now: { state: true },
  };

  static styles = [unsafeCSS(panelTokens), boardStyles];

  hass?: HassLike;
  _config?: CardConfig;
  _now = new Date();
  private _clockTimer?: number;

  setConfig(config: CardConfig): void {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid configuration");
    }
    this._config = config;
  }

  getCardSize(): number {
    return 22;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._now = new Date();
    this._clockTimer = window.setInterval(() => {
      this._now = new Date();
    }, 1000);
  }

  disconnectedCallback(): void {
    if (this._clockTimer !== undefined) {
      window.clearInterval(this._clockTimer);
      this._clockTimer = undefined;
    }
    super.disconnectedCallback();
  }

  render() {
    const notice = this._boardNotice();
    return html`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        <div class="wordmark-row">
          <span class="rule"></span>
          <span class="d20" aria-hidden="true">
            <span class="d20-numeral">20</span>
          </span>
          <span class="wordmark">NestQuest</span>
          <span class="d20" aria-hidden="true">
            <span class="d20-numeral">20</span>
          </span>
          <span class="rule"></span>
        </div>
        <p class="kicker">The Party · ${formatDay(this._now, this._timeZone())}</p>
        ${notice
          ? this._renderNotice(notice)
          : html`
              <div class="plates">
                ${this._plates().map((plate) => this._renderPlate(plate))}
              </div>
              <p class="hint">Tap your crest to open your Quest Log</p>
            `}
        <div class="spacer"></div>
        ${this._renderDock()}
      </div>
    `;
  }

  private _timeZone(): string | undefined {
    return hassTimeZone(this.hass);
  }

  private _state(entityId: string): StateObject | null {
    const states = this.hass?.states as
      | Record<string, StateObject>
      | undefined;
    const stateObj = states?.[entityId];
    return stateObj && typeof stateObj === "object" ? stateObj : null;
  }

  private _childSlugs(): string[] {
    if (!this._config) {
      return [];
    }
    const order = this._config.child_order;
    if (!Array.isArray(order)) {
      return [];
    }
    return order
      .filter(
        (entry): entry is string =>
          typeof entry === "string" && entry.trim().length > 0
      )
      .map((entry) => entry.trim());
  }

  private _plates(): ChildPlate[] {
    return this._childSlugs().map((slug) => this._plate(slug));
  }

  private _plate(slug: string): ChildPlate {
    const unresolved = this._dueSensorResolution(slug);
    const dueSensor = this._state(`sensor.nestquest_${slug}_quests_due_today`);
    const doneSensor = this._state(
      `sensor.nestquest_${slug}_quests_completed_today`
    );
    const pctSensor = this._state(
      `sensor.nestquest_${slug}_completion_pct_today`
    );
    const presence = this._state(
      `binary_sensor.nestquest_${slug}_present_today`
    );
    const dueAttrs = dueSensor?.attributes ?? {};

    const due = clampCount(asNumber(dueSensor?.state, 0));
    const completed = clampCount(asNumber(doneSensor?.state, 0));
    const rawPct = pctSensor
      ? asNumber(pctSensor.state, Number.NaN)
      : Number.NaN;
    const pct = Number.isFinite(rawPct)
      ? clampPercent(rawPct)
      : due > 0
        ? clampPercent((completed / due) * 100)
        : 0;

    let present = true;
    const presentAttr = dueAttrs.present;
    if (typeof presentAttr === "boolean") {
      present = presentAttr;
    } else if (presence) {
      present = String(presence.state ?? "").trim().toLowerCase() === "on";
    }

    let name = "";
    const dueName = dueAttrs.child_name;
    if (typeof dueName === "string" && dueName.trim()) {
      name = dueName.trim();
    } else {
      const presenceName = presence?.attributes?.child_name;
      if (typeof presenceName === "string" && presenceName.trim()) {
        name = presenceName.trim();
      }
    }
    if (!name) {
      name = titleCaseSlug(slug);
    }

    const returnsDate = parseIsoDate(
      presence?.attributes?.next_present,
      this._timeZone()
    );
    const returns = returnsDate
      ? `Returns ${formatDay(returnsDate, this._timeZone())}`
      : null;

    return {
      slug,
      name,
      initial: (name.charAt(0) || "?").toUpperCase(),
      present: unresolved === null ? present : false,
      completed,
      due,
      pct,
      returns,
      unresolved,
    };
  }

  /** "missing" when the due sensor does not exist (integration not
   *  configured), "stale" when it answers unavailable/unknown (backend
   *  unreachable or the child is absent from the snapshot), null when
   *  it resolves. */
  private _dueSensorResolution(slug: string): "missing" | "stale" | null {
    const sensor = this._state(`sensor.nestquest_${slug}_quests_due_today`);
    if (!sensor) {
      return "missing";
    }
    const state = String(sensor.state ?? "").trim().toLowerCase();
    if (!state || state === "unavailable" || state === "unknown") {
      return "stale";
    }
    return null;
  }

  private _boardNotice(): BoardNotice | null {
    const plates = this._plates();
    if (plates.length === 0) {
      return BOARD_NOTICE_NOT_SET_UP;
    }
    if (plates.every((plate) => plate.unresolved !== null)) {
      return plates.some((plate) => plate.unresolved === "stale")
        ? BOARD_NOTICE_UNREACHABLE
        : BOARD_NOTICE_NOT_SET_UP;
    }
    return null;
  }

  private _renderNotice(notice: BoardNotice) {
    return html`
      <div class="notice-wrap">
        <div class="notice" role="status">
          ${notice.icon}
          <span class="notice-headline">${notice.headline}</span>
          <p class="notice-body">${notice.body}</p>
        </div>
      </div>
    `;
  }

  private _renderPlate(plate: ChildPlate) {
    if (plate.unresolved) {
      return html`
        <div class="plate unknown">
          <span class="crest away">
            <span class="crest-face">
              <span class="initial">${plate.initial}</span>
            </span>
          </span>
          <span class="name">${plate.name}</span>
          <span class="pill away">
            ${ICON_COMPASS}
            <span>Unknown</span>
          </span>
          <span class="progress-line">&mdash;</span>
          <span class="bar"></span>
        </div>
      `;
    }
    if (plate.present) {
      return html`
        <button
          class="plate"
          type="button"
          aria-label="Open ${plate.name}'s Quest Log"
          @click=${() => this._openQuestLog(plate.slug)}
        >
          <span class="crest">
            <span class="crest-face">
              <span class="initial">${plate.initial}</span>
            </span>
          </span>
          <span class="name">${plate.name}</span>
          <span class="pill">
            ${ICON_CHECK_CIRCLE}
            <span>Home today</span>
          </span>
          <span class="progress-line">
            ${plate.completed} of ${plate.due} quests claimed
          </span>
          <span class="bar">
            <span class="fill" style="width: ${plate.pct}%"></span>
          </span>
        </button>
      `;
    }
    return html`
      <div class="plate away">
        <span class="crest away">
          <span class="crest-face">
            <span class="initial">${plate.initial}</span>
          </span>
        </span>
        <span class="name">${plate.name}</span>
        <span class="pill away">
          ${ICON_TENT}
          <span>On travels</span>
        </span>
        <span class="progress-line">${plate.returns ?? "Returns —"}</span>
        <span class="bar"></span>
      </div>
    `;
  }

  private _openQuestLog(slug: string): void {
    const path = asString(this._config?.quest_log_path);
    if (!path) {
      return;
    }
    window.history.pushState(null, "", `${path.replace(/\/+$/, "")}/${slug}`);
    window.dispatchEvent(new Event("location-changed"));
  }

  private _dockWeather(): DockWeather | null {
    const entityId = asString(this._config?.weather_entity);
    if (!entityId) {
      return null;
    }
    const stateObj = this._state(entityId);
    if (!stateObj) {
      return null;
    }
    const condition = String(stateObj.state ?? "").trim();
    if (!condition || condition === "unavailable" || condition === "unknown") {
      return null;
    }
    const attrs = stateObj.attributes ?? {};
    let high: number | null = null;
    let low: number | null = null;
    const forecast = attrs.forecast;
    if (Array.isArray(forecast) && forecast.length > 0) {
      const entry = forecast[0];
      if (entry && typeof entry === "object") {
        const typed = entry as Record<string, unknown>;
        high = this._optionalNumber(typed.temperature);
        low = this._optionalNumber(typed.templow);
      }
    }
    return {
      condition,
      temperature: this._optionalNumber(attrs.temperature),
      high,
      low,
    };
  }

  private _optionalNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === "") {
      return null;
    }
    const parsed = typeof value === "number" ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private _renderDock() {
    const weather = this._dockWeather();
    if (!weather) {
      return html`
        <div class="dock">
          <span class="date">${formatDay(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${formatTime(this._now, this._timeZone())}</span>
        </div>
      `;
    }
    const label = conditionLabel(weather.condition);
    const phrase = conditionPhrase(weather.condition, label);
    const temperature =
      weather.temperature === null
        ? nothing
        : html`<span class="temp">${Math.round(weather.temperature)}°</span>`;
    const hiLo =
      weather.high === null || weather.low === null
        ? null
        : `${Math.round(weather.high)}° / ${Math.round(weather.low)}°`;
    return html`
      <div class="dock">
        ${ICON_CLOUD_SUN}
        ${temperature}
        <span class="divider"></span>
        <span class="condition">
          ${hiLo === null ? label : `${label} · ${hiLo}`}
        </span>
        <span class="divider"></span>
        <span class="condition">${phrase}</span>
      </div>
    `;
  }
}

customElements.define("nestquest-party-board-card", NestQuestPartyBoardCard);
registerCustomCard({
  type: "nestquest-party-board-card",
  name: "NestQuest Party Board",
  description: "Kids' attract screen for present and away adventurers.",
});
