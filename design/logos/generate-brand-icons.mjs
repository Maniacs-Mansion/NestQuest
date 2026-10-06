// Generates the integration's local brand images in
// custom_components/nestquest/brand/ (read by Home Assistant 2026.3+) from the
// transparent logo (design/logos/NestQuest-NoBG.png), box-filter downscaled
// with alpha kept. Adapted from admin/scripts/generate-icons.mjs for RGBA.
// Pure Node (zlib only) — no network, no image dependencies.
// Run (from the repository root):
//   node design/logos/generate-brand-icons.mjs          # write the PNGs
//   node design/logos/generate-brand-icons.mjs --check  # exit 1 if any drifted
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
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

function encodePng(size, rgba) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // colour type: RGBA
  const stride = size * 4;
  const raw = Buffer.alloc(size * (stride + 1));
  for (let y = 0; y < size; y++) {
    raw[y * (stride + 1)] = 0; // filter: none
    raw.set(rgba.subarray(y * stride, (y + 1) * stride), y * (stride + 1) + 1);
  }
  return Buffer.concat([
    SIG,
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// Minimal decoder for the source logo: 8-bit RGBA, non-interlaced only.
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
      if (depth !== 8 || colour !== 6 || interlace !== 0) {
        throw new Error(`unsupported PNG: depth ${depth}, colour type ${colour}, interlace ${interlace}`);
      }
    } else if (type === "IDAT") idat.push(data);
    else if (type === "IEND") break;
    off += 12 + len;
  }
  const raw = inflateSync(Buffer.concat(idat));
  const stride = width * 4;
  const px = Buffer.alloc(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = y * (stride + 1) + 1;
    const dst = y * stride;
    for (let i = 0; i < stride; i++) {
      const a = i >= 4 ? px[dst + i - 4] : 0;
      const b = y > 0 ? px[dst - stride + i] : 0;
      const c = i >= 4 && y > 0 ? px[dst - stride + i - 4] : 0;
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
  if (width !== height) throw new Error(`logo must be square, got ${width}x${height}`);
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

// Colour is averaged premultiplied by alpha, so fully transparent source
// pixels (whatever RGB they carry) cannot bleed a fringe into the edges.
function resize({ width, height, px }, size) {
  const wx = boxWeights(width, size);
  const wy = boxWeights(height, size);
  const tmp = new Float64Array(size * height * 4); // horizontal pass, premultiplied
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < size; x++) {
      const t = (y * size + x) * 4;
      for (const [s, w] of wx[x]) {
        const p = (y * width + s) * 4;
        const aw = px[p + 3] * w;
        for (let k = 0; k < 3; k++) tmp[t + k] += px[p + k] * aw;
        tmp[t + 3] += aw;
      }
    }
  }
  const out = new Uint8Array(size * size * 4); // vertical pass, un-premultiply
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const acc = [0, 0, 0, 0];
      for (const [s, w] of wy[y]) {
        const t = (s * size + x) * 4;
        for (let k = 0; k < 4; k++) acc[k] += tmp[t + k] * w;
      }
      const o = (y * size + x) * 4;
      const alpha = Math.min(255, Math.round(acc[3]));
      for (let k = 0; k < 3; k++) {
        out[o + k] = alpha === 0 ? 0 : Math.min(255, Math.round(acc[k] / acc[3]));
      }
      out[o + 3] = alpha;
    }
  }
  return out;
}

const logo = decodePng(readFileSync(new URL("NestQuest-NoBG.png", import.meta.url)));
const outDir = new URL("../../custom_components/nestquest/brand/", import.meta.url);
const files = [
  ["icon.png", 256],
  ["icon@2x.png", 512],
  ["logo.png", 256],
  ["logo@2x.png", 512],
];
const check = process.argv.includes("--check");
let drifted = false;
if (!check) mkdirSync(outDir, { recursive: true });
for (const [name, size] of files) {
  const path = fileURLToPath(new URL(name, outDir));
  const png = encodePng(size, resize(logo, size));
  if (check) {
    let current = null;
    try {
      current = readFileSync(path);
    } catch {
      // missing counts as drift
    }
    if (!current || !current.equals(png)) {
      drifted = true;
      console.error(`drift: ${path} differs from a fresh generation`);
    }
  } else {
    writeFileSync(path, png);
    console.log(`wrote ${path}`);
  }
}
if (drifted) {
  console.error("run `node design/logos/generate-brand-icons.mjs` and commit the result");
  process.exit(1);
}
