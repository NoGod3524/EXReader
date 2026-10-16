import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
await mkdir('public/pdf-assets', { recursive: true });
await cp('node_modules/pdfjs-dist/build/pdf.worker.mjs', 'public/pdf-assets/pdf.worker.mjs');
for (const dir of ['cmaps', 'standard_fonts', 'wasm']) await cp(`node_modules/pdfjs-dist/${dir}`, `public/pdf-assets/${dir}`, { recursive: true });
const css = await readFile('node_modules/pdfjs-dist/web/pdf_viewer.css', 'utf8');
const start = css.indexOf('.textLayer {'), end = css.indexOf('.textLayerImages {', start);
if (start < 0 || end < 0) throw new Error('PDF.js text layer CSS changed; inspect upstream before updating');
await writeFile('src/pdf-text-layer.css', css.slice(0, css.indexOf('*/') + 2) + '\n' + css.slice(start, end));
