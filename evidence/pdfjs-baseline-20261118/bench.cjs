const fs = require('fs');
const path = require('path');
const { createCanvas } = require('canvas');
const pdfjs = require('pdfjs-dist/legacy/build/pdf.js');

class CanvasFactory {
  create(w, h) { const canvas = createCanvas(w, h); return { canvas, context: canvas.getContext('2d') }; }
  reset(cc, w, h) { cc.canvas.width = w; cc.canvas.height = h; }
  destroy(cc) { cc.canvas.width = 0; cc.canvas.height = 0; cc.canvas = null; cc.context = null; }
}

async function bench(pdfPath, width, runs) {
  const data = new Uint8Array(fs.readFileSync(pdfPath));
  const task = pdfjs.getDocument({ data, disableFontFace: true, useSystemFonts: false });
  const doc = await task.promise;
  const n = doc.numPages;
  const factory = new CanvasFactory();
  const times = [];
  let firstMs = null;
  for (let iter = 0; iter <= runs; iter++) {
    for (let p = 1; p <= n; p++) {
      const page = await doc.getPage(p);
      const vp1 = page.getViewport({ scale: 1 });
      const vp = page.getViewport({ scale: width / vp1.width });
      const cc = factory.create(Math.ceil(vp.width), Math.ceil(vp.height));
      const t0 = process.hrtime.bigint();
      await page.render({ canvasContext: cc.context, viewport: vp, canvasFactory: factory }).promise;
      const ms = Number(process.hrtime.bigint() - t0) / 1e6;
      if (iter === 0 && p === 1) firstMs = ms;
      if (iter > 0) times.push(ms);
      factory.destroy(cc);
      page.cleanup();
    }
  }
  times.sort((a, b) => a - b);
  const p50 = times[Math.floor(times.length / 2)];
  const p95 = times[Math.floor(times.length * 0.95)];
  console.log(`  ${path.basename(pdfPath).padEnd(14)} ${String(width).padStart(5)}px  p50=${p50.toFixed(3)}  best=${times[0].toFixed(3)}  p95=${p95.toFixed(3)}  first=${firstMs.toFixed(3)}  pages=${n}`);
}

(async () => {
  for (const f of process.argv.slice(2)) {
    if (!fs.existsSync(f)) { console.log(`  skip ${f}`); continue; }
    for (const w of [600, 1200]) {
      try { await bench(f, w, 5); } catch (e) { console.log(`  ${path.basename(f)} ${w}px ERROR: ${e.message}`); }
    }
  }
})();
