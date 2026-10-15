import './style.css';
import * as store from './store.js';
import { BOOK_EXTENSIONS, AUDIO_EXTENSIONS, extension, escapeHTML as esc, readMetadata, coverImage } from './formats.js';
import { createReader } from './reader.js';

const icons = {
  book: '<path d="M4 4c4-1 6 0 8 2 2-2 4-3 8-2v15c-4-1-6 0-8 2-2-2-4-3-8-2z"/><path d="M12 6v15"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  heart: '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z"/>',
  audio: '<path d="M3 14v-3a9 9 0 0 1 18 0v3"/><rect x="2" y="12" width="5" height="9" rx="2"/><rect x="17" y="12" width="5" height="9" rx="2"/>',
  note: '<path d="M14 3H4v18h16V11M9 15l1-5L19 1l4 4-9 9z"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
  plus: '<path d="M12 4v16M4 12h16"/>',
  search: '<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>',
  arrow: '<path d="m9 5 7 7-7 7M3 12h13"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M3 15v6h18v-6"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  close: '<path d="m5 5 14 14M19 5 5 19"/>',
  back: '<path d="m12 4-8 8 8 8M4 12h17"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h1M3 12h1M3 18h1"/>',
  check: '<path d="m5 12 4 4 10-10"/>',
  bookmark: '<path d="M5 3h14v18l-7-5-7 5z"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M3 17v4h18v-4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 1v2m0 18v2M1 12h2m18 0h2M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.book}</svg>`;
const btn = (action, label, i, cls = '') => `<button class="${cls}" data-action="${action}" aria-label="${esc(label)}">${i ? icon(i) : ''}<span>${label}</span></button>`;
const app = document.querySelector('#app');
let books = [], notes = [], tab = 'all', query = '', sort = 'recent', layout = 'grid', active, reader, currentNotes = [], busy = false, persistTimer, toastTimer;
const defaults = { size: 20, spacing: 1.8, font: 'serif', theme: 'paper', flow: 'paginated', columns: '1', justify: true, encoding: 'auto', zoom: 1 };
let settings;
try { settings = { ...defaults, ...JSON.parse(localStorage.getItem('exreader-settings') || '{}') }; } catch { settings = { ...defaults }; }
function toast(message) { const el = document.querySelector('#toast'); el.textContent = message; el.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 5000); }
function error(e) { console.error(e); toast(e.message || String(e)); }
const run = fn => Promise.resolve().then(fn).catch(error);
function cover(book, extra = '') {
  return `<div class="cover cover-${book.id.charCodeAt(0) % 5} ${extra}">${book.cover ? `<img src="${esc(book.cover)}" alt="${esc(book.title)}的封面" loading="lazy">` : `<div class="cover-top">EX LIBRIS <span>✦</span></div><div class="cover-title">${esc(book.title)}</div><div class="cover-author">${esc(book.author || '私人藏书')}</div><div class="cover-lines"></div>`}<span class="format-pill">${esc(book.format.toUpperCase())}</span>${book.audio ? `<span class="audio-badge">${icon('audio')}</span>` : ''}</div>`;
}
const progress = book => Math.round(Math.max(0, Math.min(1, book.progress || 0)) * 100);
function nav(id, label, i, count) { return `<button class="nav-item ${tab === id ? 'selected' : ''}" data-tab="${id}">${icon(i)}<span>${label}</span>${count !== undefined ? `<small>${count}</small>` : ''}</button>`; }
function shell() {
  app.innerHTML = `<div class="library-shell"><aside class="sidebar"><a class="brand" href="#" aria-label="EXReader 首页"><span class="brand-mark">${icon('book')}</span><span>EXReader<small>悦 读 · 自 在</small></span></a><div class="sidebar-label">我的阅读空间</div><nav>${nav('all', '全部书籍', 'grid', books.length)}${nav('reading', '正在阅读', 'clock')}${nav('favorite', '我的收藏', 'heart')}${nav('audio', '有声书', 'audio')}${nav('notes', '标注与想法', 'note', notes.length)}</nav><div class="sidebar-bottom"><div class="local-note"><span class="online-dot"></span>只属于你的书库<small>本地保存，无需账号</small></div>${btn('settings', '偏好设置', 'settings', 'nav-item')}${btn('backup', '备份书库', 'download', 'nav-item')}</div></aside><main class="library-main"><header class="topbar"><div class="breadcrumb">我的书库 <span>/</span> <strong>${({ all: '全部书籍', reading: '正在阅读', favorite: '我的收藏', audio: '有声书', notes: '标注与想法' })[tab]}</strong></div><div class="top-actions"><button class="icon-button" data-action="settings" aria-label="偏好设置">${icon('settings')}</button><span class="local-indicator">${icon('check')}本地书库</span>${btn('import', '导入书籍', 'plus', 'primary')}</div></header><div id="library-content"></div><footer class="library-footer"><span>少一点打扰，多一点阅读。</span><span>EXReader <span class="footer-dot">✦</span> 0.1</span></footer></main></div><input id="file-input" type="file" multiple accept="${[...BOOK_EXTENSIONS, ...AUDIO_EXTENSIONS].map(x => '.' + x).join(',')}" hidden><input id="restore-input" type="file" accept=".zip" hidden>`;
  app.querySelector('.brand').onclick = e => { e.preventDefault(); tab = 'all'; shell(); };
  app.querySelector('#file-input').onchange = e => importFiles(e.target.files);
  app.querySelector('#restore-input').onchange = e => e.target.files[0] && run(async () => {
    const count = await (await import('./transfer.js')).restoreBackup(e.target.files[0]); await reload(); shell(); toast(`已恢复 ${count} 本书`);
  });
  renderContent();
}
function renderContent() {
  const area = document.querySelector('#library-content');
  if (!area) return;
  if (tab === 'notes') { renderAllNotes(area); return; }
  const labels = { all: ['每一本书，都是一个新世界。', '我的书库'], reading: ['翻开书，接着上次的旅程。', '正在阅读'], favorite: ['值得珍藏，也值得重读。', '我的收藏'], audio: ['闭上眼睛，也能抵达远方。', '听见好书'] };
  const [subtitle, title] = labels[tab];
  let filtered = books.filter(b => tab === 'all' || tab === 'reading' && b.progress > 0 && b.status !== 'finished' || tab === 'favorite' && b.favorite || tab === 'audio' && b.audio).filter(b => `${b.title} ${b.author} ${(b.tags || []).join(' ')}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  filtered.sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title, 'zh') : sort === 'added' ? b.added - a.added : (b.lastRead || b.added) - (a.lastRead || a.added));
  const recent = tab === 'all' && !query ? books.filter(b => b.lastRead && b.status !== 'finished').sort((a, b) => b.lastRead - a.lastRead)[0] : null;
  area.innerHTML = `<section class="library-intro"><div><p class="eyebrow">YOUR PERSONAL READING CORNER</p><h1>${title}<span class="title-dot">.</span></h1><p class="subtitle">${subtitle}</p></div><div class="intro-quote">“ 读书，是为了遇见更好的自己。<small>留一点时间，给阅读</small></div></section>${recent ? `<section class="continue-card"><div class="continue-cover">${cover(recent)}</div><div class="continue-info"><p class="eyebrow">继续上次的阅读</p><h2>${esc(recent.title)}</h2><p>${esc(recent.author || '慢慢读，不着急。')}</p><div class="continue-progress"><div class="progress-track"><i style="width:${progress(recent)}%"></i></div><small>已读 ${progress(recent)}%</small></div></div><button class="primary" data-open="${recent.id}">继续阅读 ${icon('arrow')}</button><span class="continue-watermark">${icon('book')}</span></section>` : ''}<div class="shelf-toolbar"><div class="shelf-title"><strong>${tab === 'audio' ? '有声书' : '全部藏书'}</strong><span>${filtered.length} 本</span></div><div class="shelf-controls"><label class="search-box">${icon('search')}<input id="library-search" placeholder="搜索书名、作者、标签" aria-label="搜索书库" value="${esc(query)}"></label><select id="sort" aria-label="书籍排序"><option value="recent" ${sort === 'recent' ? 'selected' : ''}>最近阅读</option><option value="added" ${sort === 'added' ? 'selected' : ''}>最近添加</option><option value="title" ${sort === 'title' ? 'selected' : ''}>书名排序</option></select><div class="view-switch"><button data-layout="grid" class="${layout === 'grid' ? 'chosen' : ''}" aria-label="网格视图">${icon('grid')}</button><button data-layout="list" class="${layout === 'list' ? 'chosen' : ''}" aria-label="列表视图">${icon('list')}</button></div></div></div>${filtered.length ? `<div class="book-grid ${layout === 'list' ? 'book-list' : ''}">${filtered.map(b => `<article class="book-card"><button class="book-open" data-open="${b.id}" aria-label="阅读 ${esc(b.title)}">${cover(b)}</button><div class="book-info"><button class="book-title" data-open="${b.id}">${esc(b.title)}</button><p class="book-author">${esc(b.author || '作者未填写')}</p><div class="book-meta"><span>${b.status === 'finished' ? '✓ 已读完' : b.progress ? '已读 ' + progress(b) + '%' : '未开始'}</span>${b.favorite ? `<span class="favorite-mark">${icon('heart')}</span>` : ''}<button class="more-button" data-edit="${b.id}" aria-label="管理 ${esc(b.title)}">${icon('more')}</button></div>${b.progress ? `<div class="progress-track mini"><i style="width:${progress(b)}%"></i></div>` : ''}</div></article>`).join('')}<button class="add-book-tile" data-action="import">${icon('plus')}<span>再添一本好书</span><small>或将文件拖到这里</small></button></div>` : `<section class="empty-state"><div class="empty-books"><span></span><span>${icon('book')}</span><span></span></div><h2>${books.length ? '这里还没有书' : '让你的第一本书，住进来。'}</h2><p>${query ? '试试其他书名、作者或标签' : '导入喜爱的书，在任何一页，找到片刻宁静。'}</p>${btn('import', '选择本地书籍', 'upload', 'primary')}<small>PDF · EPUB · MOBI · FB2 · TXT · RTF · DOCX · 有声书</small>${!books.length ? '<button class="text-button" data-action="sample">先读一篇示例文章 →</button>' : ''}</section>`}<div class="drop-hint">${icon('upload')}将书籍拖入这里，即可加入书库<span>文件始终保存在你的设备上</span></div>`;
  const input = area.querySelector('#library-search');
  input.oninput = e => { const pos = e.target.selectionStart; query = e.target.value; renderContent(); const next = area.querySelector('#library-search'); next.focus(); next.setSelectionRange(pos, pos); };
  area.querySelector('#sort').onchange = e => { sort = e.target.value; renderContent(); };
}
function renderAllNotes(area) {
  area.innerHTML = `<section class="library-intro"><div><p class="eyebrow">WORDS THAT STAY WITH YOU</p><h1>标注与想法<span class="title-dot">.</span></h1><p class="subtitle">把触动你的句子，留在这里。</p></div>${btn('export-notes', '导出 Markdown', 'download', 'secondary')}</section><div class="notes-grid">${notes.length ? notes.sort((a, b) => b.created - a.created).map(n => `<article class="note-card"><p class="note-book">${esc(books.find(b => b.id === n.bookId)?.title || '未知书籍')}</p><blockquote>${esc(n.quote)}</blockquote><p>${esc(n.note)}</p><footer><time>${new Date(n.created).toLocaleDateString('zh-CN')}</time><button data-note-open="${n.id}" class="text-button">回到原文 →</button><button data-note-delete="${n.id}" aria-label="删除标注">${icon('close')}</button></footer></article>`).join('') : '<div class="empty-state"><h2>读到喜欢的句子，就把它留下。</h2><p>阅读时选中文字，点击“标注”，也可以添加页面书签。</p></div>'}</div>`;
}
async function reload() { [books, notes] = await Promise.all([store.allBooks(), store.allNotes()]); }
async function importFiles(files) {
  if (busy) { toast('正在处理，请稍候'); return; }
  busy = true; let count = 0; const failures = [];
  for (const file of Array.from(files || [])) {
    try {
      const ext = extension(file.name);
      if (![...BOOK_EXTENSIONS, ...AUDIO_EXTENSIONS].includes(ext)) throw new Error('不支持此格式');
      if (books.some(b => b.filename === file.name && b.size === file.size && b.modified === file.lastModified)) { failures.push(`${file.name} 已在书库中`); continue; }
      toast(`正在导入：${file.name}`);
      const metadata = await readMetadata(file);
      const book = { ...metadata, id: crypto.randomUUID(), filename: file.name, size: file.size, modified: file.lastModified, added: Date.now(), progress: 0, favorite: false, tags: [], status: 'unread' };
      await store.addBook(book, file); books.push(book); count++;
    } catch (e) { failures.push(`${file.name}：${e.message}`); }
  }
  busy = false;
  if (count) run(() => navigator.storage?.persist?.());
  if (!active) shell();
  toast(`已导入 ${count} 本${failures.length ? '；' + failures.join('；') : ''}`);
}
function dialog(title, body, className = '') {
  document.querySelector('dialog')?.remove();
  const d = document.createElement('dialog'); d.className = className;
  d.innerHTML = `<div class="dialog-head"><h2>${title}</h2><button class="icon-button" data-dismiss aria-label="关闭">${icon('close')}</button></div>${body}`;
  document.body.append(d); d.showModal();
  d.querySelector('[data-dismiss]').onclick = () => d.close();
  d.addEventListener('click', e => { if (e.target === d) { const r = d.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close(); } });
  d.addEventListener('close', () => d.remove());
  return d;
}
function manageBook(id) {
  const b = books.find(x => x.id === id); let cover = b.cover || '';
  const d = dialog('整理这本书', `<form id="metadata-form"><label>书名<input name="title" value="${esc(b.title)}" required maxlength="300"></label><label>作者<input name="author" value="${esc(b.author)}" maxlength="300"></label><label>标签 <small>用逗号分隔</small><input name="tags" value="${esc((b.tags || []).join(', '))}" maxlength="500" placeholder="文学，生活，想再读一次"></label><div class="form-row"><label>阅读状态<select name="status"><option value="unread">未读</option><option value="reading" ${b.status === 'reading' ? 'selected' : ''}>在读</option><option value="finished" ${b.status === 'finished' ? 'selected' : ''}>已读完</option></select></label><label class="checkbox"><input type="checkbox" name="favorite" ${b.favorite ? 'checked' : ''}>加入收藏</label></div><label>更换封面<input id="cover-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif"></label><p class="muted">${esc(b.format.toUpperCase())} · ${(b.size / 1024 / 1024).toFixed(2)} MB · 书库编辑不会覆盖原文件</p><div class="dialog-actions"><button type="button" id="convert-book" class="secondary">${icon('download')}转换 / 导出</button><button class="primary" type="submit">保存修改</button></div></form><button id="remove-book" class="danger text-button">从书库删除</button>`);
  d.querySelector('#cover-input').onchange = e => run(async () => { if (e.target.files[0]) { cover = await coverImage(e.target.files[0]); toast('封面已选择，保存后生效'); } });
  d.querySelector('#metadata-form').onsubmit = e => { e.preventDefault(); run(async () => {
    const data = new FormData(e.target), title = data.get('title').trim(); if (!title) throw new Error('请输入书名');
    Object.assign(b, { title, author: data.get('author').trim(), tags: data.get('tags').split(/[,，]/).map(x => x.trim()).filter(Boolean), status: data.get('status'), favorite: data.has('favorite'), cover });
    await store.saveBook(b); d.close(); if (!active) shell(); toast('已保存');
  }); };
  d.querySelector('#convert-book').onclick = () => { d.close(); conversionDialog(b); };
  d.querySelector('#remove-book').onclick = () => {
    d.close(); const confirm = dialog('删除这本书？', `<p>将从书库移除《${esc(b.title)}》以及它的标注。你导入前的原文件会保留。</p><div class="dialog-actions"><button id="cancel-delete" class="secondary">取消</button><button id="confirm-delete" class="danger-button">删除书籍</button></div>`);
    confirm.querySelector('#cancel-delete').onclick = () => confirm.close();
    confirm.querySelector('#confirm-delete').onclick = () => run(async () => { await store.removeBook(b.id); await reload(); confirm.close(); shell(); toast('已删除'); });
  };
}
function conversionDialog(b) {
  const d = dialog('转换与导出', `<p>《${esc(b.title)}》</p><label>导出方式<select id="export-format"><option value="original">下载原文件（原始内容与元数据）</option>${!b.audio ? ['epub', 'txt', 'html', 'fb2', 'rtf', 'docx'].map(x => `<option value="${x}">${x.toUpperCase()} · 文字转换</option>`).join('') : ''}</select></label><p class="muted">内置转换保留文字和段落，EPUB 可写入新书名与封面；图片、表格布局和标注不会写入转换结果。</p>${!b.audio && window.__TAURI_INTERNALS__ ? `<div class="converter-section"><label>桌面 calibre 转换<select id="calibre-format"><option value="mobi">MOBI</option><option value="pdf">PDF</option><option value="epub">EPUB</option><option value="docx">DOCX</option><option value="rtf">RTF</option><option value="fb2">FB2</option><option value="txt">TXT</option></select></label><p class="muted">需另装 calibre 或将免安装 calibre 放在程序旁的 calibre 文件夹。转换结果取决于原书格式。</p><button id="calibre-convert" class="secondary">使用 calibre 转换</button></div>` : ''}<div class="dialog-actions"><button id="do-export" class="primary">${icon('download')}导出文件</button></div>`);
  d.querySelector('#do-export').onclick = () => run(async () => {
    const button = d.querySelector('#do-export'); button.disabled = true; button.textContent = '正在导出…';
    try { const file = await store.getFile(b.id); await (await import('./transfer.js')).convert(file, b, d.querySelector('#export-format').value); toast('已生成导出文件'); d.close(); }
    finally { button.disabled = false; button.textContent = '导出文件'; }
  });
  const calibre = d.querySelector('#calibre-convert');
  if (calibre) calibre.onclick = () => run(async () => {
    calibre.disabled = true; calibre.textContent = '转换中…';
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      const file = await store.getFile(b.id), output = d.querySelector('#calibre-format').value;
      if (file.size > 100 * 1024 ** 2) throw new Error('桌面转换单文件上限为 100 MB');
      const data = await invoke('convert_book', { input: Array.from(new Uint8Array(await file.arrayBuffer())), from: b.format, to: output, title: b.title, author: b.author, cover: b.cover || null });
      (await import('./transfer.js')).download(new Blob([new Uint8Array(data)]), `${b.title.replace(/[<>:"/\\|?*]/g, '_')}.${output}`); d.close(); toast('转换完成');
    } finally { calibre.disabled = false; calibre.textContent = '使用 calibre 转换'; }
  });
}
async function openBook(id, location) {
  if (busy) return;
  busy = true;
  const b = books.find(x => x.id === id);
  try {
    active = b; currentNotes = await store.bookNotes(id); const file = await store.getFile(id);
    if (!file) throw new Error('原文件缺失，请从备份恢复');
    app.innerHTML = `<div class="reader-shell theme-${settings.theme}"><header class="reader-header"><button class="icon-button" data-action="back" aria-label="返回书库">${icon('back')}</button><div class="reader-book-title"><strong>${esc(b.title)}</strong><small>${esc(b.author || b.format.toUpperCase())}</small></div><div class="reader-tools">${btn('toc', '目录', 'list')}${btn('reader-search', '搜索', 'search')}${btn('annotate', '标注', 'note')}${btn('bookmark', '书签', 'bookmark')}${btn('appearance', '排版', 'settings')}</div></header><main id="reading-stage"><div class="reader-loading">正在翻开这本书…</div></main><footer class="reader-footer"><button data-action="prev" class="icon-button prev" aria-label="上一页">${icon('chevron')}</button><span id="location-label">正在加载</span><input id="reading-progress" type="range" min="0" max="1" step="0.001" aria-label="阅读进度"><span id="progress-label">${progress(b)}%</span><button data-action="next" class="icon-button" aria-label="下一页">${icon('chevron')}</button></footer></div>`;
    reader = await createReader(document.querySelector('#reading-stage'), file, b, currentNotes, {
      settings: () => settings, keydown: readerKey, error,
      relocate: info => {
        if (active?.id !== id) return;
        Object.assign(b, info, { lastRead: Date.now(), status: b.status === 'finished' ? 'finished' : 'reading' });
        document.querySelector('#location-label').textContent = info.label;
        document.querySelector('#reading-progress').value = info.progress;
        document.querySelector('#progress-label').textContent = `${progress(b)}%`;
        clearTimeout(persistTimer); persistTimer = setTimeout(() => run(() => store.saveBook(b)), 400);
      },
    });
    document.querySelector('#reading-progress').oninput = e => run(() => reader.seek(Number(e.target.value)));
    if (location) await reader.goTo(location.value ?? location.page ?? location.seconds);
  } catch (e) { reader?.close(); reader = null; active = null; shell(); throw e; }
  finally { busy = false; }
}
async function closeReader() {
  if (busy) return;
  clearTimeout(persistTimer);
  const closingBook = active, closingReader = reader;
  if (closingBook) await store.saveBook(closingBook);
  active = null; reader = null;
  // PDF worker teardown can finish independently after navigation.
  const cleanup = closingReader?.close(); cleanup?.catch?.(error);
  await reload(); shell();
}
function readerKey(e) {
  if (!active || !reader || e.ctrlKey || e.metaKey || e.altKey || document.querySelector('dialog[open]') || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.target.isContentEditable) return;
  if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); run(() => reader.next()); }
  if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); run(() => reader.prev()); }
}
document.addEventListener('keydown', readerKey);
function annotationDialog(bookmark = false) {
  if (!reader) return;
  const selection = bookmark ? reader.location() : reader.selected();
  if (!selection?.quote) { toast('请先在正文中选中文字，再点击“标注”'); return; }
  const d = dialog(bookmark ? '留下一个书签' : '记下此刻的想法', `<blockquote class="selected-quote">${esc(selection.quote.slice(0, 4000))}</blockquote><form id="note-form"><label>笔记<textarea name="note" rows="4" maxlength="10000" placeholder="是什么触动了你？（可留空）"></textarea></label><div class="dialog-actions"><button class="primary" type="submit">保存${bookmark ? '书签' : '标注'}</button></div></form>`);
  d.querySelector('form').onsubmit = e => { e.preventDefault(); run(async () => {
    const note = { ...selection, quote: selection.quote.slice(0, 4000), id: crypto.randomUUID(), bookId: active.id, note: new FormData(e.target).get('note'), created: Date.now(), bookmark };
    await store.saveNote(note); currentNotes.push(note); notes.push(note); await reader.addAnnotation(note); d.close(); toast('已保存，可在“目录”中查看');
  }); };
}
function tocDialog() {
  if (!reader) return;
  const flat = (items, level = 0) => items.flatMap(item => [{ ...item, level }, ...flat(item.subitems || [], level + 1)]);
  const items = flat(reader.toc);
  const d = dialog('目录与标注', `<div class="reader-index"><p class="eyebrow">目录</p>${items.length ? items.map((item, i) => `<button data-toc="${i}" style="padding-left:${12 + item.level * 16}px">${esc(item.label)}</button>`).join('') : '<p class="muted">这本书没有目录</p>'}<p class="eyebrow">标注与书签 · ${currentNotes.length}</p>${currentNotes.map((n, i) => `<div class="index-note"><button data-jump-note="${i}"><strong>${esc(n.quote)}</strong><small>${esc(n.note)}</small></button><button data-remove-note="${i}" class="icon-button" aria-label="删除标注">${icon('close')}</button></div>`).join('')}</div>`);
  d.querySelectorAll('[data-toc]').forEach(el => { el.onclick = () => run(async () => { await reader.goTo(items[Number(el.dataset.toc)].href); d.close(); }); });
  d.querySelectorAll('[data-jump-note]').forEach(el => { el.onclick = () => run(async () => { const n = currentNotes[Number(el.dataset.jumpNote)]; await reader.goTo(n.value ?? n.page ?? n.seconds); d.close(); }); });
  d.querySelectorAll('[data-remove-note]').forEach(el => { el.onclick = () => run(async () => { await removeNote(currentNotes[Number(el.dataset.removeNote)].id); d.close(); tocDialog(); }); });
}
async function removeNote(id) {
  const note = notes.find(n => n.id === id); await store.deleteNote(id);
  notes = notes.filter(n => n.id !== id); currentNotes.splice(0, currentNotes.length, ...currentNotes.filter(n => n.id !== id));
  await reader?.removeAnnotation(note); if (!active) shell();
}
function searchDialog() {
  const d = dialog('在书中搜索', '<form id="book-search"><label>搜索文字<input name="query" required maxlength="200" placeholder="输入想寻找的句子或词语" autocomplete="off"></label><button class="primary" type="submit">搜索</button></form><div id="search-results" class="reader-index"></div>');
  d.querySelector('form').onsubmit = e => { e.preventDefault(); run(async () => {
    const resultArea = d.querySelector('#search-results'); resultArea.textContent = '正在查找…';
    const query = new FormData(e.target).get('query').trim(); if (!query) return;
    const results = await reader.search(query);
    resultArea.innerHTML = `<p class="muted">${results.length ? `找到 ${results.length} 处（最多显示 100 处）` : '没有找到匹配内容'}</p>` + results.map((r, i) => `<button data-search-hit="${i}"><small>${esc(r.label || '')}</small>${esc(r.excerpt)}</button>`).join('');
    resultArea.querySelectorAll('[data-search-hit]').forEach(el => { el.onclick = () => run(async () => { await reader.goTo(results[Number(el.dataset.searchHit)].href); d.close(); }); });
  }); };
}
function appearance() {
  const d = dialog('舒服地读下去', `<form id="appearance-form"><div class="form-row"><label>字号 <output id="font-size-value">${settings.size}px</output><input name="size" type="range" min="14" max="36" value="${settings.size}"></label><label>行距<select name="spacing">${[1.4, 1.6, 1.8, 2, 2.2].map(x => `<option ${settings.spacing === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label></div><label>字体<select name="font"><option value="serif" ${settings.font === 'serif' ? 'selected' : ''}>衬线 · 宋体 / 系统衬线</option><option value="sans-serif" ${settings.font === 'sans-serif' ? 'selected' : ''}>无衬线 · 黑体 / 系统无衬线</option><option value="monospace" ${settings.font === 'monospace' ? 'selected' : ''}>等宽字体</option></select></label><div class="form-row"><label>阅读主题<select name="theme"><option value="paper" ${settings.theme === 'paper' ? 'selected' : ''}>暖纸</option><option value="light" ${settings.theme === 'light' ? 'selected' : ''}>明亮</option><option value="dark" ${settings.theme === 'dark' ? 'selected' : ''}>夜读</option></select></label><label>翻页方式<select name="flow"><option value="paginated" ${settings.flow === 'paginated' ? 'selected' : ''}>左右翻页</option><option value="scrolled" ${settings.flow === 'scrolled' ? 'selected' : ''}>连续滚动</option></select></label></div><div class="form-row"><label>分栏<select name="columns"><option value="1" ${settings.columns === '1' ? 'selected' : ''}>单栏</option><option value="2" ${settings.columns === '2' ? 'selected' : ''}>双栏（宽屏）</option></select></label><label>PDF 缩放<select name="zoom">${[0.75, 1, 1.25, 1.5, 2].map(x => `<option value="${x}" ${settings.zoom === x ? 'selected' : ''}>${x * 100}%</option>`).join('')}</select></label></div><label>TXT 编码（重新打开书籍后生效）<select name="encoding">${[['auto', '自动识别 UTF-8 / UTF-16 / GB18030'], ['utf-8', 'UTF-8'], ['gb18030', 'GB18030 / GBK'], ['big5', 'Big5'], ['utf-16le', 'UTF-16 LE']].map(([v, label]) => `<option value="${v}" ${settings.encoding === v ? 'selected' : ''}>${label}</option>`).join('')}</select></label><label class="checkbox"><input name="justify" type="checkbox" ${settings.justify ? 'checked' : ''}>正文两端对齐</label><p class="muted">字号、行距和分栏适用于流式书籍；PDF 保持原版式，使用缩放调整。</p></form>`);
  d.querySelector('form').oninput = e => { const data = new FormData(e.currentTarget); run(async () => {
    Object.assign(settings, Object.fromEntries(data));
    for (const key of ['size', 'spacing', 'zoom']) settings[key] = Number(settings[key]); settings.justify = data.has('justify');
    localStorage.setItem('exreader-settings', JSON.stringify(settings));
    d.querySelector('#font-size-value').textContent = `${settings.size}px`;
    if (active) { document.querySelector('.reader-shell').className = `reader-shell theme-${settings.theme}`; await reader?.apply(); }
  }); };
}
function preferences() {
  const d = dialog('你的阅读空间', `<p class="settings-intro">EXReader <small>0.1.0</small></p><p>书籍、封面、进度与标注保存在本机。浏览器版的书库与桌面版相互独立，可使用备份迁移。</p><div class="settings-actions">${btn('appearance', '默认阅读排版', 'settings', 'secondary')}${btn('backup', '导出整个书库', 'download', 'secondary')}${btn('restore', '从备份恢复 / 合并', 'upload', 'secondary')}</div><p class="muted">恢复会按书籍 ID 合并，同 ID 的书籍与标注会被备份内容覆盖。浏览器清除站点数据会移除本地书库，请定期备份。</p><div class="platform-note"><strong>随手打开，随处阅读</strong><p>浏览器版适用于 Windows、Linux、macOS、Android、iOS 和 iPadOS。手机或平板可通过浏览器菜单“添加到主屏幕”使用；离线功能在首次完整缓存后可用。</p></div><p class="muted">阅读引擎：Foliate · PDF.js · Mammoth · rtf.js。所有解析在本机完成。</p>`);
  d.querySelectorAll('[data-action]').forEach(el => { el.onclick = () => { const action = el.dataset.action; d.close(); run(() => actions[action]()); }; });
}
const actions = {
  import: () => { if (active) return; document.querySelector('#file-input').click(); },
  settings: preferences, appearance, back: closeReader,
  prev: () => reader?.prev(), next: () => reader?.next(), toc: tocDialog,
  annotate: () => annotationDialog(), bookmark: () => annotationDialog(true), 'reader-search': searchDialog,
  backup: async () => { toast('正在打包书库…'); await (await import('./transfer.js')).backup(); toast('书库备份已生成'); },
  restore: () => document.querySelector('#restore-input').click(),
  'export-notes': async () => (await import('./transfer.js')).notesExport(notes, books),
  sample: () => importFiles([new File([sampleText], '给阅读留一点时间.txt', { type: 'text/plain' })]),
};
app.addEventListener('click', e => {
  const target = e.target.closest('button'); if (!target) return;
  if (target.dataset.tab) { tab = target.dataset.tab; query = ''; shell(); }
  else if (target.dataset.layout) { layout = target.dataset.layout; renderContent(); }
  else if (target.dataset.open) run(() => openBook(target.dataset.open));
  else if (target.dataset.edit) manageBook(target.dataset.edit);
  else if (target.dataset.noteOpen) { const n = notes.find(x => x.id === target.dataset.noteOpen); run(() => openBook(n.bookId, n)); }
  else if (target.dataset.noteDelete) run(() => removeNote(target.dataset.noteDelete));
  else if (target.dataset.action && actions[target.dataset.action]) run(() => actions[target.dataset.action]());
});
let dragDepth = 0;
document.addEventListener('dragenter', e => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); dragDepth++; document.body.classList.add('dragging'); } });
document.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove('dragging'); } });
document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => { e.preventDefault(); dragDepth = 0; document.body.classList.remove('dragging'); if (active) toast('请先返回书库，再导入书籍'); else importFiles(e.dataTransfer.files); });
document.addEventListener('visibilitychange', () => { if (document.hidden && active) { clearTimeout(persistTimer); run(() => store.saveBook(active)); } });
const sampleText = `给阅读留一点时间\n\n一\n\n窗外的风经过树梢，书页上的光慢慢移动。你不必急着读完，也不必记住每一句话。翻开一本书，本来就可以只为了眼前这一小段安静。\n\n这是 EXReader 的原创示例文章。试着选中这段文字，点击上方的“标注”，记下你的想法。下次再打开，它仍会留在这里。\n\n二\n\n我们常常把阅读想成一段需要完成的路：这个月读几本，今年读多少页。但真正留在心里的，也许只是某个清晨读到的一个比喻，或者旅途中偶然翻过的一页。\n\n一本书的价值，有时不在结尾，而在它让你停下来的那个瞬间。你开始注意到一棵树的影子，开始愿意听一个人把故事说完，开始重新理解某段熟悉的生活。\n\n三\n\n给阅读留一点时间，不需要安排一个完美的下午。可以是等车的十分钟，是睡前的小半个小时，是雨停之前的一点空隙。\n\n让字体大一点，让行距宽一点。白天读不完的，留给夜晚。没有读懂的地方，留给下次。阅读可以有自己的速度，生活也是。\n\n四\n\n你可以把这篇文章转换成 EPUB、TXT、FB2、RTF 或 DOCX，试试不同的阅读方式。也可以改一张封面，换一个书名，给它加上“想再读一次”的标签。\n\n书库不需要装得很多。几本真正喜欢的书，就足够让一个角落变得温暖。\n\n现在，合上这篇示例，把你喜欢的第一本书带进来吧。`;
run(async () => { await reload(); shell(); });
if ('serviceWorker' in navigator && import.meta.env.PROD && !window.__TAURI_INTERNALS__) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(error));
