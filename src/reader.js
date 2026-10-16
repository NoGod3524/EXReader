// SPDX-License-Identifier: GPL-3.0-only
import { foliate, openReflow } from './formats.js';
import { DEFAULT_SETTINGS } from './registry.js';
export async function createReader(stage, file, book, notes = [], options = {}) {
  const callbacks = { relocate() {}, keydown() {}, error: error => console.error(error), ...options, settings: () => ({ ...DEFAULT_SETTINGS, ...options.settings?.() }) };
  if (book.audio) return audioReader(stage, file, book, callbacks);
  if (book.format === 'pdf') return (await import('./pdf.js')).pdfReader(stage, file, book, notes, callbacks);
  const parsed = await openReflow(file, callbacks.settings().encoding);
  await foliate();
  const view = document.createElement('foliate-view');
  stage.replaceChildren(view);
  view.addEventListener('external-link', e => e.preventDefault());
  view.addEventListener('relocate', ({ detail }) => callbacks.relocate({ progress: detail.fraction || 0, cfi: detail.cfi, label: detail.tocItem?.label || book.title }));
  view.addEventListener('load', ({ detail: { doc } }) => {
    doc.addEventListener('keydown', callbacks.keydown);
  });
  view.addEventListener('draw-annotation', async ({ detail: { draw } }) => {
    const { Overlayer } = await import('../vendor/foliate/overlayer.js');
    draw(Overlayer.highlight, { color: '#edc86c' });
  });
  view.addEventListener('create-overlay', () => {
    for (const note of notes) if (note.value) view.addAnnotation(note).catch(callbacks.error);
  });
  await view.open(parsed);
  function apply() {
    const s = callbacks.settings();
    if (view.isFixedLayout) return;
    const colors = { paper: ['#faf8f2', '#302f2a'], light: ['#ffffff', '#20251f'], dark: ['#202823', '#dddccf'] }[s.theme];
    view.renderer.setAttribute('flow', s.flow);
    view.renderer.setAttribute('max-column-count', s.columns);
    view.renderer.setAttribute('max-inline-size', '800px');
    view.renderer.setAttribute('margin', '36px');
    view.renderer.setStyles?.(`html{color-scheme:${s.theme === 'dark' ? 'dark' : 'light'};background:${colors[0]}!important;color:${colors[1]}!important}body{font-family:${s.font}!important;font-size:${s.size}px!important}p,li,blockquote{font-size:inherit!important;line-height:${s.spacing}!important;text-align:${s.justify ? 'justify' : 'start'}!important}img,svg{max-width:100%}pre{white-space:pre-wrap}a{color:#9b653d}`);
  }
  apply();
  await view.init({ lastLocation: book.cfi, showTextStart: !book.cfi });
  return {
    toc: parsed.toc || [],
    next: () => view.goRight(), prev: () => view.goLeft(), seek: fraction => view.goToFraction(fraction),
    goTo: target => view.goTo(target),
    selected: () => {
      for (const { doc, index } of view.renderer.getContents()) {
        const selection = doc.getSelection();
        if (selection?.toString().trim() && selection.rangeCount) return { quote: selection.toString().trim(), value: view.getCFI(index, selection.getRangeAt(0)) };
      }
      return null;
    },
    location: () => ({ value: view.lastLocation?.cfi, quote: view.lastLocation?.tocItem?.label || '阅读书签' }),
    addAnnotation: note => note.value ? view.addAnnotation(note) : null,
    removeAnnotation: note => note.value ? view.deleteAnnotation(note) : null,
    apply,
    async search(query) {
      const result = [];
      for await (const item of view.search({ query })) {
        for (const hit of item.subitems || []) {
          const excerpt = hit.excerpt;
          result.push({ label: item.label, excerpt: typeof excerpt === 'string' ? excerpt : `${excerpt?.pre || ''}${excerpt?.match || ''}${excerpt?.post || ''}`, href: hit.cfi });
          if (result.length >= 100) return result;
        }
      }
      return result;
    },
    close() { view.close(); parsed.destroy?.(); view.remove(); },
  };
}
function audioReader(stage, file, book, callbacks) {
  const mime = { mp3: 'audio/mpeg', m4a: 'audio/mp4', m4b: 'audio/mp4', ogg: 'audio/ogg', opus: 'audio/ogg; codecs=opus', wav: 'audio/wav', flac: 'audio/flac', aac: 'audio/aac' }[book.format];
  const url = URL.createObjectURL(new Blob([file], { type: mime || file.type }));
  const audio = document.createElement('audio');
  audio.preload = 'metadata';
  stage.replaceChildren(audio);
  audio.src = url;
  audio.addEventListener('loadedmetadata', () => { audio.currentTime = Math.min(book.seconds || 0, audio.duration || 0); });
  audio.addEventListener('timeupdate', () => callbacks.relocate({ seconds: audio.currentTime, progress: audio.duration ? audio.currentTime / audio.duration : 0, label: String(audio.currentTime) }));
  audio.addEventListener('error', () => callbacks.error(new Error('设备无法解码此音频，请尝试 MP3 或 M4A')));
  return {
    media: audio,
    toc: [], next: () => { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 30); }, prev: () => { audio.currentTime = Math.max(0, audio.currentTime - 30); },
    seek: f => { if (Number.isFinite(audio.duration)) audio.currentTime = f * audio.duration; },
    goTo: seconds => { audio.currentTime = Number(seconds); },
    selected: () => null,
    location: () => ({ seconds: audio.currentTime, quote: String(audio.currentTime) }),
    addAnnotation() {}, removeAnnotation() {}, apply() {}, search: async () => [],
    close() { audio.pause(); audio.removeAttribute('src'); audio.load(); audio.remove(); URL.revokeObjectURL(url); },
  };
}
