// Generates the committed PWA icons under public/icons/ from the brand logo
// (design/logos/NestQuest_Logo.png), box-filter downscaled.
// Pure Node (zlib only) — no network, no image dependencies.
// Run: node scripts/generate-icons.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { deflateSync, inflateSync } from "node:zlib";
import { fileURLToPath } from "node:url";

const SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

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
    SIG,
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// Minimal decoder for the source logo: 8-bit RGB, non-interlaced only.
// Anything else fails loudly rather than producing a wrong icon.
function decodePng(buf) {
  if (!buf.subarray(0, 8).equals(SIG)) throw new Error("not a PNG");
  let width, height;
  const idat = [];
  for (let off = 8; off < buf.length; ) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString("ascii", off + 4, off + 8);
    const data = buf.subarray(off + 8, off + 8 + len);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      const [depth, colour, , , interlace] = data.subarray(8);
      if (depth !== 8 || colour !== 2 || interlace !== 0) {
        throw new Error(`unsupported PNG: depth ${depth}, colour type ${colour}, interlace ${interlace}`);
      }
    } else if (type === "IDAT") idat.push(data);
    else if (type === "IEND") break;
    off += 12 + len;
  }
  const raw = inflateSync(Buffer.concat(idat));
  const stride = width * 3;
  const px = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = y * (stride + 1) + 1;
    const dst = y * stride;
    for (let i = 0; i < stride; i++) {
      const a = i >= 3 ? px[dst + i - 3] : 0;
      const b = y > 0 ? px[dst - stride + i] : 0;
      const c = i >= 3 && y > 0 ? px[dst - stride + i - 3] : 0;
      let p;
      if (filter === 0) p = 0;
      else if (filter === 1) p = a;
      else if (filter === 2) p = b;
      else if (filter === 3) p = (a + b) >> 1;
      else if (filter === 4) {
        const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c);
        p = pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      } else throw new Error(`bad PNG filter ${filter} on row ${y}`);
      px[dst + i] = (raw[src + i] + p) & 0xff;
    }
  }
  return { width, height, px };
}

// Box-filter (area-average) resize along one axis: each output sample is the
// coverage-weighted mean of the source samples it spans.
function boxWeights(srcLen, dstLen) {
  const scale = srcLen / dstLen;
  return Array.from({ length: dstLen }, (_, o) => {
    const start = o * scale, end = start + scale;
    const taps = [];
    for (let s = Math.floor(start); s < Math.min(Math.ceil(end), srcLen); s++) {
      taps.push([s, (Math.min(end, s + 1) - Math.max(start, s)) / scale]);
    }
    return taps;
  });
}

function resize({ width, height, px }, size) {
  const wx = boxWeights(width, size);
  const wy = boxWeights(height, size);
  const tmp = new Float64Array(size * height * 3); // horizontal pass
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < size; x++) {
      for (const [s, w] of wx[x]) {
        for (let k = 0; k < 3; k++) tmp[(y * size + x) * 3 + k] += px[(y * width + s) * 3 + k] * w;
      }
    }
  }
  const out = new Uint8Array(size * size * 3); // vertical pass
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      for (let k = 0; k < 3; k++) {
        let v = 0;
        for (const [s, w] of wy[y]) v += tmp[(s * size + x) * 3 + k] * w;
        out[(y * size + x) * 3 + k] = Math.min(255, Math.round(v));
      }
    }
  }
  return (x, y) => out.subarray((y * size + x) * 3, (y * size + x) * 3 + 3);
}

// Mean of the four corner pixels — the logo's solid background colour.
function cornerColour({ width, height, px }) {
  const corners = [[0, 0], [width - 1, 0], [0, height - 1], [width - 1, height - 1]];
  return [0, 1, 2].map((k) =>
    Math.round(corners.reduce((sum, [x, y]) => sum + px[(y * width + x) * 3 + k], 0) / 4),
  );
}

// `scale` < 1 shrinks the logo onto a background-coloured canvas so a
// maskable icon keeps the whole emblem inside the safe zone (inner 80% circle).
function logoIcon(logo, size, scale) {
  if (scale === 1) return resize(logo, size);
  const inner = Math.round(size * scale);
  const offset = Math.floor((size - inner) / 2);
  const pixel = resize(logo, inner);
  const bg = cornerColour(logo);
  return (x, y) => {
    const ix = x - offset, iy = y - offset;
    return ix >= 0 && iy >= 0 && ix < inner && iy < inner ? pixel(ix, iy) : bg;
  };
}

const logo = decodePng(readFileSync(new URL("../../design/logos/NestQuest_Logo.png", import.meta.url)));
const outDir = new URL("../public/icons/", import.meta.url);
const icons = [
  ["icon-192.png", 192, 1],
  ["icon-512.png", 512, 1],
  ["icon-maskable-512.png", 512, 0.8],
];
for (const [name, size, scale] of icons) {
  const path = fileURLToPath(new URL(name, outDir));
  writeFileSync(path, encodePng(size, logoIcon(logo, size, scale)));
  console.log(`wrote ${path}`);
}
