import { LitElement, css, html, nothing, unsafeCSS, type TemplateResult } from "lit";
import { repeat } from "lit/directives/repeat.js";
import panelTokens from "../../../custom_components/nestquest/www/nestquest-panel-tokens.css?inline";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

type QuestLogCardConfig = CardConfig & {
  weather_entity?: string;
};

type StateObject = {
  state: unknown;
  attributes?: Record<string, unknown> | null;
};

type HassConnection = {
  subscribeEvents: (
    callback: (event: unknown) => void,
    eventType: string
  ) => Promise<() => void>;
};

const NESTQUEST_EVENT_TYPES = [
  "nestquest_quest_completed",
  "nestquest_quest_uncompleted",
  "nestquest_quest_missed",
  "nestquest_child_day_complete",
];

type PanelInstance = {
  id: number;
  child_id: number | null;
  title: string;
  icon: string | null;
  window: string;
  due_time: string | null;
  state: string;
  overdue: boolean;
  completed_at: string | null;
  on_time: boolean | null;
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

/** The one state the log resolves before rendering anything; see
 *  design/PANEL-EMPTY-STATES.md for the decisions behind each kind. */
type LogView =
  | { kind: "no-adventurer" }
  | { kind: "not-set-up" }
  | { kind: "unreachable" }
  | { kind: "away"; name: string; returns: string | null }
  | { kind: "empty-day"; name: string }
  | { kind: "complete-day"; name: string }
  | { kind: "normal" };

type LogNotice = {
  icon: TemplateResult;
  headline: string;
  body: string;
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

function formatTime(date: Date, timeZone: string | undefined): string {
  return zonedFormatter(timeZone, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date);
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
  const childId = asNumber(row.child_id, 0);
  return {
    id,
    child_id: childId > 0 ? childId : null,
    title: asString(row.title) || "Quest",
    icon: asString(row.icon) || null,
    window: asString(row.window).toLowerCase(),
    due_time: asString(row.due_time) || null,
    state,
    overdue: row.overdue === true,
    completed_at: asString(row.completed_at) || null,
    on_time: row.on_time === true ? true : row.on_time === false ? false : null,
  };
}

type DockWeather = {
  condition: string;
  temperature: number | null;
  high: number | null;
  low: number | null;
};

const CONDITION_LABELS: Record<string, string> = {
  "clear-night": "Clear",
  cloudy: "Cloudy",
  exceptional: "Clear",
  fog: "Foggy",
  hail: "Hail",
  lightning: "Storms",
  "lightning-rainy": "Storms",
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
  "lightning-rainy": "Storms may roll in",
  partlycloudy: "Sun between clouds",
  pouring: "Heavy rain outside",
  rainy: "Rain on the walls",
  snowy: "Snow on the peaks",
  "snowy-rainy": "Sleet may fall",
  sunny: "Clear skies today",
  windy: "A blustery day",
  "windy-variant": "A blustery day",
};

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

  .crest.away .crest-face {
    background: var(--nq-p-crest-away);
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

  .notice-wrap {
    position: absolute;
    top: 236px;
    left: var(--nq-p-page-inset);
    right: var(--nq-p-page-inset);
    bottom: 130px;
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
    border-radius: 20px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    text-align: center;
  }

  .notice svg {
    width: 46px;
    height: 46px;
    color: var(--nq-p-ink-secondary);
  }

  .notice.away {
    background: linear-gradient(#f2ecdd, #e6dcc6);
    border-style: dashed;
    box-shadow: none;
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

  .notice-seal {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 78px;
    height: 78px;
    border-radius: var(--nq-p-radius-pill);
    background: var(--nq-p-seal);
    box-shadow: var(--nq-p-seal-shadow);
    color: rgba(255, 235, 235, 0.95);
    transform: rotate(-6deg);
  }

  .notice-seal svg {
    width: 38px;
    height: 38px;
    color: rgba(255, 235, 235, 0.95);
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

  .toast {
    position: absolute;
    left: 50%;
    bottom: 158px;
    z-index: 20;
    transform: translateX(-50%);
    max-width: calc(100% - 124px);
    padding: 20px 32px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: 14px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    font-family: var(--nq-p-font-body);
    font-size: 23px;
    font-weight: 600;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--nq-p-ink-secondary);
    animation: toast-in var(--nq-dur-base) var(--nq-ease-out);
    pointer-events: none;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 12px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  .complete-screen {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 96px 62px 130px;
    text-align: center;
  }

  .complete-seal {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 168px;
    height: 168px;
    border-radius: var(--nq-p-radius-pill);
    background: var(--nq-p-seal);
    box-shadow: 0 10px 24px rgba(60, 10, 20, 0.42);
    color: rgba(255, 235, 235, 0.95);
    transform: rotate(-6deg);
  }

  .complete-seal svg {
    width: 86px;
    height: 86px;
  }

  .complete-title {
    margin: 28px 0 0;
    font-family: var(--nq-p-font-display);
    font-size: 86px;
    font-weight: 900;
    line-height: 1.1;
    background: var(--nq-brand-gradient-h);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    -webkit-text-fill-color: transparent;
  }

  .complete-sub {
    margin: 16px 0 0;
    max-width: 1000px;
    font-family: var(--nq-p-font-body);
    font-size: 34px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--nq-p-ink-secondary);
    text-wrap: pretty;
  }

  .complete-countdown {
    margin: 12px 0 0;
    font-family: var(--nq-p-font-body);
    font-size: 25px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .complete-stats {
    position: absolute;
    top: 540px;
    left: 200px;
    right: 200px;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 26px;
  }

  .complete-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 28px 16px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: 16px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
  }

  .complete-stat .numeral {
    font-family: var(--nq-p-font-heading);
    font-size: 58px;
    font-weight: 900;
    line-height: 1;
    color: var(--nq-p-ink);
  }

  .complete-stat .label {
    font-family: var(--nq-p-font-heading);
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
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

const ICON_CLOUD_MOON = html`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M13 16a3 3 0 1 1 0 6H7a5 5 0 1 1 4.9-6Z"></path>
  <path d="M10.1 9A6 6 0 0 1 16 4a4.5 4.5 0 0 0 8.9 4.2v.1a6 6 0 0 1-5.2 5.7"></path>
</svg>`;

const LOG_NOTICE_NO_ADVENTURER: LogNotice = {
  icon: ICON_COMPASS,
  headline: "No adventurer chosen",
  body: "Open The Party and tap your crest to open your quest log.",
};

const LOG_NOTICE_NOT_SET_UP: LogNotice = {
  icon: ICON_ALERT,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest.",
};

const LOG_NOTICE_UNREACHABLE: LogNotice = {
  icon: ICON_CLOUD_OFF,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly.",
};

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
    _optimistic: { state: true },
    _toast: { state: true },
    _countdown: { state: true },
  };

  static styles = [unsafeCSS(panelTokens), logStyles];

  hass?: HassLike;
  _config?: QuestLogCardConfig;
  _now = new Date();
  _confirm: number | null = null;
  /** instanceId → the completion instant stamped before the service has
   *  answered; the seal shows immediately and reverts on failure. */
  _optimistic = new Map<number, string>();
  _toast: string | null = null;
  _countdown: number | null = null;
  private _clockTimer?: number;
  private _idleTimer?: number;
  private _confirmTimer?: number;
  private _toastTimer?: number;
  private _completeTimer?: number;
  private _unsubs: Array<() => void> = [];
  private _subscribed = false;
  private _subGeneration = 0;
  private _retryTimer?: number;

  setConfig(config: QuestLogCardConfig): void {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid configuration");
    }
    this._config = config;
  }

  private _hassConnection(): HassConnection | null {
    const connection = (this.hass as { connection?: unknown } | undefined)
      ?.connection;
    if (
      !connection ||
      typeof connection !== "object" ||
      typeof (connection as HassConnection).subscribeEvents !== "function"
    ) {
      return null;
    }
    return connection as HassConnection;
  }

  private _subscribeLive(): void {
    if (this._subscribed) {
      return;
    }
    const connection = this._hassConnection();
    if (!connection) {
      return;
    }
    this._subscribed = true;
    const token = ++this._subGeneration;
    const track = (unsubPromise: Promise<() => void>): void => {
      unsubPromise
        .then((unsub) => {
          if (this._subscribed && token === this._subGeneration) {
            this._unsubs.push(unsub);
          } else {
            unsub();
          }
        })
        .catch(() => {
          if (token === this._subGeneration) {
            this._unsubscribeLive();
            this._armSubscribeRetry();
          }
        });
    };
    for (const eventType of NESTQUEST_EVENT_TYPES) {
      track(
        connection.subscribeEvents(() => this.requestUpdate(), eventType)
      );
    }
  }

  private _armSubscribeRetry(): void {
    if (this._retryTimer !== undefined) {
      return;
    }
    this._retryTimer = window.setTimeout(() => {
      this._retryTimer = undefined;
      this._subscribeLive();
    }, 1000);
  }

  private _clearSubscribeRetry(): void {
    if (this._retryTimer !== undefined) {
      window.clearTimeout(this._retryTimer);
      this._retryTimer = undefined;
    }
  }

  private _unsubscribeLive(): void {
    this._clearSubscribeRetry();
    this._subGeneration++;
    for (const unsub of this._unsubs) {
      unsub();
    }
    this._unsubs = [];
    this._subscribed = false;
  }

  getCardSize(): number {
    return 22;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._subscribeLive();
    this._now = new Date();
    this._clockTimer = window.setInterval(() => {
      this._now = new Date();
    }, 60000);
    window.addEventListener("pointerdown", this._onActivity, true);
    window.addEventListener("touchstart", this._onActivity, true);
    window.addEventListener("keydown", this._onActivity, true);
    this._armIdle();
    if (this._logView().kind === "complete-day") {
      this._armCompleteTimer();
    }
  }

  protected updated(): void {
    this._subscribeLive();
    if (this._logView().kind === "complete-day") {
      this._clearIdle();
      this._armCompleteTimer();
    } else {
      this._clearCompleteTimer();
      this._countdown = null;
      if (this._idleTimer === undefined) {
        this._armIdle();
      }
    }
  }

  disconnectedCallback(): void {
    this._unsubscribeLive();
    this._stopClock();
    this._clearIdle();
    this._clearConfirmTimer();
    this._clearToastTimer();
    this._clearCompleteTimer();
    window.removeEventListener("pointerdown", this._onActivity, true);
    window.removeEventListener("touchstart", this._onActivity, true);
    window.removeEventListener("keydown", this._onActivity, true);
    super.disconnectedCallback();
  }

  render() {
    const view = this._logView();
    return html`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        ${this._renderMain(view)}
        ${this._renderConfirm()}
        ${this._renderToast()}
      </div>
    `;
  }

  private _renderToast(): TemplateResult | typeof nothing {
    if (this._toast === null) {
      return nothing;
    }
    return html`
      <div class="toast" role="status">${this._toast}</div>
    `;
  }

  private _renderMain(view: LogView): TemplateResult {
    switch (view.kind) {
      case "no-adventurer":
        return this._renderNotice(LOG_NOTICE_NO_ADVENTURER);
      case "not-set-up":
        return this._renderNotice(LOG_NOTICE_NOT_SET_UP);
      case "unreachable":
        return this._renderNotice(LOG_NOTICE_UNREACHABLE);
      case "away": {
        const body = ["The quest log unlocks when they return."];
        if (view.returns) {
          body.push(`Returns ${view.returns}`);
        }
        return html`
          ${this._renderHeader(view)}
          <div class="notice-wrap">
            <div class="notice away" role="status">
              ${ICON_TENT}
              <span class="notice-headline">${view.name} is on travels</span>
              ${body.map((line) => html`<p class="notice-body">${line}</p>`)}
            </div>
          </div>
        `;
      }
      case "empty-day":
        return html`
          ${this._renderHeader(view)}
          <div class="notice-wrap">
            <div class="notice" role="status">
              ${ICON_SUN}
              <span class="notice-headline">No quests today</span>
              <p class="notice-body">
                ${`Nothing was posted for today, ${view.name}. Enjoy the day's rest!`}
              </p>
            </div>
          </div>
        `;
      case "complete-day": {
        const stats = this._completeStats();
        const remaining = this._countdown ?? this._completeSeconds();
        return html`
          <div class="complete-screen" role="status">
            <span class="complete-seal" aria-hidden="true">${ICON_CHECK}</span>
            <h1 class="complete-title">Quest complete</h1>
            <p class="complete-sub">${this._completeSub(view.name)}</p>
            <p class="complete-countdown">
              Returning to The Party in ${remaining} seconds
            </p>
            <div class="complete-stats">
              <div class="complete-stat">
                <span class="numeral">${stats.claimed}</span>
                <span class="label">Quests claimed</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${stats.onTime}</span>
                <span class="label">On time</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${stats.late}</span>
                <span class="label">Late</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${stats.party}</span>
                <span class="label">The Party</span>
              </div>
            </div>
          </div>
          ${this._renderDock()}
        `;
      }
      default:
        return html`
          ${this._renderHeader(view)}
          <div class="columns">
            ${WINDOW_DEFS.map((windowDef) => this._renderColumn(windowDef))}
          </div>
        `;
    }
  }

  /** Resolve the log's single render state; the priority order is
   *  design/PANEL-EMPTY-STATES.md §2. */
  private _logView(): LogView {
    const slug = this._childSlug();
    if (!slug) {
      return { kind: "no-adventurer" };
    }
    const resolution = this._dueSensorResolution(slug);
    if (resolution === "missing") {
      return { kind: "not-set-up" };
    }
    if (resolution === "stale") {
      return { kind: "unreachable" };
    }
    const name = this._childName(slug) ?? titleCaseSlug(slug);
    if (!this._childPresent(slug)) {
      return { kind: "away", name, returns: this._awayReturns(slug) };
    }
    const allDone = this._state(`binary_sensor.nestquest_${slug}_all_done`);
    if (allDone && String(allDone.state ?? "").trim().toLowerCase() === "on") {
      return { kind: "complete-day", name };
    }
    const dueSensor = this._state(`sensor.nestquest_${slug}_quests_due_today`);
    const due = clampCount(asNumber(dueSensor?.state, 0));
    if (due === 0) {
      return { kind: "empty-day", name };
    }
    if (this._remaining() === 0) {
      return { kind: "complete-day", name };
    }
    return { kind: "normal" };
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

  private _childPresent(slug: string): boolean {
    const dueSensor = this._state(`sensor.nestquest_${slug}_quests_due_today`);
    const presentAttr = dueSensor?.attributes?.present;
    if (typeof presentAttr === "boolean") {
      return presentAttr;
    }
    const presence = this._state(
      `binary_sensor.nestquest_${slug}_present_today`
    );
    if (presence) {
      return String(presence.state ?? "").trim().toLowerCase() === "on";
    }
    return true;
  }

  private _awayReturns(slug: string): string | null {
    const timeZone = this._timeZone();
    const presence = this._state(
      `binary_sensor.nestquest_${slug}_present_today`
    );
    const nextPresent = parseIsoDate(
      presence?.attributes?.next_present,
      timeZone
    );
    return nextPresent ? formatDay(nextPresent, timeZone) : null;
  }

  private _renderNotice(notice: LogNotice): TemplateResult {
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

  private _completeSeconds(): number {
    const seconds = asNumber(this._config?.complete_screen_seconds, 12);
    return seconds > 0 ? seconds : 12;
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
    const instances = payload
      .map(toPanelInstance)
      .filter((instance): instance is PanelInstance => instance !== null);
    if (this._optimistic.size === 0) {
      return instances;
    }
    let settled = false;
    for (const instance of instances) {
      const stampedAt = this._optimistic.get(instance.id);
      if (stampedAt === undefined) {
        continue;
      }
      if (instance.state === "completed") {
        // the backend has caught up; the real record replaces the overlay
        this._optimistic.delete(instance.id);
        settled = true;
        continue;
      }
      instance.state = "completed";
      instance.overdue = false;
      instance.completed_at = stampedAt;
    }
    if (settled) {
      this._optimistic = new Map(this._optimistic);
    }
    return instances;
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

  private _completeStats(): {
    claimed: number;
    onTime: number;
    late: number;
    party: string;
  } {
    const claimed = this._childCounts(this._childSlug()).completed;
    const onTime = this._instances().filter(
      (instance) => instance.on_time === true
    ).length;
    const late = clampCount(claimed - onTime);
    const party = this._partyCounts();
    return {
      claimed,
      onTime,
      late,
      party: `${party.completed}/${party.due}`,
    };
  }

  private _completeSub(name: string): string {
    const date = formatDay(this._now, this._timeZone());
    const { claimed, onTime, late } = this._completeStats();
    if (claimed === 0) {
      return `${name} sealed the day on ${date}.`;
    }
    if (late === 0) {
      return `${name} claimed every quest on ${date} — all on time.`;
    }
    if (onTime === 0) {
      return `${name} claimed every quest on ${date} — all late.`;
    }
    return `${name} claimed every quest on ${date} — ${onTime} on time, ${late} late.`;
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

  private _renderHeader(view: LogView) {
    const slug = this._childSlug();
    const away = view.kind === "away";
    const name = away
      ? view.name
      : (this._childName(slug) ?? (slug ? titleCaseSlug(slug) : null));
    const { due, completed } = this._childCounts(slug);
    const remaining = this._remaining();
    const party = this._partyCounts();
    const title = name ? `${name}'s Quest Log` : "Quest Log";
    const initial = (name?.charAt(0) || "?").toUpperCase();
    return html`
      <header class="header">
        <span class="crest${away ? " away" : nothing}" aria-hidden="true">
          <span class="crest-face">
            <span class="initial">${initial}</span>
          </span>
        </span>
        <div class="titles">
          <h1 class="title">${title}</h1>
          <p class="sub">
            ${formatDay(this._now, this._timeZone())} ·
            ${away ? "On travels" : `${completed} of ${due} claimed`}
          </p>
        </div>
        ${away
          ? nothing
          : html`
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
            `}
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
        Math.max(58, Math.floor((available - (count - 1) * gap) / count))
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
    const instance =
      this._confirm === null
        ? undefined
        : this._instances().find(
            (candidate) => candidate.id === this._confirm
          );
    this._closeConfirm();
    if (!instance || instance.state !== "open") {
      return;
    }
    this._completeQuest(instance);
  }

  /** Seal first, ask the service second: the seal is stamped and the column
   *  re-sorted immediately (PANEL-SPEC §4); a service failure reverts the
   *  card and raises the parchment toast. */
  private async _completeQuest(instance: PanelInstance): Promise<void> {
    if (this._optimistic.has(instance.id)) {
      return;
    }
    const stampedAt = new Date().toISOString();
    this._optimistic = new Map(this._optimistic).set(instance.id, stampedAt);
    try {
      await this._callCompleteQuest(instance);
    } catch {
      const reverted = new Map(this._optimistic);
      reverted.delete(instance.id);
      this._optimistic = reverted;
      this._showToast(
        "NestQuest could not set the seal just now. Please try again."
      );
    }
  }

  private async _callCompleteQuest(instance: PanelInstance): Promise<void> {
    const hass = this.hass as
      | {
          callService?: (
            this: unknown,
            domain: string,
            service: string,
            data?: Record<string, unknown>
          ) => Promise<unknown>;
        }
      | undefined;
    if (typeof hass?.callService !== "function") {
      throw new Error("Home Assistant is not connected");
    }
    const actorChildId = this._actorChildId(instance);
    if (actorChildId === null) {
      throw new Error("The tapped adventurer is unknown");
    }
    await hass.callService.call(hass, "nestquest", "complete_quest", {
      instance_id: instance.id,
      actor: "panel",
      actor_child_id: actorChildId,
    });
  }

  /** The tapped profile (decision 9): the instance's own child_id, falling
   *  back to the due sensor's child-level attribute. */
  private _actorChildId(instance: PanelInstance): number | null {
    if (instance.child_id !== null) {
      return instance.child_id;
    }
    const slug = this._childSlug();
    const fromSensor = asNumber(
      this._state(`sensor.nestquest_${slug}_quests_due_today`)?.attributes
        ?.child_id,
      0
    );
    return fromSensor > 0 ? fromSensor : null;
  }

  private _showToast(message: string): void {
    this._toast = message;
    this._clearToastTimer();
    this._toastTimer = window.setTimeout(() => {
      this._toastTimer = undefined;
      this._toast = null;
    }, 6000);
  }

  private _clearToastTimer(): void {
    if (this._toastTimer !== undefined) {
      window.clearTimeout(this._toastTimer);
      this._toastTimer = undefined;
    }
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

  private _armCompleteTimer(): void {
    if (this._completeTimer !== undefined) {
      return;
    }
    if (this._countdown === null) {
      this._countdown = this._completeSeconds();
    }
    if (this._countdown <= 0) {
      this._returnToBoard();
      return;
    }
    this._completeTimer = window.setInterval(() => {
      const remaining = (this._countdown ?? 1) - 1;
      if (remaining <= 0) {
        this._countdown = 0;
        this._clearCompleteTimer();
        this._returnToBoard();
        return;
      }
      this._countdown = remaining;
    }, 1000);
  }

  private _clearCompleteTimer(): void {
    if (this._completeTimer !== undefined) {
      window.clearInterval(this._completeTimer);
      this._completeTimer = undefined;
    }
  }

  private _optionalNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === "") {
      return null;
    }
    const parsed = typeof value === "number" ? value : Number(value);
    return Number.isFinite(parsed) ? parsed : null;
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
        ${ICON_CLOUD_MOON}
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
    if (this._logView().kind !== "complete-day") {
      this._armIdle();
    }
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
