import { zipSync, unzipSync, strToU8, strFromU8 } from 'fflate';
import * as store from './store.js';
import { escapeHTML as esc, openReflow, BOOK_EXTENSIONS, AUDIO_EXTENSIONS } from './formats.js';

export function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
const safeName = name => name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').slice(0, 160) || 'book';
export async function backup() {
  const books = await store.allBooks(), notes = await store.allNotes();
  const metadata = strToU8(JSON.stringify({ version: 1, books, notes }));
  if (books.reduce((sum, b) => sum + b.size, metadata.length) > 1024 ** 3 - 1024 ** 2) throw new Error('当前整体备份上限为 1 GB，请先导出大体积音频原文件');
  const files = { 'library.json': metadata };
  for (const book of books) files[`files/${book.id}`] = new Uint8Array(await (await store.getFile(book.id)).arrayBuffer());
  download(new Blob([zipSync(files, { level: 0 })], { type: 'application/zip' }), `EXReader-${new Date().toISOString().slice(0, 10)}.zip`);
}
export async function restoreBackup(file) {
  if (file.size > 1024 ** 3) throw new Error('单次恢复上限为 1 GB');
  let expanded = 0;
  const files = unzipSync(new Uint8Array(await file.arrayBuffer()), { filter: entry => {
    expanded += entry.originalSize;
    if (expanded > 2 * 1024 ** 3) throw new Error('备份解压后超过 2 GB');
    return true;
  } });
  if (!files['library.json']) throw new Error('不是 EXReader 书库备份');
  const data = JSON.parse(strFromU8(files['library.json']));
  if (data.version !== 1 || !Array.isArray(data.books) || !Array.isArray(data.notes)) throw new Error('备份版本或结构不正确');
  const ids = new Set();
  for (const b of data.books) {
    if (typeof b.id !== 'string' || !/^[\w-]{1,100}$/.test(b.id) || ids.has(b.id) || typeof b.title !== 'string' || typeof b.filename !== 'string' || typeof b.format !== 'string' || !files[`files/${b.id}`]) throw new Error('备份缺少原书或元数据无效');
    if (b.cover && !/^data:image\/(png|jpeg|webp|gif);base64,/.test(b.cover)) throw new Error('备份封面无效');
    if (![...BOOK_EXTENSIONS, ...AUDIO_EXTENSIONS].includes(b.format) || typeof b.author !== 'string' || !Array.isArray(b.tags) || !b.tags.every(t => typeof t === 'string') || !Number.isFinite(b.added) || !Number.isFinite(b.progress) || b.progress < 0 || b.progress > 1 || !['unread', 'reading', 'finished'].includes(b.status)) throw new Error('备份书籍字段无效');
    ids.add(b.id);
  }
  for (const n of data.notes) {
    if (typeof n.id !== 'string' || !ids.has(n.bookId) || typeof n.quote !== 'string' || typeof n.note !== 'string') throw new Error('备份标注无效');
    if (!Number.isFinite(n.created) || n.value !== undefined && typeof n.value !== 'string' || n.page !== undefined && (!Number.isInteger(n.page) || n.page < 1) || n.seconds !== undefined && (!Number.isFinite(n.seconds) || n.seconds < 0)) throw new Error('备份标注位置无效');
    if (n.rects !== undefined && (!Array.isArray(n.rects) || n.rects.length > 20000 || !n.rects.every(r => ['x', 'y', 'w', 'h'].every(k => Number.isFinite(r[k]) && r[k] >= -0.01 && r[k] <= 1.01)))) throw new Error('备份标注范围无效');
  }
  await store.restore(data.books, data.books.map(b => new File([files[`files/${b.id}`]], b.filename, { lastModified: b.modified || b.added })), data.notes);
  return data.books.length;
}
export function notesExport(notes, books) {
  const text = notes.map(n => `## ${books.find(b => b.id === n.bookId)?.title || ''}\n\n> ${n.quote.replace(/\n/g, '\n> ')}\n\n${n.note}\n\n${new Date(n.created).toLocaleString()}\n`).join('\n');
  download(new Blob([text], { type: 'text/markdown;charset=utf-8' }), 'EXReader-标注.md');
}
async function paragraphs(file, book) {
  if (book.audio) throw new Error('有声书不能转换为电子书');
  if (book.format === 'pdf') {
    const { loadPDF } = await import('./pdf.js');
    const pdf = await loadPDF(file); const result = [];
    try {
      for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i), content = await page.getTextContent();
        let line = '';
        for (const item of content.items) { line += item.str || ''; if (item.hasEOL) { result.push(line); line = ''; } else line += ' '; }
        if (line.trim()) result.push(line);
      }
    } finally { await pdf.destroy(); }
    if (!result.some(x => x.trim())) throw new Error('这是扫描 PDF，转换前需要 OCR');
    return result;
  }
  const parsed = await openReflow(file);
  try {
    const result = [];
    for (const section of parsed.sections) {
      if (!section.createDocument || section.linear === 'no') continue;
      const doc = await section.createDocument();
      const blocks = doc.body.querySelectorAll('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,td');
      result.push(...(blocks.length ? Array.from(blocks, n => n.textContent.trim()) : [doc.body.textContent.trim()]).filter(Boolean));
    }
    return result;
  } finally { parsed.destroy?.(); }
}
export async function convert(file, book, format) {
  if (format === 'original') { download(file, safeName(book.title) + '.' + book.format); return; }
  const lines = await paragraphs(file, book);
  const body = `<h1>${esc(book.title)}</h1>` + lines.map(x => `<p>${esc(x)}</p>`).join('\n');
  let blob;
  if (format === 'txt') blob = new Blob([book.title + '\n\n' + lines.join('\n\n')], { type: 'text/plain;charset=utf-8' });
  else if (format === 'html') blob = new Blob([`<!doctype html><html lang="zh"><meta charset="utf-8"><title>${esc(book.title)}</title><body>${body}</body></html>`], { type: 'text/html' });
  else if (format === 'fb2') blob = new Blob([`<?xml version="1.0" encoding="utf-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info><genre>unrecognised</genre><author><nickname>${esc(book.author)}</nickname></author><book-title>${esc(book.title)}</book-title><lang>zh</lang></title-info></description><body><section><title><p>${esc(book.title)}</p></title>${lines.map(x => `<p>${esc(x)}</p>`).join('')}</section></body></FictionBook>`], { type: 'application/x-fictionbook+xml' });
  else if (format === 'rtf') {
    const rtfText = text => text.replace(/[\\{}]|[^\x20-\x7e\n]/g, ch => /[\\{}]/.test(ch) ? '\\' + ch : `\\u${ch.charCodeAt(0) > 32767 ? ch.charCodeAt(0) - 65536 : ch.charCodeAt(0)}?`).replace(/\n/g, '\\par\n');
    blob = new Blob([`{\\rtf1\\ansi\\deff0\\uc1 ${rtfText(book.title + '\n\n' + lines.join('\n\n'))}}`], { type: 'application/rtf' });
  } else if (format === 'docx') {
    const files = {
      '[Content_Types].xml': strToU8('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'),
      '_rels/.rels': strToU8('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'),
      'word/document.xml': strToU8(`<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${[book.title, ...lines].map(x => `<w:p><w:r><w:t xml:space="preserve">${esc(x)}</w:t></w:r></w:p>`).join('')}<w:sectPr/></w:body></w:document>`),
    };
    blob = new Blob([zipSync(files)], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
  } else if (format === 'epub') {
    const files = {
      mimetype: [strToU8('application/epub+zip'), { level: 0 }],
      'META-INF/container.xml': strToU8('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'),
      'OEBPS/nav.xhtml': strToU8(`<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title></head><body><nav epub:type="toc"><ol><li><a href="text.xhtml">${esc(book.title)}</a></li></ol></nav></body></html>`),
      'OEBPS/text.xhtml': strToU8(`<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" lang="zh"><head><title>${esc(book.title)}</title></head><body>${body}</body></html>`),
    };
    let coverItem = '', coverMeta = '', coverPage = '', coverSpine = '';
    if (book.cover) {
      const header = book.cover.match(/^data:(image\/(?:jpeg|png|webp|gif));base64,/);
      if (!header) throw new Error('封面数据无效，请重新选择封面');
      const b = new Blob([Uint8Array.from(atob(book.cover.slice(header[0].length)), ch => ch.charCodeAt(0))], { type: header[1] });
      files['OEBPS/cover.jpg'] = new Uint8Array(await b.arrayBuffer());
      files['OEBPS/cover.xhtml'] = strToU8('<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>封面</title></head><body><img src="cover.jpg" alt="封面" style="max-width:100%;max-height:95vh"/></body></html>');
      coverItem = `<item id="cover" href="cover.jpg" media-type="${b.type}" properties="cover-image"/>`;
      coverMeta = '<meta name="cover" content="cover"/>';
      coverPage = '<item id="coverpage" href="cover.xhtml" media-type="application/xhtml+xml"/>';
      coverSpine = '<itemref idref="coverpage"/>';
    }
    files['OEBPS/book.opf'] = strToU8(`<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:uuid:${book.id}</dc:identifier><dc:title>${esc(book.title)}</dc:title><dc:creator>${esc(book.author)}</dc:creator><dc:language>zh</dc:language><meta property="dcterms:modified">${new Date().toISOString().replace(/\.\d+Z$/, 'Z')}</meta>${coverMeta}</metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/>${coverItem}${coverPage}</manifest><spine>${coverSpine}<itemref idref="text"/></spine></package>`);
    blob = new Blob([zipSync(files)], { type: 'application/epub+zip' });
  } else throw new Error('请选择支持的导出格式');
  download(blob, `${safeName(book.title)}.${format}`);
}
