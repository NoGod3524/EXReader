import { zipSync, strToU8 } from 'fflate';
export const text = 'EXReader test paragraph. 阅读让生活慢下来。\n\n第二段文字，可以高亮并添加笔记。\n\n' + '这是供翻页测试使用的段落。'.repeat(500);
export function epub(malicious = false) {
  return Buffer.from(zipSync({
    mimetype: [strToU8('application/epub+zip'), { level: 0 }],
    'META-INF/container.xml': strToU8('<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'),
    'book.opf': strToU8('<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">test</dc:identifier><dc:title>测试 EPUB</dc:title><dc:creator>测试作者</dc:creator><dc:language>zh</dc:language><meta property="dcterms:modified">2026-10-15T00:00:00Z</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="ch1" href="one.xhtml" media-type="application/xhtml+xml"/><item id="ch2" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="ch1"/><itemref idref="ch2"/></spine></package>'),
    'nav.xhtml': strToU8('<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>目录</title></head><body><nav epub:type="toc"><ol><li><a href="one.xhtml">第一章</a></li><li><a href="two.xhtml">第二章</a></li></ol></nav></body></html>'),
    'one.xhtml': strToU8(`<html xmlns="http://www.w3.org/1999/xhtml"><head><title>第一章</title></head><body><h1>第一章</h1><p>EPUB reading works. 阅读开始了。</p>${malicious ? '<script>parent.localStorage.setItem("attacked","yes")</script><img src="https://example.invalid/track" onerror="parent.localStorage.setItem(\'attacked\',\'yes\')"/>' : ''}<p>${'一页一页地读下去。'.repeat(300)}</p></body></html>`),
    'two.xhtml': strToU8('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>第二章</title></head><body><h1>第二章</h1><p>Second chapter unique text.</p></body></html>'),
  }));
}
export const fb2 = Buffer.from('<?xml version="1.0" encoding="UTF-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description><title-info><genre>prose</genre><author><first-name>测试</first-name><last-name>作者</last-name></author><book-title>测试 FB2</book-title><lang>zh</lang></title-info></description><body><section><title><p>FB2 章节</p></title><p>FB2 reading works. 安静地读一本书。</p></section></body></FictionBook>');
export const rtf = Buffer.from('{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Times New Roman;}}\\f0\\fs24 RTF reading works.\\par Another paragraph.}');
export const docx = Buffer.from(zipSync({
  '[Content_Types].xml': strToU8('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'),
  '_rels/.rels': strToU8('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'),
  'word/document.xml': strToU8('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DOCX reading works. 文档阅读。</w:t></w:r></w:p><w:sectPr/></w:body></w:document>'),
}));
export function mobi() {
  const title = Buffer.from('MOBI Test'), html = Buffer.from('<html><head><title>MOBI Test</title></head><body><h1>MOBI reading works.</h1><p>Original fixture without DRM.</p></body></html>');
  const pdb = Buffer.alloc(96), record = Buffer.alloc(248 + title.length);
  pdb.write('EXReader MOBI fixture'); pdb.write('BOOKMOBI', 60); pdb.writeUInt16BE(2, 76);
  pdb.writeUInt32BE(pdb.length, 78); pdb.writeUInt32BE(pdb.length + record.length, 86);
  record.writeUInt16BE(1, 0); record.writeUInt32BE(html.length, 4); record.writeUInt16BE(1, 8); record.writeUInt16BE(4096, 10);
  record.write('MOBI', 16); record.writeUInt32BE(232, 20); record.writeUInt32BE(2, 24); record.writeUInt32BE(65001, 28); record.writeUInt32BE(6, 36);
  record.writeUInt32BE(248, 84); record.writeUInt32BE(title.length, 88); record.writeUInt32BE(9, 92); record.writeUInt32BE(2, 108); record.writeUInt32BE(0xffffffff, 244);
  title.copy(record, 248);
  return Buffer.concat([pdb, record, html]);
}
export function pdf() {
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>'];
  const stream = s => `<< /Length ${s.length} >>\nstream\n${s}\nendstream`;
  objects.push(stream('BT /F1 24 Tf 50 700 Td (EXReader PDF test page one) Tj ET'));
  objects.push('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>');
  objects.push(stream('BT /F1 24 Tf 50 700 Td (Second page searchable words) Tj ET'));
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  let content = '%PDF-1.4\n', offsets = [0];
  objects.forEach((o, i) => { offsets.push(content.length); content += `${i + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = content.length;
  content += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n` + offsets.slice(1).map(o => String(o).padStart(10, '0') + ' 00000 n \n').join('') + `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(content);
}
export function wav() {
  const data = Buffer.alloc(44 + 16000 * 10);
  data.write('RIFF', 0); data.writeUInt32LE(data.length - 8, 4); data.write('WAVEfmt ', 8); data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22); data.writeUInt32LE(8000, 24); data.writeUInt32LE(16000, 28); data.writeUInt16LE(2, 32); data.writeUInt16LE(16, 34); data.write('data', 36); data.writeUInt32LE(data.length - 44, 40); return data;
}
