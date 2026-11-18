// SPDX-License-Identifier: MIT
// PDF.js child for tools/bench_large_vs_pdfjs.py. Writes the same JSON schema as the
// engine child of tools/bench_real_doc.py, so both sides go through one summarizer.
//
// Protocol (mirrors bench_real_doc.py child_capture):
//   open the document, then iteration 0 = cold round (first render of every page),
//   iterations 1..runs = warm rounds whose per-page times feed p50/p95/worst/throughput.
// Per-page time = getPage + viewport + canvas allocation + render, i.e. "page index in,
// finished bitmap out", which is what exr_fixed_render (which allocates its bitmap) costs.
// render_only_ms (page.render() promise alone) is recorded as well.
// page.cleanup() after every page, as in pdfjs-bench2/bench.cjs and bench_memory_pdfjs.cjs.
//
// GC: Node's GC runs inside the timed region. GC pause time per round is recorded from
// perf_hooks "gc" entries so the report can show how much of the PDF.js time is V8 GC.
// Peak RSS = process.resourceUsage().maxRSS, which libuv fills from
// PeakWorkingSetSize on Windows (the same counter the engine child reads).
'use strict';
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');
const { PerformanceObserver, performance } = require('perf_hooks');

const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : def; };
const root = opt('--pdfjs-root');
const input = opt('--input');
const width = Number(opt('--width'));
const runs = Number(opt('--runs', '5'));
const expectPages = Number(opt('--expect-pages', '0'));
const out = opt('--out');

const gcEntries = [];
const gcObserver = new PerformanceObserver((list) => { for (const e of list.getEntries()) gcEntries.push([e.startTime, e.duration]); });
gcObserver.observe({ entryTypes: ['gc'] });

const req = createRequire(path.join(path.resolve(root), 'package.json'));
const { createCanvas } = req('canvas');
const pdfjs = req('pdfjs-dist/legacy/build/pdf.js');
globalThis.pdfjsWorker = req('pdfjs-dist/legacy/build/pdf.worker.js');  // in-process worker, loaded before timing

class CanvasFactory {
  create(w, h) { const canvas = createCanvas(w, h); return { canvas, context: canvas.getContext('2d') }; }
  reset(cc, w, h) { cc.canvas.width = w; cc.canvas.height = h; }
  destroy(cc) { cc.canvas.width = 0; cc.canvas.height = 0; cc.canvas = null; cc.context = null; }
}
const factory = new CanvasFactory();
const now = () => process.hrtime.bigint();
const ms = (t0, t1) => Number(t1 - t0) / 1e6;
const peakBytes = () => process.resourceUsage().maxRSS * 1024;

