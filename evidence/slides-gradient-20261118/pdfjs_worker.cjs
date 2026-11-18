'use strict';
// Accept a zero-based page index and hash flag, then return nanoseconds and an optional RGBA hash.
const fs = require('fs');
const path = require('path');
const hash = require('crypto');
const req = require('module').createRequire(path.resolve(process.argv[2], 'package.json'));
const { createCanvas } = req('canvas');
const pdfjs = req('pdfjs-dist/legacy/build/pdf.js');
globalThis.pdfjsWorker = req('pdfjs-dist/legacy/build/pdf.worker.js');
const factory = {
  create(w, h) { const canvas = createCanvas(w, h); return { canvas, context: canvas.getContext('2d') }; },
  reset(cc, w, h) { cc.canvas.width = w; cc.canvas.height = h; },
  destroy(cc) { cc.canvas.width = 0; cc.canvas.height = 0; cc.canvas = null; cc.context = null; }
};
(async () => {
  const task = pdfjs.getDocument({ data: new Uint8Array(fs.readFileSync(process.argv[3])), disableFontFace: true, useSystemFonts: false });
  const doc = await task.promise;
  if (doc.numPages !== 100) throw Error('unexpected page count');
  const lines = require('readline').createInterface({ input: process.stdin });
  console.log('@ready');
  for await (const line of lines) {
    const [i, cold] = line.trim().split(' ').map(Number);
    const start = process.hrtime.bigint();
    const page = await doc.getPage(i + 1);
    const at1 = page.getViewport({ scale: 1 });
    const vp = page.getViewport({ scale: 1200 / at1.width });
    const cc = factory.create(Math.ceil(vp.width), Math.ceil(vp.height));
    await page.render({ canvasContext: cc.context, viewport: vp, canvasFactory: factory }).promise;
    const ns = Number(process.hrtime.bigint() - start);
    if (cc.canvas.width !== 1200 || cc.canvas.height !== 900) throw Error('unexpected canvas size');
    const sig = cold ? hash.createHash('sha256').update(cc.context.getImageData(0, 0, 1200, 900).data).digest('hex') : null;
    factory.destroy(cc);
    page.cleanup();
    console.log('@' + JSON.stringify([ns, sig]));
  }
  await doc.cleanup();
  await task.destroy();
})().catch(err => { console.error(err); process.exit(1); });
