/**
 * Render the built quest-log card under jsdom and report its location.
 *
 * Usage: node render-quest-log.mjs < spec.json
 *
 * The spec JSON carries {bundle, url, config, hass, idle_ms?}; the card is
 * mounted at the given URL (it resolves its child from the pathname's last
 * segment), and after the optional idle wait stdout receives one JSON object
 * {location, headline, html} — the window pathname and the rendered title.
 * The Python panel tests drive this harness so the assertions run against
 * the exact bundle HACS ships.
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

if (spec.idle_ms !== undefined) {
  await new Promise((resolve) => setTimeout(resolve, spec.idle_ms));
}

const payload = JSON.stringify({
  location: window.location.pathname,
  headline: element.shadowRoot.querySelector(".title")?.textContent?.trim() ?? "",
  html: element.shadowRoot.innerHTML,
});
await new Promise((resolve) => process.stdout.write(payload, () => resolve()));
process.exit(0);