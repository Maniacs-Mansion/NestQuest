import type { HassLike } from "./types";

type StateObject = {
  state: unknown;
  attributes?: Record<string, unknown> | null;
};

type RosterEntry = {
  slug: string;
};

type View = {
  path?: string;
  title?: string;
  cards: Record<string, unknown>[];
};

type LovelaceConfig = {
  views: View[];
};

type StrategyConfig = Record<string, unknown>;

type StrategyClass = {
  new (): unknown;
  generate: (
    config: StrategyConfig,
    hass: HassLike | undefined
  ) => Promise<LovelaceConfig>;
};

declare global {
  interface Window {
    customStrategies?: Record<string, StrategyClass>;
  }
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** The slug a discovered roster entry carries, or "" when the entry is
 *  not an object with a non-empty slug string — the same shape check
 *  the party board applies to the same attribute. */
function asRosterSlug(entry: unknown): string {
  if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
    return "";
  }
  const slug = (entry as Record<string, unknown>).slug;
  return typeof slug === "string" ? slug.trim() : "";
}

/** The dashboard's URL path segment, used to COMPUTE the card paths the
 *  navigation needs.  A dashboard lives at a single top-level segment
 *  (/<url_path>), so the first pathname segment is the dashboard root —
 *  this is where the strategy renders, and navigating back to it shows
 *  the first view (the party board).  An explicit ``url_path`` in the
 *  strategy configuration wins for setups that need to pin it. */
function dashboardUrlPath(config: StrategyConfig): string {
  const configured = asString(config.url_path).replace(/^\/+|\/+$/g, "");
  if (configured) {
    return configured;
  }
  const segment = window.location.pathname.split("/").filter(Boolean)[0];
  return segment ?? "";
}

/** The ordered child roster the integration publishes on the household
 *  rollup (custom_components/nestquest/sensor.py — ``child_roster``,
 *  the snapshot's sort_order, then id).  The same source the party
 *  board's plate discovery reads, consumed here at render time so the
 *  quest-log views exist for exactly the active children. */
function rosterSlugs(hass: HassLike | undefined): string[] {
  const states = hass?.states as Record<string, StateObject> | undefined;
  const household = states?.["sensor.nestquest_household_quests_due_today"];
  const roster = household?.attributes?.child_roster;
  if (!Array.isArray(roster)) {
    return [];
  }
  return roster
    .map((entry) => asRosterSlug(entry))
    .filter((slug) => slug.length > 0);
}

/**
 * Zero-config NestQuest dashboard strategy (Feature 20).
 *
 * A dashboard configured with ``strategy: { type: custom:nestquest-party }``
 * gets its views GENERATED at render time from the household roster: one
 * party-board view (the dashboard root) and one quest-log view per child,
 * ordered by the roster's sort_order.  The paths the cards navigate by are
 * COMPUTED, not configured:
 *
 * - the board's ``quest_log_path`` is the dashboard root; tapping a crest
 *   pushes ``<root>/<slug>`` (party-board.ts ``_openQuestLog``);
 * - each log view's ``path`` IS the child's slug, so the log resolves its
 *   child from the last pathname segment (quest-log.ts
 *   ``childSlugFromPath``) and its ``board_path`` back to the dashboard
 *   root (quest-log.ts ``_returnToBoard``).
 *
 * With zero children the board view still renders — the board card shows
 * its own "not set up yet" notice for an empty roster, so no log views are
 * needed.  ``url_path`` and ``weather_entity`` may still be set explicitly
 * in the strategy configuration; everything else is derived.
 */
export class NestQuestPartyStrategy {
  static async generate(
    config: StrategyConfig,
    hass: HassLike | undefined
  ): Promise<LovelaceConfig> {
    const root = `/${dashboardUrlPath(config)}`;
    const weatherEntity = asString(config.weather_entity);
    const boardCard: Record<string, unknown> = {
      type: "custom:nestquest-party-board-card",
      quest_log_path: root,
    };
    if (weatherEntity) {
      boardCard.weather_entity = weatherEntity;
    }
    const logCard: Record<string, unknown> = {
      type: "custom:nestquest-quest-log-card",
      board_path: root,
    };
    if (weatherEntity) {
      logCard.weather_entity = weatherEntity;
    }
    return {
      views: [
        {
          path: "party",
          title: "The Party",
          cards: [boardCard],
        },
        ...rosterSlugs(hass).map<View>((slug) => ({
          path: slug,
          title: `${slug}'s Quest Log`,
          cards: [{ ...logCard }],
        })),
      ],
    };
  }
}

window.customStrategies = window.customStrategies ?? {};
window.customStrategies["nestquest-party"] = NestQuestPartyStrategy;
