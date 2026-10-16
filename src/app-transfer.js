// SPDX-License-Identifier: GPL-3.0-only
import { library } from './app-library.js';
import { convert as createExport, notesExport as createNotesExport } from './index.js';
export async function download(blob, name) {
  if (window.__TAURI_INTERNALS__) {
    const { save } = await import('@tauri-apps/plugin-dialog');
    const { writeFile } = await import('@tauri-apps/plugin-fs');
    const path = await save({ defaultPath: name });
    if (!path) return false;
    await writeFile(path, new Uint8Array(await blob.arrayBuffer()));
    return true;
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  return true;
}
const safeName = name => name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').slice(0, 160) || 'book';
export const backup = async () => download(await library.createBackup(), `EXReader-${new Date().toISOString().slice(0, 10)}.zip`);
export const restoreBackup = file => library.restoreBackup(file);
export const notesExport = async (notes, books) => download(await createNotesExport(notes, books), 'EXReader-标注.md');
export const convert = async (file, book, format) => download(await createExport(file, book, format), `${safeName(book.title)}.${format === 'original' ? book.format : format}`);
