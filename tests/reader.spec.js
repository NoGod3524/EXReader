import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { unzipSync, strFromU8 } from 'fflate';
import { text, epub, fb2, rtf, docx, mobi, pdf, wav } from './fixtures.js';

async function importBook(page, name, buffer) {
  await page.locator('#file-input').setInputFiles({ name, mimeType: 'application/octet-stream', buffer: Buffer.isBuffer(buffer) ? buffer : Buffer.from(buffer) });
  await expect(page.locator('.book-card')).toHaveCount(1);
}
const open = page => page.locator('.book-card .book-open').first().click();
async function frameText(page, needle) {
  await expect.poll(() => page.evaluate(needle => {
    const view = document.querySelector('foliate-view');
    return view?.renderer?.getContents().some(({ doc }) => doc.body?.textContent.includes(needle)) || false;
  }, needle)).toBe(true);
}
test.beforeEach(async ({ page }) => { await page.goto('/'); await expect(page.locator('.library-intro')).toBeVisible(); });

test('reading lifecycle: import, annotate, settings, reopen, edit, export, backup/restore', async ({ page }) => {
  // WebKit reports a deferred ResizeObserver notification during pagination as a page error.
  const errors = []; page.on('pageerror', e => { if (!e.message.startsWith('ResizeObserver loop')) errors.push(e.message); });
  await importBook(page, '安静地读书.txt', text);
  await open(page); await frameText(page, 'EXReader test paragraph');
  await page.evaluate(() => {
    const doc = document.querySelector('foliate-view').renderer.getContents()[0].doc;
    const range = doc.createRange(); range.selectNodeContents(doc.querySelector('p')); const sel = doc.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  });
  await page.locator('[data-action="annotate"]').click();
  await page.locator('textarea').fill('这是一条会被保存的笔记');
  await page.getByRole('button', { name: '保存标注', exact: true }).click();
  await expect(page.locator('dialog')).toHaveCount(0);
  await page.locator('[data-action="appearance"]').click();
  await page.locator('select[name="theme"]').selectOption('dark');
  await expect(page.locator('.reader-shell')).toHaveClass(/theme-dark/);
  await page.locator('[data-dismiss]').click();
  await page.locator('[data-action="next"]').click();
  await page.locator('[data-action="back"]').click();
  await page.reload(); await open(page); await frameText(page, 'EXReader');
  await page.locator('[data-action="toc"]').click();
  await expect(page.locator('.index-note')).toHaveCount(1);
  await expect(page.locator('.index-note')).toContainText('这是一条会被保存的笔记');
  await page.locator('[data-dismiss]').click();
  await page.locator('[data-action="back"]').click();
  await page.locator('[data-edit]').click();
  await page.locator('[name="title"]').fill('我的第一本书');
  await page.locator('[name="favorite"]').check();
  await page.locator('#cover-input').setInputFiles({ name: 'cover.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64') });
  await expect(page.locator('#toast')).toContainText('封面已选择');
  await page.getByRole('button', { name: '保存修改' }).click();
  await expect(page.locator('.book-title')).toHaveText('我的第一本书');
  await page.locator('[data-edit]').click(); await page.locator('#convert-book').click(); await page.locator('#export-format').selectOption('epub');
  const exportEvent = page.waitForEvent('download'); await page.locator('#do-export').click();
  const exported = await exportEvent; expect(exported.suggestedFilename()).toBe('我的第一本书.epub');
  const data = await readFile(await exported.path()); expect(data.subarray(0, 2).toString()).toBe('PK');
  const entries = unzipSync(data);
  expect(entries['OEBPS/cover.jpg'].length).toBeGreaterThan(100);
  expect(strFromU8(entries['OEBPS/book.opf'])).toContain('我的第一本书');
  const backupEvent = page.waitForEvent('download');
  await page.locator('.topbar [data-action="settings"]').click();
  await page.getByRole('button', { name: '导出整个书库', exact: true }).click();
  const backup = await backupEvent, backupPath = await backup.path();
  await page.locator('[data-edit]').click(); await page.locator('#remove-book').click(); await page.locator('#confirm-delete').click();
  await expect(page.locator('.book-card')).toHaveCount(0);
  await page.locator('#restore-input').setInputFiles({ name: 'backup.zip', mimeType: 'application/zip', buffer: await readFile(backupPath) });
  await expect(page.locator('.book-title')).toHaveText('我的第一本书');
  await page.locator('[data-tab="notes"]').click(); await expect(page.locator('.note-card')).toContainText('这是一条会被保存的笔记');
  expect(errors).toEqual([]);
});

for (const [ext, buffer, needle] of [
  ['epub', epub(), 'EPUB reading works'], ['fb2', fb2, 'FB2 reading works'], ['rtf', rtf, 'RTF reading works'], ['docx', docx, 'DOCX reading works'], ['mobi', mobi(), 'MOBI reading works'],
]) test(`reads ${ext.toUpperCase()} and resumes after reopening`, async ({ page }) => {
  await importBook(page, `fixture.${ext}`, buffer); await open(page); await frameText(page, needle);
  await page.locator('[data-action="bookmark"]').click(); await page.getByRole('button', { name: '保存书签', exact: true }).click();
  await page.locator('[data-action="back"]').click(); await open(page); await frameText(page, needle);
});

