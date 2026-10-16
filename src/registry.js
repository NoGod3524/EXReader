// SPDX-License-Identifier: GPL-3.0-only
// Format descriptions are safe to import without a DOM or storage runtime.
const audio = ['mp3', 'm4a', 'm4b', 'ogg', 'opus', 'wav', 'flac', 'aac'];
export const BOOK_EXTENSIONS = Object.freeze(['pdf', 'epub', 'fb2', 'fb2.zip', 'fbz', 'txt', 'rtf', 'mobi', 'azw3', 'docx', 'html', 'htm', 'cbz']);
export const AUDIO_EXTENSIONS = Object.freeze(audio);
export const supportedFormats = () => [
  ...BOOK_EXTENSIONS.map(extension => ({ extension, kind: extension === 'pdf' ? 'pdf' : extension === 'cbz' ? 'fixed' : 'reflow', readable: true, textExport: extension !== 'cbz' })),
  ...AUDIO_EXTENSIONS.map(extension => ({ extension, kind: 'audio', readable: true, textExport: false, requiresDeviceDecoder: true })),
];
export function extension(name) {
  const lower = String(name).toLowerCase();
  return [...BOOK_EXTENSIONS, ...AUDIO_EXTENSIONS].sort((a, b) => b.length - a.length).find(ext => lower.endsWith('.' + ext)) || lower.split('.').pop();
}
export const supports = name => supportedFormats().some(format => format.extension === extension(name));
export const DEFAULT_SETTINGS = Object.freeze({ size: 20, spacing: 1.8, font: 'serif', theme: 'paper', flow: 'paginated', columns: '1', justify: true, encoding: 'auto', zoom: 1 });
