import { LitElement, css, html, nothing, unsafeCSS, type TemplateResult } from "lit";
import { repeat } from "lit/directives/repeat.js";
import panelTokens from "../../../custom_components/nestquest/www/nestquest-panel-tokens.css?inline";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

type StateObject = {
  state: unknown;
  attributes?: Record<string, unknown> | null;
};

type PanelInstance = {
  id: number;
  title: string;
  icon: string | null;
  window: string;
  due_time: string | null;
  state: string;
  overdue: boolean;
  completed_at: string | null;
};

type WindowDef = {
  key: string;
  name: string;
  range: string;
  icon: TemplateResult;
};

type OtherChild = {
  slug: string;
  name: string;
  present: boolean;
  due: number;
  completed: number;
  returnsWeekday: string | null;
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

function formatWeekday(date: Date, timeZone: string | undefined): string {
  return zonedFormatter(timeZone, { weekday: "long" }).format(date);
}

function formatInstant(value: string, timeZone: string | undefined): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return zonedFormatter(timeZone, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(parsed);
}

function formatWallClock(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) {
    return null;
  }
  const hours = Number(match[1]);
  if (hours > 23) {
    return null;
  }
  const suffix = hours >= 12 ? "PM" : "AM";
  const hour12 = hours % 12 === 0 ? 12 : hours % 12;
  return `${hour12}:${match[2]} ${suffix}`;
}

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

function childSlugFromPath(): string {
  const segments = window.location.pathname.split("/").filter(Boolean);
  return segments.length > 0
    ? segments[segments.length - 1].toLowerCase()
    : "";
}

function toPanelInstance(value: unknown): PanelInstance | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  const state = asString(row.state).toLowerCase();
  if (state !== "open" && state !== "completed") {
    return null;
  }
  const id = asNumber(row.id, 0);
  if (!id) {
    return null;
  }
  return {
    id,
    title: asString(row.title) || "Quest",
    icon: asString(row.icon) || null,
    window: asString(row.window).toLowerCase(),
    due_time: asString(row.due_time) || null,
    state,
    overdue: row.overdue === true,
    completed_at: asString(row.completed_at) || null,
  };
}

const SHIELD_CLIP = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)";
const HEXAGON_CLIP =
  "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)";

const SEAL_ROTATIONS = [-9, 6, -4];

