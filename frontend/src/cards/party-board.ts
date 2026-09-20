import { LitElement, html } from "lit";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

export class NestQuestPartyBoardCard extends LitElement {
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
    return 6;
  }

  render() {
    return html`<div>NestQuest Party Board</div>`;
  }
}

customElements.define("nestquest-party-board-card", NestQuestPartyBoardCard);
registerCustomCard({
  type: "nestquest-party-board-card",
  name: "NestQuest Party Board",
  description: "Kids' attract screen for present and away adventurers.",
});
