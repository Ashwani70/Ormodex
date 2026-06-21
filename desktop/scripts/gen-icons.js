// Generates the platform icons electron-builder needs from build-resources/icon.svg:
//   • icon.png  (1024×1024) — Linux + electron-builder's macOS .icns source
//   • icon.ico  (multi-size) — Windows
//
// macOS .icns is produced by electron-builder itself from icon.png at build time,
// so we don't need iconutil here.
//
// Requires `sharp` and `png-to-ico` (installed on demand by the release workflow,
// or `npm i -D sharp png-to-ico` locally). Run:  node scripts/gen-icons.js

const fs = require("fs");
const path = require("path");

const RES = path.resolve(__dirname, "..", "build-resources");
const SVG = path.join(RES, "icon.svg");
const PNG = path.join(RES, "icon.png");
const ICO = path.join(RES, "icon.ico");

async function main() {
  const sharp = require("sharp");
  // png-to-ico exports the function as a default; handle both CJS shapes.
  const pngToIcoMod = require("png-to-ico");
  const pngToIco = pngToIcoMod.default || pngToIcoMod;

  const svg = fs.readFileSync(SVG);

  // 1024px master PNG (Linux icon + macOS icns source).
  await sharp(svg, { density: 384 }).resize(1024, 1024).png().toFile(PNG);
  console.log("✓ icon.png");

  // Multi-resolution .ico for Windows.
  const sizes = [16, 24, 32, 48, 64, 128, 256];
  const buffers = await Promise.all(
    sizes.map((s) => sharp(svg, { density: 384 }).resize(s, s).png().toBuffer())
  );
  fs.writeFileSync(ICO, await pngToIco(buffers));
  console.log("✓ icon.ico");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
