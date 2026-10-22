// Lists the logos saved in public/logos/ into public/logos/manifest.json, which the app reads to
// show them before falling back to Brandfetch. Name each file after the symbol as it appears in
// the app (AXISBANK.png; BSE:FOCUS -> BSE_FOCUS.png). Run after adding logos:
//   node scripts/logo-manifest.mjs
import { readdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const LOGO_DIR = new URL('../public/logos/', import.meta.url);

export function writeManifest() {
  const files = readdirSync(LOGO_DIR).filter((f) => /\.(png|webp|svg|jpe?g)$/i.test(f)).sort();
  const manifest = Object.fromEntries(
    files.map((f) => [f.replace(/\.[^.]+$/, '').toUpperCase().replace(/^BSE_/, 'BSE:'), f]),
  );
  writeFileSync(new URL('manifest.json', LOGO_DIR), JSON.stringify(manifest, null, 1) + '\n');
  return files.length;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  console.log(`${writeManifest()} logos listed in public/logos/manifest.json`);
}
