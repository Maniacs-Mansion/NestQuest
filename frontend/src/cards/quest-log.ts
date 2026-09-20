import { LitElement, html } from "lit";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

export class NestQuestQuestLogCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };

  hass?: HassLike;
  _config?: CardConfig;

  setConfig(config: CardConfig): void {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid configuration");
    }
    this._config = config;
  }

  getCardSize(): number {
    return 8;
  }

  render() {
    return html`<div>NestQuest Quest Log</div>`;
  }
}

customElements.define("nestquest-quest-log-card", NestQuestQuestLogCard);
registerCustomCard({
  type: "nestquest-quest-log-card",
  name: "NestQuest Quest Log",
  description: "One child's daily quests, grouped by window.",
});