test('PDF text selection, highlight persistence and page navigation', async ({ page }) => {
  await importBook(page, 'test.pdf', pdf()); await open(page);
  await expect(page.locator('.textLayer')).toContainText('EXReader PDF test');
  await page.evaluate(() => {
    const node = document.querySelector('.textLayer span'); const range = document.createRange(); range.selectNodeContents(node); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
  });
  await page.locator('[data-action="annotate"]').click(); await page.locator('textarea').fill('PDF 笔记'); await page.getByRole('button', { name: '保存标注', exact: true }).click();
  await expect(page.locator('.pdf-highlights span')).not.toHaveCount(0);
  await page.locator('[data-action="next"]').click(); await expect(page.locator('#location-label')).toHaveText('第 2 / 2 页');
  await page.locator('[data-action="back"]').click(); await open(page); await expect(page.locator('#location-label')).toHaveText('第 2 / 2 页');
  await page.locator('[data-action="prev"]').click(); await expect(page.locator('.pdf-highlights span')).not.toHaveCount(0);
});

test('audio seeks and resumes from local library', async ({ page, browserName }) => {
  test.skip(browserName === 'webkit' && process.platform === 'win32', 'Windows WebKit port advertises WAV but cannot decode the local PCM fixture; verified in Chromium. Apple devices still require real-device testing.');
  const supported = await page.evaluate(() => document.createElement('audio').canPlayType('audio/wav'));
  test.skip(!supported, 'This browser build has no WAV decoder');
  await importBook(page, 'audio.wav', wav()); await open(page);
  await expect(page.locator('audio')).toBeVisible();
  await expect.poll(() => page.locator('audio').evaluate(a => a.duration)).toBe(10);
  await page.locator('audio').evaluate(a => { a.currentTime = 4; });
  await expect(page.locator('#progress-label')).toHaveText('40%');
  await page.locator('[data-action="bookmark"]').click(); await page.getByRole('button', { name: '保存书签', exact: true }).click();
  await page.locator('[data-action="back"]').click(); await open(page);
  await expect.poll(() => page.locator('audio').evaluate(a => a.currentTime)).toBe(4);
});

test('untrusted EPUB cannot execute code or fetch tracking resources', async ({ page }) => {
  const remote = []; page.on('request', request => { if (request.url().includes('example.invalid')) remote.push(request.url()); });
  await importBook(page, 'unsafe.epub', epub(true)); await open(page); await frameText(page, 'EPUB reading works');
  expect(await page.evaluate(() => localStorage.getItem('attacked'))).toBeNull(); expect(remote).toEqual([]);
});

test('every built-in conversion can be reopened', async ({ page }) => {
  await importBook(page, 'roundtrip.txt', 'Roundtrip text.\n\n第二段中文与 emoji 🐈。');
  for (const ext of ['epub', 'docx', 'fb2', 'rtf', 'txt', 'html']) {
    await page.locator('[data-edit]').first().click(); await page.locator('#convert-book').click(); await page.locator('#export-format').selectOption(ext);
    const pending = page.waitForEvent('download'); await page.locator('#do-export').click(); const download = await pending;
    const path = await download.path(); const data = await readFile(path); expect(data.length).toBeGreaterThan(20);
    if (!['txt', 'html'].includes(ext)) {
      const contents = await page.evaluate(async ({ data, ext }) => {
        const { openReflow } = await import('/src/formats.js');
        const book = await openReflow(new File([new Uint8Array(data)], `roundtrip.${ext}`));
        let text = ''; for (const s of book.sections) text += (await s.createDocument()).body.textContent;
        book.destroy?.(); return text;
      }, { data: Array.from(data), ext });
      expect(contents).toContain('Roundtrip text'); expect(contents).toContain('第二段中文与 emoji 🐈');
    }
  }
});

test('responsive library and reader use the available viewport', async ({ page }) => {
  await page.getByRole('button', { name: '先读一篇示例文章 →' }).click();
  await expect(page.locator('.book-card')).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('.book-open').click();
  await page.waitForFunction(() => document.querySelector('foliate-view')?.renderer?.getContents().some(({ doc }) => doc.body?.textContent.includes('窗外的风')));
  await expect.poll(() => page.evaluate(() => {
    const stage = document.querySelector('#reading-stage').getBoundingClientRect();
    const frame = document.querySelector('foliate-view').renderer.getContents()[0].doc.defaultView.frameElement.getBoundingClientRect();
    return frame.height / stage.height;
  })).toBeGreaterThan(0.75);
  const top = await page.evaluate(() => document.querySelector('foliate-view').renderer.getContents()[0].doc.defaultView.frameElement.getBoundingClientRect().top - document.querySelector('#reading-stage').getBoundingClientRect().top);
  expect(top).toBeLessThan(80);
});
