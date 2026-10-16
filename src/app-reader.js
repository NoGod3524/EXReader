// SPDX-License-Identifier: GPL-3.0-only
import { createReader as mountReader } from './index.js';
import { escapeHTML as esc } from './formats.js';
export async function createReader(stage, file, book, notes, callbacks) {
  const reader = await mountReader(stage, file, book, notes, callbacks);
  if (!reader.media) return reader;
  const audio = reader.media;
  const panel = document.createElement('div'); panel.className = 'audio-reader';
  panel.innerHTML = `<div class="audio-art">${book.cover ? `<img src="${esc(book.cover)}" alt="封面">` : '<span>♪</span>'}</div><p class="eyebrow">此刻，让文字有声音</p><h1>${esc(book.title)}</h1><p>${esc(book.author || '本地有声书')}</p><div class="audio-slot"></div><div class="audio-actions"><button data-skip="-15">↶ 15 秒</button><label>播放速度 <select id="audio-rate"><option value="0.75">0.75×</option><option selected value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><button data-skip="15">15 秒 ↷</button></div><p class="muted">支持格式取决于设备音频解码器。离开后保留播放进度。</p>`;
  audio.controls = true;
  panel.querySelector('.audio-slot').append(audio);
  stage.replaceChildren(panel);
  panel.querySelector('#audio-rate').onchange = event => { audio.playbackRate = Number(event.target.value); };
  panel.querySelectorAll('[data-skip]').forEach(button => { button.onclick = () => { audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + Number(button.dataset.skip))); }; });
  return reader;
}
