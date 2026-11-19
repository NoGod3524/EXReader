// Persistent JSON-lines worker; stdout is reserved for protocol replies.
'use strict';
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const readline = require('readline'), {createRequire} = require('module');
console.log = (...args) => console.error(...args);
const root = path.resolve(process.argv[2]);
const req = createRequire(path.join(root, 'package.json'));
const pkg = req('./package.json');
if (pkg.name !== 'pdfjs-dist' || pkg.version !== '3.11.174')
  throw Error('Expected --pdfjs-root to be the pdfjs-dist 3.11.174 package directory');
const {createCanvas} = req('canvas');
const pdfjs = req('./legacy/build/pdf.js');
if (pdfjs.version !== pkg.version) throw Error('PDF.js runtime version mismatch');
let task, doc;
async function handle(m) {
  if (m.op === 'open') {
    if (task) await task.destroy();
    task = pdfjs.getDocument({data: new Uint8Array(fs.readFileSync(m.file)),
      standardFontDataUrl: path.join(root, 'standard_fonts') + path.sep,
      cMapUrl: path.join(root, 'cmaps') + path.sep, cMapPacked: true,
      useSystemFonts: false, isEvalSupported: false});
    doc = await task.promise;
    return {pages: doc.numPages, node: process.version, canvas: req('canvas/package.json').version,
      pdfjs: pdfjs.version, pid: process.pid};
  }
  if (m.op !== 'render') throw Error('unknown request');
  const page = await doc.getPage(m.page), base = page.getViewport({scale: 1});
  const vp = page.getViewport({scale: m.width/base.width});
  const w = m.width, h = Math.max(1, Math.ceil(vp.height - 1e-9));
  const start = process.hrtime.bigint();
  const canvas = createCanvas(w,h), ctx = canvas.getContext('2d');
  await page.render({canvasContext: ctx, viewport: vp, background:'rgb(255,255,255)'}).promise;
  const ns = Number(process.hrtime.bigint() - start);
  const data = ctx.getImageData(0,0,w,h).data;
  const sha256 = crypto.createHash('sha256').update(data).digest('hex');
  return {ns, dimensions:[w,h], sha256, rss_bytes:process.memoryUsage().rss};
}
(async () => {
  for await (const line of readline.createInterface({input:process.stdin})) {
    try { process.stdout.write(JSON.stringify(await handle(JSON.parse(line)))+'\n'); }
    catch (e) { process.stdout.write(JSON.stringify({error:String(e.stack || e)})+'\n'); }
  }
  if (task) await task.destroy();
})().catch(e => { console.error(e); process.exitCode = 1; });
