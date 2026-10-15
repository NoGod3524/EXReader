import { readdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
async function list(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  return (await Promise.all(entries.map(e => e.isDirectory() ? list(`${dir}/${e.name}`) : `${dir}/${e.name}`))).flat();
}
const files = (await list('dist')).filter(f => !f.endsWith('.map') && !f.endsWith('.md') && !f.endsWith('/sw.js'));
const hash = createHash('sha256');
for (const file of files) hash.update(await readFile(file));
const version = `exreader-${hash.digest('hex').slice(0, 12)}`;
await writeFile('dist/sw.js', `const CACHE=${JSON.stringify(version)},FILES=${JSON.stringify(files.map(f => f.slice(4)))};
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES))));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('exreader-')&&k!==CACHE).map(k=>caches.delete(k))))));
self.addEventListener('fetch',e=>{if(e.request.method==='GET'&&new URL(e.request.url).origin===self.location.origin)e.respondWith(caches.open(CACHE).then(c=>c.match(e.request.mode==='navigate'?'/index.html':e.request,{ignoreVary:true})).then(r=>r||fetch(e.request)));});`);
console.log('Offline cache:', version, files.length, 'files');
