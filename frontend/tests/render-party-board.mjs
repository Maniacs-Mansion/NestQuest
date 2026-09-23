/**
 * Render the built party-board card under jsdom and print its plates.
 *
 * Usage: node render-party-board.mjs < spec.json
 *
 * The spec JSON carries {bundle, tag, config, hass}; stdout receives one JSON
 * object {plates, html} where plates is the ordered plate list the shadow DOM
 * renders (name + present/away/unknown kind). The Python panel tests drive
 * this harness so the assertions run against the exact bundle HACS ships.
 */
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const spec = JSON.parse(readFileSync(0, "utf8"));

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://homeassistant.local/nestquest/board",
  pretendToBeVisual: true,
});

// Expose the jsdom globals the Lit bundle expects. Node's own intrinsics
// (Object, Array, ...) are kept — only what globalThis lacks is copied.
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (!(key in globalThis)) {
    try {
      globalThis[key] = dom.window[key];
    } catch {
      // jsdom getters may throw on access; the card does not need them.
    }
  }
}
globalThis.window = dom.window;

await import(pathToFileURL(spec.bundle).href);

const element = document.createElement(spec.tag);
element.setConfig(spec.config);
element.hass = spec.hass;
document.body.appendChild(element);
await element.updateComplete;

const plates = [
  ...element.shadowRoot.querySelectorAll(".plates .plate"),
].map((plate) => ({
  name: plate.querySelector(".name")?.textContent?.trim() ?? "",
  kind: plate.classList.contains("unknown")
    ? "unknown"
    : plate.classList.contains("away")
      ? "away"
      : "present",
}));

const payload = JSON.stringify({ plates, html: element.shadowRoot.innerHTML });
await new Promise((resolve) => process.stdout.write(payload, () => resolve()));
process.exit(0);