const logStyles = css`
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

  .header {
    position: absolute;
    top: 56px;
    left: var(--nq-p-page-inset);
    right: var(--nq-p-page-inset);
    display: flex;
    align-items: center;
    gap: 28px;
  }

  .crest {
    position: relative;
    flex: none;
    width: 96px;
    height: 110px;
    padding: 3px;
    clip-path: ${unsafeCSS(SHIELD_CLIP)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 32px;
    clip-path: ${unsafeCSS(SHIELD_CLIP)};
    background: var(--nq-p-crest);
  }

  .crest .initial {
    font-family: var(--nq-p-font-display);
    font-size: 44px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .titles {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  .title {
    margin: 0;
    font-family: var(--nq-p-font-display);
    font-size: var(--nq-p-size-title);
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sub {
    margin: 0;
    font-family: var(--nq-p-font-heading);
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .remaining {
    margin-left: auto;
    flex: none;
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 18px 28px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: 14px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
  }

  .d20 {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    clip-path: ${unsafeCSS(HEXAGON_CLIP)};
    background: var(--nq-brand-gradient);
  }

  .d20-numeral {
    font-family: var(--nq-p-font-heading);
    font-size: 19px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .remaining-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .remaining-count {
    font-family: var(--nq-p-font-heading);
    font-size: 28px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
  }

  .party-line {
    font-family: var(--nq-p-font-body);
    font-size: var(--nq-p-size-body);
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .columns {
    position: absolute;
    top: 236px;
    left: var(--nq-p-page-inset);
    right: var(--nq-p-page-inset);
    bottom: 130px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 34px;
  }

  .column {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .column-head {
    flex: none;
    display: flex;
    align-items: center;
    gap: 14px;
    padding-bottom: 14px;
    border-bottom: var(--nq-p-rule);
  }

  .column-head svg {
    flex: none;
    width: 34px;
    height: 34px;
    color: var(--nq-p-ink-secondary);
  }

  .column-names {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .column-name {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-section);
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
  }

  .column-range {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-label);
    font-weight: 600;
    letter-spacing: var(--nq-p-track-label);
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .column-count {
    margin-left: auto;
    flex: none;
    font-family: var(--nq-p-font-heading);
    font-size: 26px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink-secondary);
  }

  .stack {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: visible;
    gap: var(--nq-p-quest-gap);
    margin-top: 22px;
  }

  .quest {
    position: relative;
    display: flex;
    align-items: center;
    gap: 22px;
    min-height: var(--nq-p-quest-min-height);
    padding: var(--nq-p-quest-pad);
    border: 1px solid var(--nq-p-card-border);
    border-radius: var(--nq-p-radius-card);
    background: var(--nq-p-card-open);
    box-shadow: var(--nq-p-card-shadow);
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  .quest.tappable {
    cursor: pointer;
  }

  .quest.tappable:active {
    transform: scale(0.98);
  }

  .quest.sealed {
    background: var(--nq-p-card-done);
    opacity: 0.82;
    box-shadow: none;
  }

  .tile {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--nq-p-tile-size);
    height: var(--nq-p-tile-size);
    border-radius: 10px;
    background: var(--nq-p-icon-tile);
    color: #ffffff;
  }

  .tile svg {
    width: 34px;
    height: 34px;
  }

  .sealed .tile {
    background: var(--nq-p-icon-tile-done);
    color: var(--nq-p-ink-secondary);
  }

  .quest .body {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .quest .quest-title {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-quest);
    font-weight: 700;
    line-height: 1.15;
    color: var(--nq-p-ink);
    overflow-wrap: anywhere;
  }

  .sealed .quest-title {
    color: var(--nq-p-ink-muted);
    text-decoration: line-through;
  }

  .quest .meta {
    font-family: var(--nq-p-font-body);
    font-size: var(--nq-p-size-body);
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .quest .meta.late {
    font-family: var(--nq-p-font-heading);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--nq-p-ink-late);
  }

  button.complete {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    height: var(--nq-p-button-height);
    min-width: var(--nq-p-button-min-width);
    border: none;
    border-radius: 10px;
    background: var(--nq-brand-gradient);
    color: #ffffff;
    font-family: var(--nq-p-font-heading);
    font-size: 24px;
    font-weight: 700;
    line-height: 1;
    box-shadow: 0 3px 0 rgba(40, 20, 60, 0.35);
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  button.complete:active {
    transform: scale(0.98);
  }

  button.complete svg {
    width: 30px;
    height: 30px;
  }

  button:focus-visible {
    outline: 3px solid var(--nq-brand-purple);
    outline-offset: 4px;
  }

  .seal {
    position: absolute;
    right: 16px;
    top: -12px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--nq-p-seal-size);
    height: var(--nq-p-seal-size);
    border-radius: var(--nq-p-radius-pill);
    background: var(--nq-p-seal);
    box-shadow: var(--nq-p-seal-shadow);
    color: rgba(255, 235, 235, 0.95);
    transform: rotate(var(--seal-rot, 0deg));
    animation: seal-in var(--nq-dur-base) var(--nq-ease-out);
    pointer-events: none;
  }

  .seal svg {
    width: 38px;
    height: 38px;
  }

  @keyframes seal-in {
    from {
      opacity: 0;
      transform: scale(1.15) rotate(var(--seal-rot, 0deg));
    }
    to {
      opacity: 1;
      transform: scale(1) rotate(var(--seal-rot, 0deg));
    }
  }

  .rollup {
    border: 2px dashed var(--nq-p-panel-border);
    border-radius: 14px;
    padding: 16px 22px;
  }

  .rollup-label {
    display: block;
    font-family: var(--nq-p-font-heading);
    font-size: 18px;
    font-weight: 600;
    letter-spacing: var(--nq-p-track-label);
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .rollup-body {
    margin: 6px 0 0;
    font-family: var(--nq-p-font-body);
    font-size: 23px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--nq-p-ink-secondary);
  }

  .scrim {
    position: absolute;
    inset: 0;
    z-index: 10;
    background: rgba(30, 20, 10, 0.62);
  }

  .dialog {
    position: absolute;
    top: 196px;
    left: 460px;
    width: 1000px;
    border: 3px solid rgba(92, 62, 26, 0.5);
    border-radius: 20px;
    background: var(--nq-p-card-panel);
    box-shadow: 0 26px 60px rgba(20, 10, 0, 0.5);
    padding: 64px 68px 56px;
    animation: dialog-in var(--nq-dur-modal) var(--nq-ease-out);
  }

  @keyframes dialog-in {
    from {
      opacity: 0;
      transform: scale(0.96);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  .dialog-header {
    display: flex;
    align-items: center;
    gap: 24px;
  }

  .dialog-tile {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 104px;
    height: 104px;
    border-radius: 12px;
    background: var(--nq-p-icon-tile);
    color: #ffffff;
  }

  .dialog-tile svg {
    width: 56px;
    height: 56px;
  }

  .dialog-titles {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  .dialog-kicker {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-label);
    font-weight: 600;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .dialog-quest-title {
    font-family: var(--nq-p-font-display);
    font-size: 58px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
    overflow-wrap: anywhere;
  }

  .dialog-body {
    margin: 28px 0 0;
    font-family: var(--nq-p-font-body);
    font-size: 32px;
    font-weight: 600;
    line-height: 1.35;
    color: #3f2f1c;
  }

  .dialog-buttons {
    display: flex;
    gap: 24px;
    margin-top: 40px;
  }

  button.confirm-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    height: var(--nq-p-confirm-button);
    border-radius: 10px;
    font-family: var(--nq-p-font-heading);
    font-weight: 700;
    line-height: 1;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  button.confirm-button:active {
    transform: scale(0.98);
  }

  button.not-yet {
    flex: 1;
    border: 2px solid rgba(92, 62, 26, 0.5);
    background: rgba(92, 62, 26, 0.1);
    color: var(--nq-p-ink);
    font-size: 30px;
  }

  button.not-yet svg {
    width: 34px;
    height: 34px;
  }

  button.do-complete {
    flex: 2;
    border: none;
    background: var(--nq-brand-gradient);
    color: #ffffff;
    font-size: 32px;
  }

  button.do-complete svg {
    width: 38px;
    height: 38px;
  }
`;

