// SPDX-License-Identifier: MIT
// F09 macOS screen reader: what VoiceOver actually speaks on the product host.
// XCUI results say what an assistive client can query; they are not a screen
// reader result. This lane starts the real VoiceOver through guidepup, moves
// only with VoiceOver's own navigation and activation, and records its spoken
// phrases. Human listening is a separate record this lane does not claim.
import { voiceOver } from '@guidepup/guidepup';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';

const [app, out] = process.argv.slice(2);
if (process.env.GITHUB_ACTIONS !== 'true') throw new Error('GitHub Actions only');
mkdirSync(out, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const steps = [];
const result = { source_sha: process.env.GITHUB_SHA, run_id: process.env.GITHUB_RUN_ID,
  attempt: process.env.GITHUB_RUN_ATTEMPT, screen_reader: 'VoiceOver (macOS)', human_listening_verified: false };

// `fragment` is a string or a predicate over the spoken phrase.
async function seek(fragment, limit = 60) {
  const matches = typeof fragment === 'function' ? fragment : (phrase) => phrase.includes(fragment);
  let silent = 0;
  for (let i = 0; i < limit; i++) {
    const phrase = await voiceOver.lastSpokenPhrase();
    steps.push(phrase);
    if (matches(phrase)) return true;
    silent = phrase ? 0 : silent + 1;
    // A cursor trapped inside an element speaks nothing; step back out of it.
    if (silent >= 4) { await voiceOver.stopInteracting(); steps.push('[stop interacting]'); silent = 0; }
    await voiceOver.next();
    await sleep(250);
  }
  return false;
}

try {
  await voiceOver.start();
  execFileSync('open', ['-n', app, '--args', '-EXRUITestFixtures', '1', '-EXRFreshState', '1']);
  await sleep(8000);
  // No interact(): it moved the VoiceOver cursor inside the first button, where
  // every next() spoke nothing (round 15). Window-level next() walks the controls.
  const found = {};
  found.library = await seek('书架');
  found.search = await seek('搜索');
  found.organize = await seek('整理');
  found.importSample = await seek('导入 EPUB');
  if (found.importSample) { await voiceOver.act(); await sleep(6000); }
  // The shelf row button itself: the status "已导入 Sample.epub" also names the
  // book and was taken for the row once (run 41284439868).
  found.book = await seek((phrase) => phrase.startsWith('Sample.epub') && phrase.includes('button'), 80);
  if (found.book) { await voiceOver.act(); await sleep(8000); }
  found.page = await seek('第 1 页', 80);
  result.found = found;
  result.spoken = await voiceOver.spokenPhraseLog();
  result.checks = Object.entries({
    'V-01 library title spoken': found.library, 'V-02 search field spoken': found.search,
    'V-03 organize command spoken': found.organize, 'V-04 import command reached and activated': found.importSample,
    'V-05 imported book row spoken and opened': found.book, 'V-06 reading page spoken': found.page,
  }).map(([id, ok]) => ({ id, status: ok ? 'pass' : 'fail' }));
  result.accepted = result.checks.every((c) => c.status === 'pass');
} catch (error) {
  result.error = String(error && error.stack || error);
  // guidepup wraps the real start failure; keep the whole cause chain.
  for (let cause = error && error.cause, depth = 0; cause && depth < 5; cause = cause.cause, depth++) {
    result.error += '\ncaused by: ' + String(cause.stack || cause);
  }
  result.accepted = false;
} finally {
  result.steps = steps;
  try { await voiceOver.stop(); } catch (_) { /* already stopped */ }
  writeFileSync(`${out}/report.json`, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ accepted: result.accepted, checks: result.checks, error: result.error }));
}
