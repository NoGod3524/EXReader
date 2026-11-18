// SPDX-License-Identifier: MIT
'use strict';
// PDF.js 3.11.174/node-canvas scopes. The stdin gate is driven by pdfjs_scopes.py.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const Module = require('node:module');
const { createInterface } = require('node:readline');
const req = Module.createRequire(path.resolve(process.argv[2], 'package.json'));
const { createCanvas } = req('canvas');
const file = req.resolve('pdfjs-dist/legacy/build/pdf.js');
globalThis.pdfjsWorker = req('pdfjs-dist/legacy/build/pdf.worker.js');
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
const now = () => process.hrtime.bigint();
let images = [], clip = [];

function instrument(source) {
  function add(before, after, replacements) {
    const start = source.indexOf(before), end = source.indexOf(after, start + before.length);
    if (start < 0 || end < 0) throw Error('Unknown PDF.js bundle');
    let method = source.slice(start, end);
    for (const [old, replacement] of replacements) {
      if (method.split(old).length !== 2) throw Error('Scope anchor changed: ' + old);
      method = method.replace(old, replacement);
    }
    source = source.slice(0, start) + method + source.slice(end);
  }
  add('  paintInlineImageXObject(imgData) {', '  paintInlineImageXObjectGroup', [
    ['    const width = imgData.width;', '    const begin = process.hrtime.bigint();\n    const width = imgData.width;'],
    ['    const scaled = this._scaleImage', '    const prepare = process.hrtime.bigint();\n    const scaled = this._scaleImage'],
    ['    ctx.imageSmoothingEnabled =', '    const scale = process.hrtime.bigint();\n    ctx.imageSmoothingEnabled ='],
    ['    this.compose();', '    const draw = process.hrtime.bigint();\n    this.compose();'],
    ['    this.restore();', '    this.restore();\n    globalThis.multiimageScope(imgData, begin, prepare, scale, draw);'],
  ]);
  add('  consumePath(clipBox) {', '  getSinglePixelWidth()', [
    ['    const isEmpty =', '    const begin = this.pendingClip && process.hrtime.bigint();\n    const isEmpty ='],
    ['    ctx.beginPath();', '    ctx.beginPath();\n    if (begin) globalThis.multiimageClip(begin);'],
  ]);
  return source;
}

globalThis.multiimageScope = (data, begin, prepare, scale, draw) => {
  const end = now();
  images.push({ kind: data.kind, width: data.width, height: data.height,
    total_ns: Number(end - begin), preparation_ns: Number(prepare - begin),
    scale_ns: Number(scale - prepare), draw_ns: Number(draw - scale),
    compose_restore_ns: Number(end - draw) });
};
globalThis.multiimageClip = begin => clip.push(Number(now() - begin));

function loadProbe() {
  const mod = new Module(file, module);
  mod.filename = file;
  mod.paths = Module._nodeModulePaths(path.dirname(file));
  mod._compile(instrument(fs.readFileSync(file, 'utf8')), file);
  return mod.exports;
}
const factory = {
  create(w, h) { const canvas = createCanvas(w, h); return { canvas, context: canvas.getContext('2d') }; },
  reset(cc, w, h) { cc.canvas.width = w; cc.canvas.height = h; },
  destroy(cc) { cc.canvas.width = cc.canvas.height = 0; cc.canvas = cc.context = null; },
};

async function main() {
  const runs = Number(process.argv[4]);
  const data = fs.readFileSync(process.argv[3]);
  const engines = [req('pdfjs-dist/legacy/build/pdf.js'), loadProbe()];
  const tasks = engines.map(e => e.getDocument({ data: new Uint8Array(data),
    disableFontFace: true, useSystemFonts: false }));
  const docs = await Promise.all(tasks.map(t => t.promise));
  const stdin = createInterface({input: process.stdin})[Symbol.asyncIterator]();
  const sweeps = [], gates = [];
  for (let r = 0; r <= runs;) {
    console.log('@gate');
    const line = await stdin.next();
    if (line.done) throw Error('Missing gate sample');
    const busy = Number(line.value);
    if (!Number.isFinite(busy) || busy < 0 || busy > 15) throw Error('Idle gate closed');
    const pair = [{}, {}];
    for (let i = 71; i <= 100; ++i) {
      for (const j of (r+i) % 2 ? [0, 1] : [1, 0]) {
        images = []; clip = [];
        const t = now();
        const page = await docs[j].getPage(i);
        const vp = page.getViewport({scale: 1200 / page.getViewport({scale: 1}).width});
        const cc = factory.create(Math.ceil(vp.width), Math.ceil(vp.height));
        await page.render({canvasContext: cc.context, viewport: vp, canvasFactory: factory}).promise;
        const record = {ns: Number(now() - t), images, clip};
        if (!r) record.rgba = hash(cc.context.getImageData(0, 0, cc.canvas.width, cc.canvas.height).data);
        factory.destroy(cc);
        page.cleanup();
        pair[j][i] = record;
      }
      if (!r && pair[0][i].rgba !== pair[1][i].rgba) throw Error('PDF.js parity page ' + i);
      if (pair[1][i].images.length !== 3 || pair[1][i].clip.length !== 3) throw Error('Scope count page ' + i);
    }
    console.log('@done');
    const verdict = await stdin.next();
    if (verdict.done) throw Error('Missing post-capture gate verdict');
    if (verdict.value === 'retry') continue;
    if (verdict.value !== 'ok') throw Error('Invalid post-capture gate verdict');
    gates.push(busy);
    sweeps.push(pair);
    ++r;
  }
  await Promise.all(tasks.map(t => t.destroy()));
  console.log('@' + JSON.stringify({pdfjs: engines[0].version, canvas: req('canvas').version,
    bundle_sha256: hash(fs.readFileSync(file)), pdf_sha256: hash(data), gates, sweeps}));
}
main().catch(err => { console.error(err); process.exitCode = 1; });
