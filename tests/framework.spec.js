import { test, expect } from '@playwright/test';
import { zipSync, strToU8 } from 'fflate';
import { text, epub, fb2, rtf, docx, mobi, pdf, wav } from './fixtures.js';

async function boot(page) {
  await page.goto('/tests/blank.html');
  await page.evaluate(async () => {
    window.core = await import('/src/index.js');
    window.library = core.createLibrary({ name: 'framework-test' });
  });
}
async function importFile(page, name, bytes) {
  return page.evaluate(async ({ name, bytes }) => library.importFile(new File([new Uint8Array(bytes)], name, { lastModified: 7 })), { name, bytes: [...Buffer.from(bytes)] });
}
test.beforeEach(async ({ page }) => boot(page));

test('headless bookshelf: isolated libraries, duplicates, metadata, progress, notes, backup, removal and restore', async ({ page }) => {
  const { book } = await importFile(page, 'story.txt', text);
  expect((await importFile(page, 'story.txt', text)).duplicate).toBe(true);
  const result = await page.evaluate(async id => {
    await Promise.all([
      library.updateBook(id, { title: '新书名', author: '作者', tags: ['文学'], favorite: true }),
      library.saveProgress(id, { progress: 0.4, cfi: 'epubcfi(/6/2!/4/2:1)' }),
    ]);
    await library.saveNote(id, { quote: '原文', note: '想法', value: 'epubcfi(/6/2!/4/2:1)' });
    const found = await library.listBooks({ query: '文学', filter: 'favorite' });
    const isolated = core.createLibrary({ name: 'another-library' });
    const other = await isolated.listBooks();
    await isolated.close();
    const backup = await library.createBackup();
    const markdown = await (await library.exportNotes()).text();
    await library.removeBook(id);
    const removed = [await library.listBooks(), await library.listNotes(), await library.getFile(id)];
    const restored = await library.restoreBackup(backup);
    await library.close();
    window.library = core.createLibrary({ name: 'framework-test' });
    return { found, other, removed, restored, books: await library.listBooks(), notes: await library.listNotes(), markdown, body: await (await library.getFile(id)).text(), elements: document.body.children.length };
  }, book.id);
  expect(result.found).toHaveLength(1);
  expect(result.found[0]).toMatchObject({ title: '新书名', author: '作者', progress: 0.4 });
  expect(result.other).toEqual([]);
  expect(result.removed).toEqual([[], [], undefined]);
  expect(result.restored).toBe(1);
  expect(result.books[0].title).toBe('新书名');
  expect(result.notes[0].note).toBe('想法');
  expect(result.markdown).toContain('原文');
  expect(result.body).toContain('EXReader test paragraph');
  expect(result.elements).toBe(0);
});

test('rejects invalid mutations and malicious HTML without creating application UI', async ({ page }) => {
  const { book } = await importFile(page, 'unsafe.html', '<p>safe text</p><script>window.attacked=1</script><img src="https://example.invalid/track">');
  const result = await page.evaluate(async id => {
    const failures = [];
    for (const action of [() => library.updateBook(id, { id: 'changed' }), () => library.updateBook(id, { title: '' }), () => library.saveProgress(id, { progress: 2 }), () => library.saveNote(id, { rects: [{ x: 0, y: 0, w: Infinity, h: 1 }] })]) {
      try { await action(); } catch { failures.push(true); }
    }
    const parsed = await core.openReflow(await library.getFile(id));
    const doc = await parsed.sections[0].createDocument();
    const sanitized = doc.body.innerHTML;
    parsed.destroy();
    return { failures, sanitized, attacked: window.attacked, elements: document.body.children.length };
  }, book.id);
  expect(result.failures).toHaveLength(4);
  expect(result.sanitized).toContain('safe text');
  expect(result.sanitized).not.toMatch(/script|example.invalid/);
  expect(result.attacked).toBeUndefined();
  expect(result.elements).toBe(0);
});

for (const [ext, bytes, needle] of [
  ['epub', epub(), 'EPUB reading works'], ['fb2', fb2, 'FB2 reading works'],
  ['fb2.zip', zipSync({ 'book.fb2': strToU8(fb2) }), 'FB2 reading works'],
  ['fbz', zipSync({ 'book.fb2': strToU8(fb2) }), 'FB2 reading works'],
  ['rtf', rtf, 'RTF reading works'], ['docx', docx, 'DOCX reading works'],
  ['mobi', mobi(), 'MOBI reading works'], ['txt', text, 'EXReader test paragraph'],
  ['html', '<p>HTML reading works</p>', 'HTML reading works'],
]) test(`parses ${ext} through the public API`, async ({ page }) => {
  const { book } = await importFile(page, 'BOOK.' + ext.toUpperCase(), bytes);
  const content = await page.evaluate(async id => {
    const parsed = await core.openReflow(await library.getFile(id));
    try { return (await parsed.sections[0].createDocument()).body.textContent; }
    finally { parsed.destroy?.(); }
  }, book.id);
  expect(content).toContain(needle);
});

