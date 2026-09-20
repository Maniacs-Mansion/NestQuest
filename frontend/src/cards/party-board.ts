import { LitElement, html, unsafeCSS } from "lit";
import panelTokens from "../../../custom_components/nestquest/www/nestquest-panel-tokens.css?inline";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

export class NestQuestPartyBoardCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };

  static styles = [unsafeCSS(panelTokens)];

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
