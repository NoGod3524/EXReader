import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { unzipSync, strFromU8 } from 'fflate';
const adb = (...args) => execFileSync('adb', args, { encoding: 'utf8' }).trim();
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function tapSave() {
  for (let attempt = 0; attempt < 20; attempt++) {
    adb('shell', 'uiautomator', 'dump', '/sdcard/exreader-ui.xml');
    const xml = adb('shell', 'cat', '/sdcard/exreader-ui.xml');
    const nodes = Array.from(xml.matchAll(/<node\b[^>]*>/g), ([node]) => Object.fromEntries(Array.from(node.matchAll(/([\w:-]+)="([^"]*)"/g), m => [m[1], m[2]])));
    const save = nodes.find(n => n.enabled === 'true' && (/action_menu_save/.test(n['resource-id'] || '') || /^save$/i.test(n.text || '')));
    if (save) {
      const bounds = Array.from(save.bounds.matchAll(/\d+/g), m => Number(m[0]));
      adb('shell', 'input', 'tap', String(Math.floor((bounds[0] + bounds[2]) / 2)), String(Math.floor((bounds[1] + bounds[3]) / 2)));
      return;
    }
    await wait(500);
  }
  throw new Error('System document Save button did not appear');
}
await mkdir('test-results/android', { recursive: true });
async function apks(folder) {
  const entries = await readdir(folder, { withFileTypes: true });
  return (await Promise.all(entries.map(e => e.isDirectory() ? apks(`${folder}/${e.name}`) : `${folder}/${e.name}`))).flat();
}
const apk = (await apks('android-apks')).find(p => p.endsWith('.apk') && /x86_64/.test(p));
assert.ok(apk, 'x86_64 emulator APK must exist');
adb('install', '-r', apk);
try {
  for (let round = 0; round < 2; round++) {
    adb('shell', 'am', 'start', '-n', 'io.exreader.reader/.MainActivity');
    let browser;
    let connectionError;
    for (let retry = 0; retry < 60; retry++) {
      try {
        const pid = adb('shell', 'pidof', 'io.exreader.reader');
        const sockets = adb('shell', 'cat', '/proc/net/unix').split('\n').map(line => line.trim().split(/\s+/).at(-1)?.replace(/^@/, '')).filter(name => name?.startsWith('webview_devtools_remote'));
        const socket = sockets.find(name => name.endsWith(`_${pid}`)) || (sockets.length === 1 ? sockets[0] : undefined);
        assert.ok(socket, `No WebView socket for PID ${pid}; available: ${sockets.join(', ')}`);
        adb('forward', 'tcp:9222', `localabstract:${socket}`);
        browser = await chromium.connectOverCDP('http://127.0.0.1:9222', { timeout: 2000 });
        break;
      } catch (error) { connectionError = error; await wait(1000); }
    }
    assert.ok(browser, `Android WebView debugging endpoint must be available: ${connectionError}`);
    try {
      const page = browser.contexts()[0].pages()[0];
      await page.locator('.library-intro').waitFor();
      const viewport = await page.evaluate(() => ({ width: innerWidth, content: document.documentElement.scrollWidth }));
      assert.ok(viewport.width < 600, `Phone must use a mobile viewport: ${JSON.stringify(viewport)}`);
      assert.ok(viewport.content <= viewport.width, 'Library must fit the screen without horizontal overflow');
      if (!round) {
        await page.getByRole('button', { name: '先读一篇示例文章 →' }).click();
        await page.locator('.book-card').waitFor();
        await page.locator('.book-open').click();
        await page.waitForFunction(() => document.querySelector('foliate-view')?.renderer?.getContents().some(({ doc }) => doc.body?.textContent.includes('窗外的风')));
        await page.locator('[data-action="bookmark"]').click();
        await page.getByRole('button', { name: '保存书签', exact: true }).click();
        await page.locator('[data-action="back"]').click();
        await page.locator('.book-card').waitFor();
      } else {
        assert.equal(await page.locator('.book-card').count(), 1);
        await page.locator('[data-tab="notes"]').click();
        await page.locator('.note-card').waitFor();
        assert.equal(await page.locator('.note-card').count(), 1);
        await page.locator('[data-tab="all"]').click();
        await page.locator('[data-edit]').click();
        await page.locator('#convert-book').click();
        assert.equal(await page.locator('#calibre-convert').count(), 0, 'Desktop-only conversion must not appear on Android');
        await page.locator('[data-dismiss]').click();
        await page.locator('.topbar [data-action="settings"]').click();
        await page.getByRole('button', { name: '导出整个书库', exact: true }).click();
        await tapSave();
        await page.waitForFunction(() => document.querySelector('#toast')?.textContent.includes('书库备份已保存'));
        const saved = adb('shell', 'find', '/sdcard/Download', '-maxdepth', '1', '-name', 'EXReader-*.zip').split('\n').filter(Boolean)[0];
        assert.ok(saved, 'Native export must create a file in Downloads');
        adb('pull', saved, 'test-results/android/backup.zip');
        const { readFile } = await import('node:fs/promises');
        const archive = unzipSync(new Uint8Array(await readFile('test-results/android/backup.zip')));
        const metadata = JSON.parse(strFromU8(archive['library.json']));
        assert.equal(metadata.books.length, 1);
        assert.equal(metadata.notes.length, 1);
      }
      console.log(`Android native round ${round + 1}: passed`);
    } finally { await browser.close(); }
    await writeFile(`test-results/android/round-${round + 1}.png`, execFileSync('adb', ['exec-out', 'screencap', '-p']));
    adb('shell', 'am', 'force-stop', 'io.exreader.reader');
    await wait(1000);
  }
} catch (error) {
  await writeFile('test-results/android/failure.png', execFileSync('adb', ['exec-out', 'screencap', '-p']));
  await writeFile('test-results/android/logcat.txt', adb('logcat', '-d'));
  await writeFile('test-results/android/sockets.txt', adb('shell', 'cat', '/proc/net/unix'));
  throw error;
}
