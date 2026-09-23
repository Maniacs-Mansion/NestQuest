/**
 * Render the built quest-log card under jsdom and report its location.
 *
 * Usage: node render-quest-log.mjs < spec.json
 *
 * The spec JSON carries {bundle, url, config, hass, idle_ms?, probe_ms?};
 * the card is mounted at the given URL (it resolves its child from the
 * pathname's last segment), after the optional probe wait one snapshot of
 * the render is taken mid-wait, then after the optional idle wait stdout
 * receives one JSON object {location, headline, countdown, html, probe} —
 * the final window pathname, the rendered title, the complete-screen
 * countdown text, the rendered shadow DOM, and the probe snapshot when
 * probe_ms was given. The Python panel tests drive this harness so the
 * assertions run against the exact bundle HACS ships.
 */
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const spec = JSON.parse(readFileSync(0, "utf8"));

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: spec.url ?? "http://homeassistant.local/nestquest/ada",
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
// The card navigates by dispatching new Event("location-changed") on this
// window; jsdom's EventTarget rejects Node's own global Event class, so the
// jsdom Event must shadow it for the return navigation to be delivered.
globalThis.Event = dom.window.Event;

await import(pathToFileURL(spec.bundle).href);

const element = document.createElement("nestquest-quest-log-card");
element.setConfig(spec.config);
element.hass = spec.hass;
document.body.appendChild(element);
await element.updateComplete;

const snapshot = () => ({
  location: window.location.pathname,
  headline: element.shadowRoot.querySelector(".title")?.textContent?.trim() ?? "",
  countdown:
    element.shadowRoot.querySelector(".complete-countdown")?.textContent?.trim() ??
    "",
  html: element.shadowRoot.innerHTML,
});

let probe = null;
if (spec.probe_ms !== undefined) {
  await new Promise((resolve) => setTimeout(resolve, spec.probe_ms));
  probe = snapshot();
}

if (spec.idle_ms !== undefined) {
  await new Promise((resolve) => setTimeout(resolve, spec.idle_ms));
}

const payload = JSON.stringify({ ...snapshot(), probe });
await new Promise((resolve) => process.stdout.write(payload, () => resolve()));
process.exit(0);