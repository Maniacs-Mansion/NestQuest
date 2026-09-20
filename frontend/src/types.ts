export type HassLike = Record<string, unknown>;

export type CardConfig = Record<string, unknown>;

export type CustomCardInfo = {
  type: string;
  name: string;
  description: string;
};

declare global {
  interface Window {
    customCards?: CustomCardInfo[];
  }
}

export function registerCustomCard(info: CustomCardInfo): void {
  window.customCards = window.customCards ?? [];
  window.customCards.push(info);
}
