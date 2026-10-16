import { execFileSync } from 'node:child_process';
import { mkdir, readdir, writeFile, readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { unzipSync, strFromU8 } from 'fflate';
const adb = (...args) => execFileSync('adb', args, { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }).trim();
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const folder = 'test-results/android';
await mkdir(folder, { recursive: true });
async function nodes() {
  adb('shell', 'uiautomator', 'dump', '/sdcard/exreader-ui.xml');
  const xml = adb('shell', 'cat', '/sdcard/exreader-ui.xml');
  await writeFile(`${folder}/ui.xml`, xml);
  return Array.from(xml.matchAll(/<node\b[^>]*>/g), ([node]) => {
    const attributes = Object.fromEntries(Array.from(node.matchAll(/([\w:-]+)="([^"]*)"/g), m => [m[1], m[2]]));
    attributes.rect = Array.from((attributes.bounds || '').matchAll(/\d+/g), m => Number(m[0]));
    return attributes;
  }).filter(n => n.rect.length === 4 && n.rect[2] > n.rect[0] && n.rect[3] > n.rect[1]);
}
async function find(pattern, clickable = false) {
  let latest = [];
  for (let attempt = 0; attempt < 25; attempt++) {
    try { latest = await nodes(); }
    catch (error) {
      if (error.status === undefined) throw error;
      await wait(500);
      continue;
    }
    // Cold emulator boots can show a launcher ANR over the foreground app.
    if (latest.some(n => n.text === "Pixel Launcher isn't responding")) {
      const close = latest.find(n => n.text === 'Close app');
      if (close) { tapNode(close); await wait(1000); continue; }
    }
    const matches = latest.filter(n => pattern.test(n.text || '') || pattern.test(n['content-desc'] || ''));
    if (matches.length) return (clickable && matches.find(n => n.clickable === 'true')) || matches[0];
    await wait(500);
  }
  throw new Error(`Android UI did not show ${pattern}; visible: ${latest.map(n => n.text || n['content-desc']).filter(Boolean).join(' | ')}`);
}
function tapNode(n) {
  const [left, top, right, bottom] = n.rect;
  adb('shell', 'input', 'tap', String(Math.floor((left + right) / 2)), String(Math.floor((top + bottom) / 2)));
}
async function tap(pattern) { tapNode(await find(pattern, true)); }
async function apks(path) {
  return (await Promise.all((await readdir(path, { withFileTypes: true })).map(e => e.isDirectory() ? apks(`${path}/${e.name}`) : `${path}/${e.name}`))).flat();
}
const apk = (await apks('android-apks')).find(p => p.endsWith('.apk') && /x86_64/.test(p));
assert.ok(apk, 'x86_64 emulator APK must exist');
adb('install', '-r', apk);
adb('shell', 'settings', 'put', 'system', 'screen_off_timeout', '2147483647');
adb('shell', 'svc', 'power', 'stayon', 'true');
try {
  for (let round = 0; round < 2; round++) {
    adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP');
    adb('shell', 'am', 'start', '-W', '-n', 'io.exreader.reader/.MainActivity');
    if (!round) {
      await tap(/先读一篇示例文章/);
      await tap(/^阅读 给阅读留一点时间$/);
      await find(/窗外的风/);
      await writeFile(`${folder}/reading.png`, execFileSync('adb', ['exec-out', 'screencap', '-p']));
      await tap(/^书签$/);
      await tap(/^保存书签$/);
      await tap(/^返回书库$/);
      await find(/^阅读 给阅读留一点时间$/);
    } else {
      await find(/^阅读 给阅读留一点时间$/);
      await tap(/^标注与想法$/);
      await find(/回到原文/);
      await tap(/^全部书籍$/);
      await tap(/^偏好设置$/);
      await tap(/^导出整个书库$/);
      await tap(/^save$/i);
      let saved;
      for (let attempt = 0; attempt < 30; attempt++) {
        saved = adb('shell', 'find', '/sdcard/Download', '-maxdepth', '1', '-name', 'EXReader-*.zip').split('\n').filter(Boolean)[0];
        if (saved) {
          const size = Number(adb('shell', 'stat', '-c', '%s', saved));
          if (size > 0) break;
        }
        await wait(500);
      }
      assert.ok(saved, 'System save dialog must export the backup to Downloads');
      adb('pull', saved, `${folder}/backup.zip`);
      const archive = unzipSync(new Uint8Array(await readFile(`${folder}/backup.zip`)));
      const metadata = JSON.parse(strFromU8(archive['library.json']));
      assert.equal(metadata.books.length, 1);
      assert.equal(metadata.notes.length, 1);
    }
    await writeFile(`${folder}/round-${round + 1}.png`, execFileSync('adb', ['exec-out', 'screencap', '-p']));
    console.log(`Android native round ${round + 1}: passed`);
    adb('shell', 'am', 'force-stop', 'io.exreader.reader');
    await wait(1000);
  }
} catch (error) {
  console.error(error);
  await writeFile(`${folder}/error.txt`, String(error));
  await writeFile(`${folder}/failure.png`, execFileSync('adb', ['exec-out', 'screencap', '-p']));
  await writeFile(`${folder}/logcat.txt`, adb('logcat', '-d'));
  throw error;
}
