// SPDX-License-Identifier: GPL-3.0-only
export { createLibrary } from './library.js';
export { createStore } from './store.js';
export { BOOK_EXTENSIONS, AUDIO_EXTENSIONS, extension, supports, supportedFormats, DEFAULT_SETTINGS } from './registry.js';
export const createReader = async (...args) => (await import('./reader.js')).createReader(...args);
export const openReflow = async (...args) => (await import('./formats.js')).openReflow(...args);
export const readMetadata = async (...args) => (await import('./formats.js')).readMetadata(...args);
export const coverImage = async (...args) => (await import('./formats.js')).coverImage(...args);
export const convert = async (...args) => (await import('./transfer.js')).convert(...args);
export const notesExport = async (...args) => (await import('./transfer.js')).notesExport(...args);
export const configurePDF = async (...args) => (await import('./pdf.js')).configurePDF(...args);