const pct = (sorted, q) => sorted[Math.ceil(q * sorted.length) - 1];
const median = (values) => {
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

(async () => {
  const rssStart = process.memoryUsage.rss();
  const peakStart = peakBytes();
  const data = new Uint8Array(fs.readFileSync(input));
  const tOpen = now();
  const task = pdfjs.getDocument({ data, disableFontFace: true, useSystemFonts: false });
  const doc = await task.promise;
  const openMs = ms(tOpen, now());
  const rssAfterOpen = process.memoryUsage.rss();
  const pageCount = doc.numPages;
  if (expectPages && pageCount !== expectPages) throw new Error(`Expected ${expectPages} pages, found ${pageCount}`);

  const pages = Array.from({ length: pageCount }, (_, i) => ({ page: i + 1, render_ms: [], render_only_ms: [] }));
  const rounds = [];
  const roundWall = [];
  const roundSpans = [];
  let coldRoundWall = 0;
  for (let iteration = 0; iteration <= runs; iteration++) {
    const times = [];
    const spanStart = performance.now();
    const r0 = now();
    for (const page of pages) {
      const t0 = now();
      const p = await doc.getPage(page.page);
      const vp1 = p.getViewport({ scale: 1 });
      const vp = p.getViewport({ scale: width / vp1.width });
      const cc = factory.create(Math.ceil(vp.width), Math.ceil(vp.height));
      const t1 = now();
      await p.render({ canvasContext: cc.context, viewport: vp, canvasFactory: factory }).promise;
      const t2 = now();
      const elapsed = ms(t0, t2);
      if (cc.canvas.width !== width) throw new Error(`unexpected canvas ${cc.canvas.width}x${cc.canvas.height}`);
      if (iteration === 0) {
        Object.assign(page, {
          dimensions: [cc.canvas.width, cc.canvas.height],
          pixels: cc.canvas.width * cc.canvas.height,
          rgba_sha256: null,
          first_render_ms: elapsed,
          first_render_only_ms: ms(t1, t2),
          rss_after_first_render_bytes: process.memoryUsage.rss(),
          peak_rss_after_first_render_bytes: peakBytes(),
        });
      } else {
        page.render_ms.push(elapsed);
        page.render_only_ms.push(ms(t1, t2));
        times.push(elapsed);
      }
      factory.destroy(cc);
      p.cleanup();
    }
    const wall = ms(r0, now());
    roundSpans.push([spanStart, performance.now()]);
    if (iteration === 0) coldRoundWall = wall;
    else { rounds.push(times); roundWall.push(wall); }
  }
  const rssEnd = process.memoryUsage.rss();
  const peakEnd = peakBytes();
  await doc.cleanup();
  await task.destroy();
  // gc entries are delivered on a later timer tick, not on setImmediate: wait, then drain.
  await new Promise((resolve) => setTimeout(resolve, 200));
  for (const e of gcObserver.takeRecords()) gcEntries.push([e.startTime, e.duration]);

  const gcRoundMs = roundSpans.map(([a, b]) => gcEntries.filter(([s]) => s >= a && s < b).reduce((t, [, d]) => t + d, 0));

  for (const page of pages) {
    const s = [...page.render_ms].sort((a, b) => a - b);
    Object.assign(page, { p50_ms: median(s), p95_ms: pct(s, 0.95), max_ms: s[s.length - 1],
                          render_only_p50_ms: median(page.render_only_ms) });
  }
  const all = rounds.flat().sort((a, b) => a - b);
  const pageP50s = pages.map((p) => p.p50_ms).sort((a, b) => a - b);
  const worstByP50 = pages.reduce((a, b) => (b.p50_ms > a.p50_ms ? b : a));
  const worstByMax = pages.reduce((a, b) => (b.max_ms > a.max_ms ? b : a));
  const roundSums = rounds.map((r) => r.reduce((a, b) => a + b, 0));
  const wallP50 = median(roundSums);
  const r4 = (v) => Math.round(v * 1e4) / 1e4;
  const result = {
    width,
    page_count: pageCount,
    runs,
    open_ms: r4(openMs),
    first_page_render_ms: r4(pages[0].first_render_ms),
    first_screen_ms: r4(openMs + pages[0].first_render_ms),
    cold_round_wall_ms: r4(coldRoundWall),
    p50_ms: r4(median(all)),
    p95_ms: r4(pct(all, 0.95)),
    page_p50_median_ms: r4(median(pageP50s)),
    page_p95_ms: r4(pct(pageP50s, 0.95)),
    worst_page: worstByP50.page,
    worst_page_p50_ms: r4(worstByP50.p50_ms),
    worst_page_max_ms: r4(worstByMax.max_ms),
    worst_max_page: worstByMax.page,
    round_wall_ms_p50: r4(wallP50),
    total_measured_wall_ms: r4(roundSums.reduce((a, b) => a + b, 0)),
    throughput_pages_per_s: wallP50 > 0 ? Math.round(pageCount * 1e5 / wallP50) / 100 : 0,
    render_only_p50_ms: r4(median(pages.flatMap((p) => p.render_only_ms))),
    gc_cold_round_ms: r4(gcRoundMs[0]),
    gc_events: gcEntries.length,
    gc_warm_round_ms: gcRoundMs.slice(1).map(r4),
    gc_warm_share_pct: r4(100 * gcRoundMs.slice(1).reduce((a, b) => a + b, 0) / roundSums.reduce((a, b) => a + b, 0)),
    rss_start_bytes: rssStart,
    peak_rss_start_bytes: peakStart,
    rss_after_open_bytes: rssAfterOpen,
    rss_end_bytes: rssEnd,
    peak_rss_bytes: peakEnd,
    peak_rss_mib: Math.round(peakEnd / 10485.76) / 100,
    active_pixels_per_round: pages.reduce((a, p) => a + p.pixels, 0),
    pages,
  };
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, JSON.stringify(result, null, 2) + '\n');
})().catch((e) => { console.error((e && e.stack) || e); process.exit(1); });