const ICON_CHECK = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M20 6 9 17l-5-5"></path>
</svg>`;

const ICON_X = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M18 6 6 18"></path>
  <path d="m6 6 12 12"></path>
</svg>`;

const ICON_STAR = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <polygon
    points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26"
  ></polygon>
</svg>`;

const ICON_SUNRISE = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 2v8"></path>
  <path d="m4.93 10.93 1.41 1.41"></path>
  <path d="M2 18h2"></path>
  <path d="M20 18h2"></path>
  <path d="m19.07 10.93-1.41 1.41"></path>
  <path d="M22 22H2"></path>
  <path d="m8 6 4-4 4 4"></path>
  <path d="M16 18a4 4 0 0 0-8 0"></path>
</svg>`;

const ICON_SUN = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <circle cx="12" cy="12" r="4"></circle>
  <path d="M12 2v2"></path>
  <path d="M12 20v2"></path>
  <path d="m4.93 4.93 1.41 1.41"></path>
  <path d="m17.66 17.66 1.41 1.41"></path>
  <path d="M2 12h2"></path>
  <path d="M20 12h2"></path>
  <path d="m6.34 17.66-1.41 1.41"></path>
  <path d="m19.07 4.93-1.41 1.41"></path>
</svg>`;

const ICON_MOON = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>
</svg>`;

