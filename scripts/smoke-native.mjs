import { chromium } from '@playwright/test';
import { mkdir, cp, writeFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import path from 'node:path';
import assert from 'node:assert/strict';

if (process.platform !== 'win32') throw new Error('This smoke check targets the Windows portable build');
const folder = path.resolve(`test-results/native-smoke-${Date.now()}`);
await mkdir(folder, { recursive: true });
const executable = path.join(folder, 'EXReader.exe');
await cp('release/EXReader-portable/EXReader.exe', executable);
await writeFile(path.join(folder, '.portable'), '');
for (let round = 0; round < 2; round++) {
  const port = 9137 + round;
  const child = spawn(executable, [], { cwd: folder, windowsHide: true, stdio: 'ignore', env: { ...process.env, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${port}` } });
  let browser;
  try {
    for (let n = 0; n < 60; n++) {
      try { if ((await fetch(`http://127.0.0.1:${port}/json/version`)).ok) break; } catch {}
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
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
      const rejection = await page.evaluate(async () => {
        try { await window.__TAURI_INTERNALS__.invoke('convert_book', { input: [1], from: '../../file', to: 'epub', title: '', author: '', cover: null }); }
        catch (e) { return String(e); }
      });
      assert.match(rejection, /不支持的转换格式/);
    } else {
      assert.equal(await page.locator('.book-card').count(), 1, 'portable library must persist across process restarts');
      await page.locator('[data-tab="notes"]').click();
      assert.equal(await page.locator('.note-card').count(), 1, 'bookmark must persist across process restarts');
      await page.locator('[data-tab="all"]').click();
      await page.screenshot({ path: 'docs/screenshots/windows-native.png' });
    }
    console.log(`Windows native round ${round + 1}: passed`);
  } finally { await browser?.close(); child.kill(); }
}
