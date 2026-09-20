import { LitElement, html, unsafeCSS } from "lit";
import adminTokens from "../../../custom_components/nestquest/www/nestquest-admin-tokens.css?inline";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

export class NestQuestAdminCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
  };

  static styles = [unsafeCSS(adminTokens)];

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
    return html`<div>NestQuest Admin</div>`;
  }
}

customElements.define("nestquest-admin-card", NestQuestAdminCard);
registerCustomCard({
  type: "nestquest-admin-card",
  name: "NestQuest Admin",
  description: "Parent phone view for today, tasks, schedule, and history.",
});
