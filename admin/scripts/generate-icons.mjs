// Generates the committed PWA icons under public/icons/ as genuine PNGs.
// Pure Node (zlib only) — no network, no image dependencies.
// Run: node scripts/generate-icons.mjs
import { writeFileSync } from "node:fs";
import { deflateSync } from "node:zlib";
import { fileURLToPath } from "node:url";

// Brand tokens (design/tokens/nestquest-admin-tokens.css).
const BLUE = [0x3b, 0x3a, 0xb8];
const PURPLE = [0xa0, 0x35, 0xcc];
const WHITE = [0xff, 0xff, 0xff];

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function encodePng(size, pixel) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // colour type: RGB
  const raw = Buffer.alloc(size * (size * 3 + 1));
  for (let y = 0; y < size; y++) {
    const row = y * (size * 3 + 1);
    raw[row] = 0; // filter: none
    for (let x = 0; x < size; x++) raw.set(pixel(x, y), row + 1 + x * 3);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// Flat brand mark: diagonal blue→purple gradient with a white ring ("nest")
// around a white dot ("quest"). `scale` shrinks the mark for the maskable
// safe zone (inner 80% circle).
function brandMark(size, scale) {
  const c = size / 2;
  const outer = size * 0.34 * scale;
  const inner = size * 0.24 * scale;
  const dot = size * 0.1 * scale;
  return (x, y) => {
    const d = Math.hypot(x + 0.5 - c, y + 0.5 - c);
    if ((d <= outer && d >= inner) || d <= dot) return WHITE;
    const t = (x + y) / (2 * (size - 1));
    return BLUE.map((b, i) => Math.round(b + (PURPLE[i] - b) * t));
  };
}

const outDir = new URL("../public/icons/", import.meta.url);
const icons = [
  ["icon-192.png", 192, 1],
  ["icon-512.png", 512, 1],
  ["icon-maskable-512.png", 512, 0.75],
];
for (const [name, size, scale] of icons) {
  const path = fileURLToPath(new URL(name, outDir));
  writeFileSync(path, encodePng(size, brandMark(size, scale)));
  console.log(`wrote ${path}`);
}