const WINDOW_DEFS: WindowDef[] = [
  { key: "morning", name: "Morning", range: "Until 11:59 AM", icon: ICON_SUNRISE },
  { key: "afternoon", name: "Afternoon", range: "12:00–5:00 PM", icon: ICON_SUN },
  { key: "evening", name: "Evening", range: "5:00–9:00 PM", icon: ICON_MOON },
];

export class NestQuestQuestLogCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _now: { state: true },
    _confirm: { state: true },
  };

  static styles = [unsafeCSS(panelTokens), logStyles];

  hass?: HassLike;
  _config?: CardConfig;
  _now = new Date();
  _confirm: number | null = null;
  private _clockTimer?: number;
  private _idleTimer?: number;
  private _confirmTimer?: number;

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
    }, 60000);
    window.addEventListener("pointerdown", this._onActivity, true);
    window.addEventListener("touchstart", this._onActivity, true);
    window.addEventListener("keydown", this._onActivity, true);
    this._armIdle();
  }

  disconnectedCallback(): void {
    this._stopClock();
    this._clearIdle();
    this._clearConfirmTimer();
    window.removeEventListener("pointerdown", this._onActivity, true);
    window.removeEventListener("touchstart", this._onActivity, true);
    window.removeEventListener("keydown", this._onActivity, true);
    super.disconnectedCallback();
  }

  render() {
    return html`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        ${this._renderHeader()}
        <div class="columns">
          ${WINDOW_DEFS.map((windowDef) => this._renderColumn(windowDef))}
        </div>
        ${this._renderConfirm()}
      </div>
    `;
  }

  private _timeZone(): string | undefined {
    return hassTimeZone(this.hass);
  }

  private _state(entityId: string): StateObject | null {
    const states = this.hass?.states as Record<string, StateObject> | undefined;
    const stateObj = states?.[entityId];
    return stateObj && typeof stateObj === "object" ? stateObj : null;
  }

  private _childSlug(): string {
    return childSlugFromPath();
  }

  private _boardPath(): string {
    return asString(this._config?.board_path).replace(/\/+$/, "");
  }

  private _idleSeconds(): number {
    const seconds = asNumber(this._config?.idle_return_seconds, 40);
    return seconds > 0 ? seconds : 40;
  }

  private _confirmSeconds(): number {
    const seconds = asNumber(this._config?.confirm_timeout_seconds, 15);
    return seconds > 0 ? seconds : 15;
  }

  private _childName(slug: string): string | null {
    if (!slug) {
      return null;
    }
    const name = this._state(`sensor.nestquest_${slug}_quests_due_today`)
      ?.attributes?.child_name;
    if (typeof name === "string" && name.trim()) {
      return name.trim();
    }
    return null;
  }

  private _childCounts(slug: string): { due: number; completed: number } {
    const dueSensor = this._state(`sensor.nestquest_${slug}_quests_due_today`);
    const completedSensor = this._state(
      `sensor.nestquest_${slug}_quests_completed_today`
    );
    const due = clampCount(asNumber(dueSensor?.state, 0));
    const completed = clampCount(asNumber(completedSensor?.state, 0));
    return { due, completed };
  }

  private _instances(): PanelInstance[] {
    const slug = this._childSlug();
    if (!slug) {
      return [];
    }
    const payload = this._state(`sensor.nestquest_${slug}_quests_due_today`)
      ?.attributes?.instances;
    if (!Array.isArray(payload)) {
      return [];
    }
    return payload
      .map(toPanelInstance)
      .filter((instance): instance is PanelInstance => instance !== null);
  }

  private _remaining(): number {
    const slug = this._childSlug();
    if (!slug) {
      return 0;
    }
    const sensor = this._state(
      `sensor.nestquest_${slug}_quests_remaining_today`
    );
    if (sensor) {
      return clampCount(asNumber(sensor.state, 0));
    }
    const { due, completed } = this._childCounts(slug);
    return clampCount(due - completed);
  }

  private _partyCounts(): { completed: number; due: number } {
    const householdDue = this._state(
      "sensor.nestquest_household_quests_due_today"
    );
    const householdCompleted = this._state(
      "sensor.nestquest_household_quests_completed_today"
    );
    if (householdDue || householdCompleted) {
      return {
        completed: clampCount(asNumber(householdCompleted?.state, 0)),
        due: clampCount(asNumber(householdDue?.state, 0)),
      };
    }
    const slug = this._childSlug();
    const { due, completed } = this._childCounts(slug);
    return { completed, due };
  }

  private _otherChildren(): OtherChild[] {
    const states = this.hass?.states as
      | Record<string, StateObject>
      | undefined;
    if (!states) {
      return [];
    }
    const slug = this._childSlug();
    const timeZone = this._timeZone();
    const result: OtherChild[] = [];
    for (const entityId of Object.keys(states)) {
      const match = /^sensor\.nestquest_(.+)_quests_due_today$/.exec(entityId);
      if (!match || match[1] === "household" || match[1] === slug) {
        continue;
      }
      const childSlug = match[1];
      const attrs = states[entityId]?.attributes ?? {};
      let name = "";
      if (typeof attrs.child_name === "string" && attrs.child_name.trim()) {
        name = attrs.child_name.trim();
      } else {
        name = titleCaseSlug(childSlug);
      }
      let present = true;
      if (typeof attrs.present === "boolean") {
        present = attrs.present;
      } else {
        const presence = this._state(
          `binary_sensor.nestquest_${childSlug}_present_today`
        );
        present =
          presence === null ||
          String(presence.state ?? "").trim().toLowerCase() !== "off";
      }
      const completedSensor = this._state(
        `sensor.nestquest_${childSlug}_quests_completed_today`
      );
      const due = clampCount(asNumber(states[entityId]?.state, 0));
      const completed = clampCount(asNumber(completedSensor?.state, 0));
      let returnsWeekday: string | null = null;
      if (!present) {
        const presence = this._state(
          `binary_sensor.nestquest_${childSlug}_present_today`
        );
        const nextPresent = parseIsoDate(
          presence?.attributes?.next_present,
          timeZone
        );
        returnsWeekday = nextPresent
          ? formatWeekday(nextPresent, timeZone)
          : null;
      }
      result.push({
        slug: childSlug,
        name,
        present,
        due,
        completed,
        returnsWeekday,
      });
    }
    return result.sort((a, b) => a.name.localeCompare(b.name));
  }

  private _renderHeader() {
    const slug = this._childSlug();
    const name = this._childName(slug);
    const displayName = name ?? (slug ? titleCaseSlug(slug) : null);
    const { due, completed } = this._childCounts(slug);
    const remaining = this._remaining();
    const party = this._partyCounts();
    const title = displayName ? `${displayName}'s Quest Log` : "Quest Log";
    const initial = (displayName?.charAt(0) || "?").toUpperCase();
    return html`
      <header class="header">
        <span class="crest" aria-hidden="true">
          <span class="crest-face">
            <span class="initial">${initial}</span>
          </span>
        </span>
        <div class="titles">
          <h1 class="title">${title}</h1>
          <p class="sub">
            ${formatDay(this._now, this._timeZone())} · ${completed} of ${due}
            claimed
          </p>
        </div>
        <div class="remaining">
          <span class="d20" aria-hidden="true">
            <span class="d20-numeral">${remaining}</span>
          </span>
          <div class="remaining-text">
            <span class="remaining-count">
              ${remaining} quest${remaining === 1 ? "" : "s"} left
            </span>
            <span class="party-line">
              Party progress · ${party.completed} of ${party.due} today
            </span>
          </div>
        </div>
      </header>
    `;
  }

  private _renderColumn(windowDef: WindowDef) {
    const instances = this._instances().filter(
      (instance) => instance.window === windowDef.key
    );
    const open = instances
      .filter((instance) => instance.state === "open")
      .sort((a, b) =>
        (a.due_time ?? "99:99").localeCompare(b.due_time ?? "99:99")
      );
    const sealed = instances.filter(
      (instance) => instance.state === "completed"
    );
    const count = instances.length;
    let stackStyle: string | typeof nothing = nothing;
    if (count > 0) {
      const rollupReserve =
        windowDef.key === "afternoon" && this._otherChildren().length > 0
          ? 160
          : 0;
      const available = 644 - rollupReserve;
      const gap = Math.min(
        24,
        Math.max(8, Math.floor((available - count * 74) / Math.max(count - 1, 1)))
      );
      const minHeight = Math.min(
        116,
        Math.max(74, Math.floor((available - (count - 1) * gap) / count))
      );
      const buttonHeight = Math.max(56, Math.min(72, minHeight - 2));
      let stackVars = `--nq-p-quest-gap: ${gap}px; --nq-p-quest-min-height: ${minHeight}px; --nq-p-button-height: ${buttonHeight}px`;
      if (count >= 5) {
        const pad = Math.max(0, Math.min(22, Math.floor((minHeight - buttonHeight - 2) / 2)));
        const tile = Math.max(44, Math.min(64, minHeight - 2 * pad - 2));
        stackVars += `; --nq-p-quest-pad: ${pad}px; --nq-p-tile-size: ${tile}px`;
      }
      stackStyle = stackVars;
    }
    return html`
      <section
        class="column"
        aria-label="${windowDef.name} quests"
        style=${stackStyle}
      >
        <div class="column-head">
          ${windowDef.icon}
          <div class="column-names">
            <span class="column-name">${windowDef.name}</span>
            <span class="column-range">${windowDef.range}</span>
          </div>
          <span class="column-count">${sealed.length}/${instances.length}</span>
        </div>
        <div class="stack">
          ${repeat(
            open,
            (instance) => instance.id,
            (instance) => this._renderQuest(instance, false, 0)
          )}
          ${repeat(
            sealed,
            (instance) => instance.id,
            (instance, index) => this._renderQuest(instance, true, index)
          )}
          ${windowDef.key === "afternoon" ? this._renderRollup() : nothing}
        </div>
      </section>
    `;
  }

  private _renderQuest(
    instance: PanelInstance,
    sealed: boolean,
    sealedIndex: number
  ) {
    if (sealed) {
      const rotation = SEAL_ROTATIONS[sealedIndex % SEAL_ROTATIONS.length];
      const claimedAt = instance.completed_at
        ? formatInstant(instance.completed_at, this._timeZone())
        : "";
      return html`
        <div class="quest sealed" data-instance-id=${instance.id}>
          <span class="tile" aria-hidden="true">${ICON_STAR}</span>
          <div class="body">
            <span class="quest-title">${instance.title}</span>
            <span class="meta">
              ${claimedAt ? `Claimed ${claimedAt}` : "Claimed"}
            </span>
          </div>
          <span
            class="seal"
            aria-hidden="true"
            style="--seal-rot: ${rotation}deg"
          >
            ${ICON_CHECK}
          </span>
        </div>
      `;
    }
    const dueAt = formatWallClock(instance.due_time);
    const meta = instance.overdue
      ? {
          text: dueAt ? `Overdue · due ${dueAt}` : "Overdue",
          late: true,
        }
      : {
          text: dueAt ? `Due by ${dueAt}` : "Due today",
          late: false,
        };
    return html`
      <div
        class="quest tappable"
        role="button"
        tabindex="0"
        data-instance-id=${instance.id}
        aria-label="Complete ${instance.title}"
        @click=${() => this._openConfirm(instance.id)}
        @keydown=${(event: KeyboardEvent) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this._openConfirm(instance.id);
          }
        }}
      >
        <span class="tile" aria-hidden="true">${ICON_STAR}</span>
        <div class="body">
          <span class="quest-title">${instance.title}</span>
          <span class="meta ${meta.late ? "late" : nothing}">${meta.text}</span>
        </div>
        <button
          class="complete"
          type="button"
          @click=${() => this._openConfirm(instance.id)}
        >
          ${ICON_CHECK}
          <span>Complete</span>
        </button>
      </div>
    `;
  }

  private _renderRollup() {
    const others = this._otherChildren();
    if (others.length === 0) {
      return nothing;
    }
    const sentences = others.slice(0, 2).map((child) => {
      if (!child.present) {
        return child.returnsWeekday
          ? `${child.name} is on travels until ${child.returnsWeekday}.`
          : `${child.name} is on travels.`;
      }
      if (child.due > 0 && child.completed >= child.due) {
        return `${child.name} has finished their log.`;
      }
      if (child.due > child.completed) {
        return `${child.name} has ${child.due - child.completed} quests left.`;
      }
      return `${child.name} has no quests today.`;
    });
    return html`
      <div class="rollup">
        <span class="rollup-label">Party roll-up</span>
        <p class="rollup-body">${sentences.join(" ")}</p>
      </div>
    `;
  }

  private _renderConfirm() {
    if (this._confirm === null) {
      return nothing;
    }
    const instance = this._instances().find(
      (candidate) => candidate.id === this._confirm
    );
    if (!instance) {
      return nothing;
    }
    const windowDef = WINDOW_DEFS.find((entry) => entry.key === instance.window);
    return html`
      <div class="scrim" @click=${() => this._closeConfirm()}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          @click=${(event: Event) => event.stopPropagation()}
        >
          <div class="dialog-header">
            <span class="dialog-tile" aria-hidden="true">${ICON_STAR}</span>
            <div class="dialog-titles">
              <span class="dialog-kicker">
                ${windowDef?.name ?? "Quest"}
              </span>
              <span class="dialog-quest-title">${instance.title}</span>
            </div>
          </div>
          <p class="dialog-body">
            Mark this quest complete? Once the seal is set, only a parent can
            undo it.
          </p>
          <div class="dialog-buttons">
            <button
              class="confirm-button not-yet"
              type="button"
              @click=${() => this._closeConfirm()}
            >
              ${ICON_X}
              <span>Not yet</span>
            </button>
            <button
              class="confirm-button do-complete"
              type="button"
              @click=${() => this._confirmComplete()}
            >
              ${ICON_CHECK}
              <span>Complete</span>
            </button>
          </div>
        </div>
      </div>
    `;
  }

  private _openConfirm(instanceId: number): void {
    this._confirm = instanceId;
    this._armConfirmTimer();
  }

  private _closeConfirm(): void {
    this._clearConfirmTimer();
    this._confirm = null;
  }

  private _confirmComplete(): void {
    this._closeConfirm();
  }

  private _armConfirmTimer(): void {
    this._clearConfirmTimer();
    this._confirmTimer = window.setTimeout(() => {
      this._confirmTimer = undefined;
      this._closeConfirm();
    }, this._confirmSeconds() * 1000);
  }

  private _clearConfirmTimer(): void {
    if (this._confirmTimer !== undefined) {
      window.clearTimeout(this._confirmTimer);
      this._confirmTimer = undefined;
    }
  }

  private _armIdle(): void {
    this._clearIdle();
    this._idleTimer = window.setTimeout(() => {
      this._idleTimer = undefined;
      this._returnToBoard();
    }, this._idleSeconds() * 1000);
  }

  private _clearIdle(): void {
    if (this._idleTimer !== undefined) {
      window.clearTimeout(this._idleTimer);
      this._idleTimer = undefined;
    }
  }

  private _returnToBoard(): void {
    const path = this._boardPath();
    if (!path) {
      return;
    }
    window.history.pushState(null, "", path);
    window.dispatchEvent(new Event("location-changed"));
  }

  private _stopClock(): void {
    if (this._clockTimer !== undefined) {
      window.clearInterval(this._clockTimer);
      this._clockTimer = undefined;
    }
  }

  private _onActivity = (): void => {
    this._armIdle();
    if (this._confirm !== null) {
      this._armConfirmTimer();
    }
  };
}

customElements.define("nestquest-quest-log-card", NestQuestQuestLogCard);
registerCustomCard({
  type: "nestquest-quest-log-card",
  name: "NestQuest Quest Log",
  description: "One child's daily quests, grouped by window.",
});
