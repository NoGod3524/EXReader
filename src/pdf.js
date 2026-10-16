// SPDX-License-Identifier: GPL-3.0-only
import * as pdfjs from 'pdfjs-dist/build/pdf.mjs';
import worker from 'pdfjs-dist/build/pdf.worker.mjs?url';
import './pdf-text-layer.css';
pdfjs.GlobalWorkerOptions.workerSrc = worker;
const assets = { cMapUrl: '/pdf-assets/cmaps/', standardFontDataUrl: '/pdf-assets/standard_fonts/', wasmUrl: '/pdf-assets/wasm/' };
export function configurePDF(options = {}) {
  for (const key of Object.keys(options)) {
    if (!Object.hasOwn(assets, key) || typeof options[key] !== 'string') throw new TypeError('PDF 资源配置无效');
  }
  Object.assign(assets, options);
}
export const loadPDF = async file => pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()), ...assets, cMapPacked: true, isEvalSupported: false }).promise;

export async function pdfReader(stage, file, book, notes, callbacks) {
  const pdf = await loadPDF(file);
  let pageNo = Math.max(1, Math.min(pdf.numPages, book.page || 1)), renderTask, textLayer, generation = 0, closed = false;
  stage.innerHTML = '<div class="pdf-scroll"><div class="pdf-page"><canvas></canvas><div class="textLayer"></div><div class="pdf-highlights"></div></div></div>';
  const canvas = stage.querySelector('canvas'), wrapper = stage.querySelector('.pdf-page');
  const layer = stage.querySelector('.textLayer'), highlights = stage.querySelector('.pdf-highlights');
  function paint() {
    highlights.replaceChildren();
    for (const note of notes.filter(n => n.page === pageNo && n.rects)) for (const r of note.rects) {
      const el = document.createElement('span');
      el.style.cssText = `left:${r.x * 100}%;top:${r.y * 100}%;width:${r.w * 100}%;height:${r.h * 100}%`;
      el.title = note.note || note.quote; highlights.append(el);
    }
  }
  async function render() {
    const current = ++generation;
    renderTask?.cancel(); textLayer?.cancel();
    const page = await pdf.getPage(pageNo);
    if (closed || current !== generation) return;
    const raw = page.getViewport({ scale: 1 });
    const scale = Math.min(1.8, Math.max(0.3, (stage.clientWidth - 32) / raw.width)) * (callbacks.settings().zoom || 1);
    const viewport = page.getViewport({ scale });
    const dpr = Math.min(devicePixelRatio, 2);
    canvas.width = Math.floor(viewport.width * dpr); canvas.height = Math.floor(viewport.height * dpr);
    canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
    wrapper.style.width = `${viewport.width}px`; wrapper.style.height = `${viewport.height}px`;
    wrapper.style.setProperty('--scale-factor', scale);
    layer.replaceChildren();
    renderTask = page.render({ canvasContext: canvas.getContext('2d'), viewport, transform: [dpr, 0, 0, dpr, 0, 0] });
    try {
      await renderTask.promise;
      if (closed || current !== generation) return;
      textLayer = new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container: layer, viewport });
      await textLayer.render();
      paint(); stage.querySelector('.pdf-scroll').scrollTop = 0;
      callbacks.relocate({ page: pageNo, progress: pageNo / pdf.numPages, label: `第 ${pageNo} / ${pdf.numPages} 页` });
    } catch (e) { if (!/cancel|abort/i.test(e.name) && !/cancel/i.test(e.message)) throw e; }
  }
  let resizeTimer;
  let previousWidth = stage.clientWidth, previousHeight = stage.clientHeight;
  const observer = new ResizeObserver(() => {
    if (stage.clientWidth === previousWidth && stage.clientHeight === previousHeight) return;
    previousWidth = stage.clientWidth; previousHeight = stage.clientHeight;
    clearTimeout(resizeTimer); resizeTimer = setTimeout(() => render().catch(callbacks.error), 200);
  });
  observer.observe(stage);
  await render();
  return {
    toc: Array.from({ length: pdf.numPages }, (_, i) => ({ label: `第 ${i + 1} 页`, href: i + 1 })),
    next: () => { if (pageNo < pdf.numPages) { pageNo++; return render(); } },
    prev: () => { if (pageNo > 1) { pageNo--; return render(); } },
    goTo: page => { pageNo = Math.max(1, Math.min(pdf.numPages, Number(page))); return render(); },
    seek: fraction => { pageNo = Math.max(1, Math.ceil(fraction * pdf.numPages)); return render(); },
    selected: () => {
      const selection = window.getSelection();
      if (!selection.rangeCount || !layer.contains(selection.anchorNode)) return null;
      const range = selection.getRangeAt(0), boundary = wrapper.getBoundingClientRect();
      return { quote: selection.toString().trim(), page: pageNo, rects: Array.from(range.getClientRects()).filter(r => r.width && r.height).map(r => ({ x: (r.left - boundary.left) / boundary.width, y: (r.top - boundary.top) / boundary.height, w: r.width / boundary.width, h: r.height / boundary.height })) };
    },
    location: () => ({ page: pageNo, quote: `第 ${pageNo} 页` }),
    addAnnotation: () => paint(),
    removeAnnotation: () => paint(),
    apply: () => render(),
    async search(query) {
      const result = [];
      for (let i = 1; i <= pdf.numPages && result.length < 100; i++) {
        const content = await (await pdf.getPage(i)).getTextContent();
        const text = content.items.map(x => x.str || '').join(' ');
        const at = text.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
        if (at !== -1) result.push({ label: `第 ${i} 页`, excerpt: text.slice(Math.max(0, at - 30), at + query.length + 60), href: i });
      }
      return result;
    },
    async close() { closed = true; generation++; observer.disconnect(); clearTimeout(resizeTimer); renderTask?.cancel(); textLayer?.cancel(); await pdf.loadingTask.destroy(); },
  };
}
