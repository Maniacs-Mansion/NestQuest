/**
 * Import the built bundle into jsdom and generate the dashboard strategy's
 * views.
 *
 * Usage: node render-strategy.mjs < spec.json
 *
 * The spec JSON carries {bundle, url, config, hass}; stdout receives one
 * JSON object {views} — the strategy output's views array with the paths
 * and card configs the generated dashboard renders.  The Python panel
 * tests drive this harness so the assertions run against the exact bundle
 * HACS ships.
 */
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const spec = JSON.parse(readFileSync(0, "utf8"));

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: spec.url ?? "http://homeassistant.local/nestquest/party",
  pretendToBeVisual: true,
});

// Expose the jsdom globals the Lit bundle expects. Node's own intrinsics
// (Object, Array, ...) are kept — only what globalThis lacks is copied.
for (const key of Object.getOwnPropertyNames(dom.window)) {
  if (!(key in globalThis)) {
    try {
      globalThis[key] = dom.window[key];
    } catch {
      // jsdom getters may throw on access; the strategy does not need them.
    }
  }
}
globalThis.window = dom.window;

await import(pathToFileURL(spec.bundle).href);

const strategy = window.customStrategies?.["nestquest-party"];
if (!strategy) {
  console.error("nestquest-party strategy is not registered on the bundle");
  process.exit(1);
}

const lovelace = await strategy.generate(spec.config, spec.hass);
const payload = JSON.stringify({ views: lovelace.views });
await new Promise((resolve) => process.stdout.write(payload, () => resolve()));
process.exit(0);
