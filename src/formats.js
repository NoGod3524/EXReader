import DOMPurify from 'dompurify';
DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
  const resource = ['src', 'poster', 'background', 'xlink:href'].includes(data.attrName) || data.attrName === 'href' && ['link', 'image', 'use'].includes(node.nodeName.toLowerCase());
  if (resource && /^(?:https?:|\/\/)/i.test(data.attrValue.trim())) data.keepAttr = false;
});
export const BOOK_EXTENSIONS = ['pdf', 'epub', 'fb2', 'txt', 'rtf', 'mobi', 'azw3', 'docx'];
export const AUDIO_EXTENSIONS = ['mp3', 'm4a', 'm4b', 'ogg', 'opus', 'wav', 'flac', 'aac'];
export const extension = name => name.split('.').pop().toLowerCase();
export const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
export const titleOf = value => typeof value === 'string' ? value : value?.name ? titleOf(value.name) : value ? Object.values(value)[0] || '' : '';
export const authorOf = value => (Array.isArray(value) ? value : [value]).map(titleOf).filter(Boolean).join('、');
export const foliate = () => import('../vendor/foliate/view.js');
export function cleanHTML(html, whole = false) {
  return DOMPurify.sanitize(html, {
    WHOLE_DOCUMENT: whole,
    ADD_TAGS: ['link'],
    ADD_ATTR: ['xmlns', 'epub:type'],
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'base', 'meta'],
    FORBID_ATTR: ['srcdoc', 'srcset', 'autofocus', 'action', 'formaction'],
  });
}
export function protectBook(book) {
  book.transformTarget?.addEventListener('data', ({ detail }) => {
    if (/html/.test(detail.type)) {
      detail.data = Promise.resolve(detail.data).then(async data => {
        const html = typeof data === 'string' ? data : await data.text();
        const clean = cleanHTML(html, true);
        return /xhtml/.test(detail.type) ? new XMLSerializer().serializeToString(new DOMParser().parseFromString(clean, 'text/html')) : clean;
      });
    }
  });
  return book;
}
export async function decodeText(file, encoding = 'auto') {
  const data = await file.arrayBuffer();
  if (encoding !== 'auto') return new TextDecoder(encoding).decode(data);
  const bytes = new Uint8Array(data);
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder('utf-16le').decode(data);
  if (bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder('utf-16be').decode(data);
  try { return new TextDecoder('utf-8', { fatal: true }).decode(data); }
  catch { return new TextDecoder('gb18030').decode(data); }
}
function htmlBook(html, title) {
  const clean = cleanHTML(html);
  const doc = new DOMParser().parseFromString(clean, 'text/html');
  // Split long documents at block boundaries so pagination does not lay out an entire novel.
  const chapters = []; let content = '', length = 0;
  for (const node of doc.body.childNodes) {
    const markup = node.outerHTML || escapeHTML(node.textContent);
    if (length > 18000 && node.nodeName !== '#text') { chapters.push(content); content = ''; length = 0; }
    content += markup; length += node.textContent.length;
  }
  if (content || !chapters.length) chapters.push(content);
  const urls = [];
  const sections = chapters.map((part, i) => ({
    id: String(i), size: part.length,
    load() { return urls[i] ||= URL.createObjectURL(new Blob([`<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>${escapeHTML(title)}</title></head><body>${part}</body></html>`], { type: 'text/html' })); },
    createDocument: () => new DOMParser().parseFromString(part, 'text/html'),
  }));
  return {
    sections, metadata: { title, language: 'zh' },
    toc: sections.map((_, i) => ({ label: chapters.length > 1 ? `第 ${i + 1} 节` : title, href: String(i) })),
    resolveHref: href => ({ index: Number(String(href).split('#')[0]) || 0 }),
    splitTOCHref: href => [String(href).split('#')[0]],
    getTOCFragment: doc => doc.body,
    isExternal: href => /^\w+:/i.test(href),
    destroy: () => urls.forEach(url => URL.revokeObjectURL(url)),
  };
}
export async function openReflow(file, encoding) {
  const ext = extension(file.name);
  const title = file.name.replace(/\.[^.]+$/, '');
  if (ext === 'txt') {
    const text = await decodeText(file, encoding);
    return htmlBook(text.split(/\r?\n/).map(line => `<p>${escapeHTML(line) || '<br>'}</p>`).join(''), title);
  }
  if (ext === 'docx') {
    const mammoth = await import('mammoth/mammoth.browser');
    const result = await (mammoth.default || mammoth).convertToHtml({ arrayBuffer: await file.arrayBuffer() });
    return htmlBook(result.value, title);
  }
  if (ext === 'rtf') {
    const module = await import('rtf.js');
    const { RTFJS } = module.default || module;
    RTFJS.loggingEnabled(false);
    const doc = new RTFJS.Document(await file.arrayBuffer(), {});
    return htmlBook((await doc.render()).map(el => el.outerHTML).join(''), titleOf(doc.metadata()?.title) || title);
  }
  const { makeBook } = await foliate();
  return protectBook(await makeBook(file));
}
export async function readMetadata(file) {
  const ext = extension(file.name);
  const base = { title: file.name.replace(/\.[^.]+$/, ''), author: '', format: ext, audio: AUDIO_EXTENSIONS.includes(ext) };
  if (base.audio || ['txt', 'rtf', 'docx', 'pdf'].includes(ext)) return base;
  const book = await openReflow(file);
  try {
    const cover = await book.getCover?.();
    let thumbnail = '';
    if (cover) { try { thumbnail = await coverImage(cover, true); } catch { /* A broken cover must not prevent importing the book. */ } }
    return { ...base, title: titleOf(book.metadata?.title) || base.title, author: authorOf(book.metadata?.author), cover: thumbnail };
  } finally { book.destroy?.(); }
}
export async function coverImage(file, embedded = false) {
  if (!embedded && !/^image\/(png|jpeg|webp|gif)$/.test(file.type)) throw new Error('封面请选择 PNG、JPEG、WebP 或 GIF 图片');
  const url = URL.createObjectURL(file), img = new Image();
  try {
    img.src = url; await img.decode();
    const ratio = Math.min(1, 600 / img.naturalWidth, 900 / img.naturalHeight);
    const canvas = document.createElement('canvas'); canvas.width = Math.round(img.naturalWidth * ratio); canvas.height = Math.round(img.naturalHeight * ratio);
    const ctx = canvas.getContext('2d'); ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
  } finally { URL.revokeObjectURL(url); }
}