test('renders EPUB and PDF using only a host-provided container', async ({ page }) => {
  const { book } = await importFile(page, 'sample.epub', epub());
  await page.evaluate(async id => {
    const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/src/render.css'; document.head.append(style);
    const stage = document.createElement('div'); stage.id = 'stage'; stage.style.cssText = 'width:800px;height:700px'; document.body.append(stage);
    window.reader = await core.createReader(stage, await library.getFile(id), await library.getBook(id));
  }, book.id);
  await expect.poll(() => page.evaluate(() => document.querySelector('foliate-view')?.renderer?.getContents().some(({ doc }) => doc.body.textContent.includes('EPUB reading works')))).toBe(true);
  await page.evaluate(async () => { await reader.close(); document.querySelector('#stage').replaceChildren(); });
  const pdfBook = (await importFile(page, 'sample.pdf', pdf())).book;
  await page.evaluate(async id => { window.reader = await core.createReader(document.querySelector('#stage'), await library.getFile(id), await library.getBook(id)); }, pdfBook.id);
  await expect(page.locator('.textLayer')).toContainText('EXReader PDF test');
  await page.evaluate(() => reader.next());
  expect(await page.evaluate(() => reader.location().page)).toBe(2);
  await page.evaluate(() => reader.close());
  expect(await page.evaluate(async id => (await library.exportBook(id, 'txt')).text(), pdfBook.id)).toContain('EXReader PDF test');
  await expect(page.locator('button, nav, dialog, aside')).toHaveCount(0);
});

test('exports every text format as a Blob without invoking a download dialog', async ({ page }) => {
  const { book } = await importFile(page, 'convert.txt', 'Roundtrip text.\n\n第二段');
  const results = await page.evaluate(async id => {
    const results = [];
    for (const ext of ['epub', 'txt', 'html', 'fb2', 'rtf', 'docx']) {
      const blob = await library.exportBook(id, ext);
      const parsed = await core.openReflow(new File([blob], 'roundtrip.' + ext));
      try { results.push({ ext, size: blob.size, text: (await parsed.sections[0].createDocument()).body.textContent }); }
      finally { parsed.destroy?.(); }
    }
    return results;
  }, book.id);
  expect(results).toHaveLength(6);
  for (const result of results) { expect(result.size).toBeGreaterThan(0); expect(result.text).toContain('Roundtrip text.'); }
});

test('CBZ uses the existing fixed-layout engine', async ({ page }) => {
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');
  const { book } = await importFile(page, 'comic.CBZ', zipSync({ '1.png': image, '2.png': image }));
  const result = await page.evaluate(async id => {
    const parsed = await core.openReflow(await library.getFile(id));
    const result = { pages: parsed.sections.length, layout: parsed.rendition.layout, toc: parsed.toc.length };
    parsed.destroy();
    return result;
  }, book.id);
  expect(result).toEqual({ pages: 2, layout: 'pre-paginated', toc: 2 });
});

test('audio exposes a controllable media element without player controls', async ({ page, browserName }) => {
  test.skip(browserName === 'webkit' && process.platform === 'win32', 'Windows WebKit cannot decode the PCM fixture.');
  const { book } = await importFile(page, 'audio.wav', wav());
  await page.evaluate(async id => {
    const stage = document.createElement('div'); document.body.append(stage);
    window.reader = await core.createReader(stage, await library.getFile(id), await library.getBook(id));
  }, book.id);
  await expect.poll(() => page.evaluate(() => reader.media.duration)).toBe(10);
  expect(await page.evaluate(() => reader.media.controls)).toBe(false);
  await page.evaluate(() => reader.goTo(4));
  expect(await page.evaluate(() => reader.location().seconds)).toBe(4);
  await page.evaluate(() => reader.close());
});

test('built ESM entry imports and runs without the source entry', async ({ page }) => {
  const result = await page.evaluate(async () => {
    const built = await import('/dist/exreader.js');
    const db = built.createLibrary({ name: 'built-framework' });
    const { book } = await db.importFile(new File(['Built entry text'], 'built.txt'));
    const blob = await db.exportBook(book.id, 'txt');
    const result = { text: await blob.text(), elements: document.body.children.length };
    await db.close();
    return result;
  });
  expect(result.text).toContain('Built entry text');
  expect(result.elements).toBe(0);
});

test('built PDF renderer loads a separate worker under a restrictive CSP', async ({ page }) => {
  await page.evaluate(async bytes => {
    const policy = document.createElement('meta'); policy.httpEquiv = 'Content-Security-Policy';
    policy.content = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self' blob: data:; connect-src 'self'; worker-src 'self' blob:; frame-src 'self' blob:; object-src 'none'";
    document.head.append(policy);
    const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = '/dist/exreader.css'; document.head.append(css);
    const stage = document.createElement('div'); stage.style.cssText = 'width:800px;height:700px'; document.body.append(stage);
    const built = await import('/dist/exreader.js');
    window.reader = await built.createReader(stage, new File([new Uint8Array(bytes)], 'built.pdf'), { format: 'pdf' });
  }, [...pdf()]);
  await expect(page.locator('.textLayer')).toContainText('EXReader PDF test');
  await page.evaluate(() => reader.close());
});
