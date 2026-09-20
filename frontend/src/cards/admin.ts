import { LitElement, html } from "lit";

import { registerCustomCard, type CardConfig, type HassLike } from "../types";

export class NestQuestAdminCard extends LitElement {
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
    return html`<div>NestQuest Admin</div>`;
  }
}

customElements.define("nestquest-admin-card", NestQuestAdminCard);
registerCustomCard({
  type: "nestquest-admin-card",
  name: "NestQuest Admin",
  description: "Parent phone view for today, tasks, schedule, and history.",
});
