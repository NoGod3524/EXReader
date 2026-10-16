import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
await mkdir('public/licenses', { recursive: true });
await writeFile('public/licenses/EXREADER-GPL-3.0.txt', await readFile('LICENSE'));
const lock = JSON.parse(await readFile('package-lock.json', 'utf8'));
let js = '# JavaScript dependency licenses\n';
for (const [dir, entry] of Object.entries(lock.packages)) {
  if (!dir || entry.dev || entry.optional && !dir.includes('pdfjs-dist')) continue;
  let names; try { names = await readdir(dir); } catch { continue; }
  const licenses = names.filter(n => /^(licen[cs]e|copying|notice)([.-]|$)/i.test(n));
  js += `\n\n===== ${dir.replace(/^node_modules\//, '')} ${entry.version} (${entry.license || 'see below'}) =====\n`;
  for (const name of licenses) { try { js += `\n${name}\n${await readFile(`${dir}/${name}`, 'utf8')}\n`; } catch {} }
}
await writeFile('public/licenses/JAVASCRIPT-LICENSES.txt', js);
await writeFile('public/licenses/FOLIATE-LICENSE.txt', await readFile('vendor/foliate/LICENSE'));
let fonts = '# PDF CMaps and standard font licenses\n';
for (const dir of ['cmaps', 'standard_fonts']) for (const filename of (await readdir(`public/pdf-assets/${dir}`)).filter(f => /^LICENSE/.test(f))) {
  fonts += `\n\n===== ${dir}/${filename} =====\n${await readFile(`public/pdf-assets/${dir}/${filename}`, 'utf8')}\n`;
}
await writeFile('public/licenses/PDF-FONT-LICENSES.txt', fonts);
const root = path.join(process.env.CARGO_HOME || path.join(homedir(), '.cargo'), 'registry', 'src');
try {
  let cargo = await readFile('integrations/calibre/Cargo.lock', 'utf8');
  try { cargo += '\n' + await readFile('src-tauri/Cargo.lock', 'utf8'); } catch { /* The framework has no application shell. */ }
  const registries = await readdir(root);
  let rust = '# Rust dependency licenses (includes build and target-specific crates)\n';
  for (const block of cargo.split('[[package]]').slice(1)) {
    const name = block.match(/\nname = "([^"]+)"/)?.[1], version = block.match(/\nversion = "([^"]+)"/)?.[1];
    if (!name || !version) continue;
    for (const registry of registries) {
      const dir = path.join(root, registry, `${name}-${version}`);
      let files; try { files = await readdir(dir); } catch { continue; }
      const manifest = await readFile(path.join(dir, 'Cargo.toml'), 'utf8');
      rust += `\n\n===== ${name} ${version} (${manifest.match(/\nlicense = "([^"]+)"/)?.[1] || 'see upstream'}) =====\n`;
      for (const filename of files.filter(f => /^(licen[cs]e|copying|notice)([.-]|$)/i.test(f))) {
        try { rust += `\n${filename}\n${await readFile(path.join(dir, filename), 'utf8')}\n`; } catch {}
      }
      break;
    }
  }
  await writeFile('public/licenses/RUST-LICENSES.txt', rust);
} catch { /* Web-only builds do not need a Rust toolchain or crate cache. */ }
