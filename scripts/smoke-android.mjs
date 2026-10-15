import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const adb = (...args) => execFileSync('adb', args, { encoding: 'utf8' }).trim();
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
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
    for (let retry = 0; retry < 60; retry++) {
      try {
        const pid = adb('shell', 'pidof', 'io.exreader.reader');
        adb('forward', 'tcp:9222', `localabstract:webview_devtools_remote_${pid}`);
        browser = await chromium.connectOverCDP('http://127.0.0.1:9222', { timeout: 2000 });
        break;
      } catch { await wait(1000); }
    }
    assert.ok(browser, 'Android WebView debugging endpoint must be available');
    try {
      const page = browser.contexts()[0].pages()[0];
      await page.locator('.library-intro').waitFor();
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
      }
      console.log(`Android native round ${round + 1}: passed`);
    } finally { await browser.close(); }
    await writeFile(`test-results/android/round-${round + 1}.png`, execFileSync('adb', ['exec-out', 'screencap', '-p']));
    adb('shell', 'am', 'force-stop', 'io.exreader.reader');
    await wait(1000);
  }
} catch (error) {
  await writeFile('test-results/android/logcat.txt', adb('logcat', '-d', '-t', '1500'));
  throw error;
}
