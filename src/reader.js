import { foliate, openReflow, escapeHTML as esc } from './formats.js';
export async function createReader(stage, file, book, notes, callbacks) {
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
    const colors = { paper: ['#faf8f2', '#302f2a'], light: ['#ffffff', '#20251f'], dark: ['#202823', '#dddccf'] }[s.theme];
    view.renderer.setAttribute('flow', s.flow);
    view.renderer.setAttribute('max-column-count', s.columns);
    view.renderer.setAttribute('max-inline-size', '800');
    view.renderer.setAttribute('margin', '36');
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
  stage.innerHTML = `<div class="audio-reader"><div class="audio-art">${book.cover ? `<img src="${esc(book.cover)}" alt="封面">` : '<span>♪</span>'}</div><p class="eyebrow">此刻，让文字有声音</p><h1>${esc(book.title)}</h1><p>${esc(book.author || '本地有声书')}</p><audio controls preload="metadata"></audio><div class="audio-actions"><button data-skip="-15">↶ 15 秒</button><label>播放速度 <select id="audio-rate"><option value="0.75">0.75×</option><option selected value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><button data-skip="15">15 秒 ↷</button></div><p class="muted">支持格式取决于设备音频解码器。离开后保留播放进度。</p></div>`;
  const audio = stage.querySelector('audio'); audio.src = url;
  audio.addEventListener('loadedmetadata', () => { audio.currentTime = Math.min(book.seconds || 0, audio.duration || 0); });
  audio.addEventListener('timeupdate', () => callbacks.relocate({ seconds: audio.currentTime, progress: audio.duration ? audio.currentTime / audio.duration : 0, label: `${Math.floor(audio.currentTime / 60)} 分 / ${Math.floor((audio.duration || 0) / 60)} 分` }));
  audio.addEventListener('error', () => callbacks.error(new Error('设备无法解码此音频，请尝试 MP3 或 M4A')));
  stage.querySelector('#audio-rate').onchange = e => { audio.playbackRate = Number(e.target.value); };
  stage.querySelectorAll('[data-skip]').forEach(el => { el.onclick = () => { audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + Number(el.dataset.skip))); }; });
  return {
    toc: [], next: () => { audio.currentTime += 30; }, prev: () => { audio.currentTime = Math.max(0, audio.currentTime - 30); },
    seek: f => { if (Number.isFinite(audio.duration)) audio.currentTime = f * audio.duration; },
    goTo: seconds => { audio.currentTime = Number(seconds); },
    selected: () => null,
    location: () => ({ seconds: audio.currentTime, quote: `${Math.floor(audio.currentTime / 60)}:${String(Math.floor(audio.currentTime % 60)).padStart(2, '0')} 声音书签` }),
    addAnnotation() {}, removeAnnotation() {}, apply() {}, search: async () => [],
    close() { audio.pause(); audio.removeAttribute('src'); audio.load(); URL.revokeObjectURL(url); },
  };
}
