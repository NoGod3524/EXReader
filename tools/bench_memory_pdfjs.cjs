// SPDX-License-Identifier: MIT
// PDF.js side of tools/bench_memory.py. Stage protocol: print "STAGE <name>",
// wait for one stdin line (the parent samples this process with
// GetProcessMemoryInfo meanwhile), finally print "RESULT <json>".
// Run with --expose-gc so "closed_gc" can separate GC timing from renderer memory.
// Same render calls and canvas factory as pdfjs-bench2/bench.cjs (pdfjs-dist 3.11.174
// legacy build + node-canvas).
'use strict';
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');
const readline = require('readline');

const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : def; };
const root = opt('--pdfjs-root');
const width = Number(opt('--width', '1200'));
const rounds = Number(opt('--rounds', '0'));
const cycles = Number(opt('--cycles', '0'));
const inputs = argv.slice(argv.indexOf('--') + 1);

const rl = readline.createInterface({ input: process.stdin });
const lines = rl[Symbol.asyncIterator]();
async function stage(name) {
  process.stdout.write(`STAGE ${name}\n`);
  const next = await lines.next();
  if (next.done) process.exit(3);
}

const req = createRequire(path.join(root, 'package.json'));
const { createCanvas } = req('canvas');
const pdfjs = req('pdfjs-dist/legacy/build/pdf.js');
// Load the worker code up front (in-process "fake worker", as Node always uses),
// so module loading is part of "loaded" just like the engine DLL load.
globalThis.pdfjsWorker = req('pdfjs-dist/legacy/build/pdf.worker.js');

class CanvasFactory {
  create(w, h) { const canvas = createCanvas(w, h); return { canvas, context: canvas.getContext('2d') }; }
  reset(cc, w, h) { cc.canvas.width = w; cc.canvas.height = h; }
  destroy(cc) { cc.canvas.width = 0; cc.canvas.height = 0; cc.canvas = null; cc.context = null; }
}
const factory = new CanvasFactory();
const ms = (t0) => Number(process.hrtime.bigint() - t0) / 1e6;

async function openAll() {
  const docs = [];
  for (const file of inputs) {
    const t0 = process.hrtime.bigint();
    const data = new Uint8Array(fs.readFileSync(file));
    const task = pdfjs.getDocument({ data, disableFontFace: true, useSystemFonts: false });
    const doc = await task.promise;
    docs.push({ task, doc, openMs: ms(t0) });
  }
  return docs;
}

async function render(doc, number) {
  const t0 = process.hrtime.bigint();
  const page = await doc.getPage(number);
  const vp1 = page.getViewport({ scale: 1 });
  const vp = page.getViewport({ scale: width / vp1.width });
  const cc = factory.create(Math.ceil(vp.width), Math.ceil(vp.height));
  await page.render({ canvasContext: cc.context, viewport: vp, canvasFactory: factory }).promise;
  const elapsed = ms(t0);
  factory.destroy(cc);
  page.cleanup();
  return elapsed;
}

async function renderAll(docs, skipFirst) {
  for (let d = 0; d < docs.length; d++) {
    for (let p = 1; p <= docs[d].doc.numPages; p++) {
      if (skipFirst && d === 0 && p === 1) continue;
      await render(docs[d].doc, p);
    }
  }
}

async function closeAll(docs) {
  for (const item of docs) { await item.doc.cleanup(); await item.task.destroy(); }
}

(async () => {
  const result = {};
  await stage('loaded');
  let docs = await openAll();
  result.open_ms = docs.map((d) => d.openMs);
  result.pages = docs.map((d) => d.doc.numPages);
  await stage('opened');
  // getPage(1) is included: PDF.js resolves the page tree lazily at this point.
  result.first_render_ms = await render(docs[0].doc, 1);
  await stage('first_page');
  await renderAll(docs, true);
  await stage('rendered');
  if (rounds) {
    for (let r = 0; r < rounds; r++) await renderAll(docs, false);
    await stage('steady');
  }
  await closeAll(docs);
  docs = null;
  await stage('closed');
  global.gc();
  await new Promise((resolve) => setImmediate(resolve));
  global.gc();
  await stage('closed_gc');
  for (let i = 0; i < cycles; i++) {
    docs = await openAll();
    await renderAll(docs, false);
    await closeAll(docs);
    docs = null;
    global.gc();
    await stage(`cycle_${i + 1}`);
  }
  process.stdout.write('RESULT ' + JSON.stringify(result) + '\n');
  rl.close();
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
