const fs = require('fs'), path = require('path'), { createRequire } = require('module');
const [root, pdf, pageNo, width, outp] = process.argv.slice(2);
const req = createRequire(path.join(path.resolve(root), 'package.json'));
const { createCanvas } = req('canvas'); const pdfjs = req('pdfjs-dist/legacy/build/pdf.js');
globalThis.pdfjsWorker = req('pdfjs-dist/legacy/build/pdf.worker.js');
(async () => {
  const doc = await pdfjs.getDocument({ data: new Uint8Array(fs.readFileSync(pdf)), disableFontFace: true, useSystemFonts: false }).promise;
  const p = await doc.getPage(Number(pageNo)); const vp = p.getViewport({ scale: Number(width) / p.getViewport({ scale: 1 }).width });
  const cv = createCanvas(Math.ceil(vp.width), Math.ceil(vp.height));
  await p.render({ canvasContext: cv.getContext('2d'), viewport: vp }).promise;
  fs.writeFileSync(outp, cv.toBuffer('image/png'));
})();
