// SPDX-License-Identifier: MIT
// Real-browser chain, step 1: create a version-1 IndexedDB "exreader" with the OLD application's own
// store/library modules, run the shipped exporter against it in the page and save the download.
// usage: node export_e2e.mjs <spec.json> <legacy-src-dir> <exporter.js> <out-dir>
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';

const [specPath, legacyDir, exporterPath, outDir] = process.argv.slice(2);
const require = createRequire(path.join(process.cwd(), 'noop.js'));
const { chromium } = require('playwright');
mkdirSync(outDir, { recursive: true });
const spec = JSON.parse(readFileSync(specPath, 'utf8'));
const sha = file => createHash('sha256').update(readFileSync(file)).digest('hex');

const server = createServer((req, res) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname === '/blank.html') { res.setHeader('content-type', 'text/html'); res.end('<!doctype html><title>legacy origin</title>'); return; }
  if (url.pathname.startsWith('/legacy/')) {
    const file = path.join(legacyDir, path.basename(url.pathname));
    if (existsSync(file)) { res.setHeader('content-type', 'text/javascript'); res.end(readFileSync(file)); return; }
  }
  res.statusCode = 404; res.end('not found');
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch();
const context = await browser.newContext({ acceptDownloads: true });
const page = await context.newPage();
page.on('console', m => console.log('[page]', m.text()));
await page.goto(`${origin}/blank.html`);

// 1. Build the legacy database exactly as the old app would: createStore().addBook + createLibrary APIs.
const built = await page.evaluate(async spec => {
  const { createStore } = await import('/legacy/store.js');
  const { createLibrary } = await import('/legacy/library.js');
  const storage = createStore('exreader');
  const library = createLibrary({ name: 'exreader', storage });
  const bytes = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  for (const b of spec.books) {
    const r = b.record;
    const file = new File([bytes(b.file_b64)], r.filename, { type: '', lastModified: r.modified });
    const book = { title: r.title, author: '', format: r.format, audio: !!r.audio, id: r.id, filename: r.filename, size: file.size, modified: r.modified, added: r.added, progress: 0, favorite: false, tags: [], status: 'unread' };
    await storage.addBook(book, file);
    const meta = {};
    for (const k of ['title', 'author', 'tags', 'favorite', 'status', 'cover']) if (k in r) meta[k] = r[k];
    await library.updateBook(r.id, meta);
    const progress = {};
    for (const k of ['progress', 'cfi', 'page', 'seconds']) if (k in r) progress[k] = r[k];
    if (Object.keys(progress).length) await library.saveProgress(r.id, progress);
  }
  for (const n of spec.notes) {
    const { bookId, created, ...data } = n;
    await library.saveNote(bookId, data);
  }
  await library.close();
  return true;
}, spec);

// 2. Snapshot the raw stores before and after the export to prove it is read-only.
const snapshot = () => page.evaluate(async () => {
  const db = await new Promise((res, rej) => { const r = indexedDB.open('exreader'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
  const get = (store, fn) => new Promise((res, rej) => { const q = db.transaction([store], 'readonly').objectStore(store)[fn](); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error); });
  const hex = async buf => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buf)), b => b.toString(16).padStart(2, '0')).join('');
  const books = await get('books', 'getAll'), notes = await get('notes', 'getAll'), keys = await get('files', 'getAllKeys');
  const files = {};
  for (const k of keys) {
    const rec = await new Promise((res, rej) => { const q = db.transaction(['files'], 'readonly').objectStore('files').get(k); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error); });
    files[k] = await hex(rec.bytes);
  }
  const out = { version: db.version, stores: Array.from(db.objectStoreNames), books: books.length, notes: notes.length, files: keys.length, digest: await hex(new TextEncoder().encode(JSON.stringify({ books, notes, files }))) };
  db.close();
  return out;
});
const before = await snapshot();

// 3. A missing database must fail without creating one.
await page.addScriptTag({ path: exporterPath });
const missing = await page.evaluate(async () => {
  try { await exrLegacyExport({ database: 'nope', download: false }); return { threw: false }; }
  catch (e) { return { threw: true, code: e.code, exists: (await indexedDB.databases()).some(d => d.name === 'nope') }; }
});

// 4. The real export, delivered as a browser download.
const [download] = await Promise.all([
  page.waitForEvent('download'),
  page.evaluate(() => exrLegacyExport({ filename: 'legacy.exrpack' }).then(r => { window.__summary = r.summary; })),
]);
const pack = path.join(outDir, 'legacy.exrpack');
await download.saveAs(pack);
const summary = await page.evaluate(() => window.__summary);
const after = await snapshot();
const info = {
  browser: browser.version(), user_agent: await page.evaluate(() => navigator.userAgent), origin, built, before, after,
  source_unchanged: before.digest === after.digest, missing_database: missing, export_summary: summary,
  pack: { path: 'legacy.exrpack', bytes: readFileSync(pack).length, sha256: sha(pack) }, exporter_sha256: sha(exporterPath),
  legacy_sources: Object.fromEntries(['store.js', 'library.js', 'registry.js'].map(f => [f, sha(path.join(legacyDir, f))])),
};
writeFileSync(path.join(outDir, 'e2e-export.json'), JSON.stringify(info, null, 1));
console.log(JSON.stringify({ source_unchanged: info.source_unchanged, missing, summary }));
await browser.close();
server.close();
if (!info.source_unchanged || !missing.threw || missing.exists || before.version !== 1) process.exit(1);
