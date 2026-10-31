// SPDX-License-Identifier: MIT
// Read-only exporter for the legacy EXReader browser/Tauri store (IndexedDB "exreader", version 1,
// object stores "books", "files", "notes"). Run it on the SAME ORIGIN as the old app (IndexedDB is
// origin-scoped): paste into the DevTools console or inject it with a test driver, then call
//   await exrLegacyExport()                       // downloads <database>.exrpack
//   await exrLegacyExport({ download: false })    // returns { blob, summary } instead
// It only opens readonly transactions and never writes, upgrades or deletes anything. If the
// database does not exist the open request is aborted so that no empty database is created.
// Memory: originals are read one at a time and appended to a Blob (browser-managed storage), so the
// JS heap holds at most one original plus the record metadata.
(function (global) {
  'use strict';
  const VERSION = '1';
  const MAGIC = 'EXRLGP1\n';
  const TRAILER_MAGIC = 'EXRLGPT1';
  const KNOWN_STORES = ['books', 'files', 'notes'];
  const encoder = new TextEncoder();

  class LegacyExportError extends Error {
    constructor(code, message) { super(message); this.name = 'LegacyExportError'; this.code = code; }
  }
  const request = r => new Promise((resolve, reject) => { r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });
  const hex = buffer => Array.from(new Uint8Array(buffer), b => b.toString(16).padStart(2, '0')).join('');
  async function sha256(bytes) {
    if (!global.crypto || !global.crypto.subtle) throw new LegacyExportError('crypto-unavailable', 'crypto.subtle needs a secure context (https or localhost)');
    return hex(await global.crypto.subtle.digest('SHA-256', bytes));
  }
  function u64(n) {
    const out = new Uint8Array(8);
    let v = BigInt(n);
    for (let i = 0; i < 8; i++) { out[i] = Number(v & 0xffn); v >>= 8n; }
    return out;
  }
  function fromHex(text) {
    const out = new Uint8Array(text.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(text.substr(i * 2, 2), 16);
    return out;
  }
  class BlobSink {
    constructor() { this.blob = new Blob([]); }
    async write(chunk) { this.blob = new Blob([this.blob, chunk instanceof Blob ? chunk : new Blob([chunk])]); }
    async close() { return this.blob; }
  }
  async function openExisting(name) {
    if (global.indexedDB.databases) {
      const known = await global.indexedDB.databases();
      if (!known.some(d => d.name === name)) throw new LegacyExportError('database-missing', `no IndexedDB database named "${name}" on this origin`);
    }
    return new Promise((resolve, reject) => {
      const r = global.indexedDB.open(name); // no version: never upgrade
      let created = false;
      r.onupgradeneeded = () => { created = true; r.transaction.abort(); };
      r.onsuccess = () => resolve(r.result);
      r.onblocked = () => reject(new LegacyExportError('blocked', 'the database is blocked by another connection'));
      r.onerror = () => reject(created ? new LegacyExportError('database-missing', `no IndexedDB database named "${name}" on this origin`) : r.error);
    });
  }
  async function readFileRecord(db, id, fallbackName) {
    const value = await request(db.transaction(['files'], 'readonly').objectStore('files').get(id));
    if (value === undefined) return null;
    if (value instanceof Blob) return { bytes: new Uint8Array(await value.arrayBuffer()), name: value.name || fallbackName || '', type: value.type || '', modified: value.lastModified ?? null, shape: 'blob' };
    if (value && value.bytes instanceof ArrayBuffer) return { bytes: new Uint8Array(value.bytes), name: value.name || fallbackName || '', type: value.type || '', modified: value.modified ?? null, shape: 'record' };
    if (value && ArrayBuffer.isView(value.bytes)) return { bytes: new Uint8Array(value.bytes.buffer, value.bytes.byteOffset, value.bytes.byteLength), name: value.name || fallbackName || '', type: value.type || '', modified: value.modified ?? null, shape: 'record' };
    throw new LegacyExportError('unsupported-file-record', `files["${id}"] has an unknown shape`);
  }

  async function exportLegacy(options = {}) {
    const name = options.database || 'exreader';
    const db = await openExisting(name);
    try {
      if (db.version !== 1 && !options.acceptAnyVersion) throw new LegacyExportError('unknown-version', `legacy database version is ${db.version}; only version 1 is documented`);
      const stores = Array.from(db.objectStoreNames);
      for (const required of KNOWN_STORES) if (!stores.includes(required)) throw new LegacyExportError('store-missing', `object store "${required}" is missing`);
      const snapshot = db.transaction(['books', 'notes', 'files'], 'readonly');
      const bookStore = snapshot.objectStore('books'), noteStore = snapshot.objectStore('notes'), fileStore = snapshot.objectStore('files');
      const [bookKeys, bookRecords, noteKeys, noteRecords, fileKeys] = await Promise.all([
        request(bookStore.getAllKeys()), request(bookStore.getAll()), request(noteStore.getAllKeys()), request(noteStore.getAll()), request(fileStore.getAllKeys())]);
      const noteIndexes = Array.from(noteStore.indexNames);
      const sink = options.sink || new BlobSink();
      let offset = 0;
      const put = async chunk => { await sink.write(chunk); offset += chunk instanceof Blob ? chunk.size : chunk.byteLength; };
      await put(encoder.encode(MAGIC));
      const warnings = [];
      const books = [];
      const bookIds = new Set(bookKeys.map(String));
      const fileIds = new Set(fileKeys.map(String));
      let maxOriginal = 0, totalOriginal = 0;
      for (let i = 0; i < bookKeys.length; i++) {
        const id = String(bookKeys[i]), record = bookRecords[i];
        if (record && record.id !== undefined && String(record.id) !== id) warnings.push({ code: 'record-id-mismatch', legacy_id: id, message: 'record.id differs from the store key; the key is used' });
        const entry = { legacy_id: id, record, file: { present: false } };
        const file = fileIds.has(id) ? await readFileRecord(db, bookKeys[i], record && record.filename) : null;
        if (file) {
          const digest = await sha256(file.bytes);
          entry.file = { present: true, offset, size: file.bytes.byteLength, sha256: digest, name: file.name, type: file.type, modified: file.modified, shape: file.shape };
          maxOriginal = Math.max(maxOriginal, file.bytes.byteLength);
          totalOriginal += file.bytes.byteLength;
          await put(file.bytes);
        }
        books.push(entry); // `file.bytes` goes out of scope here: one original at a time
      }
      const notes = noteKeys.map((key, i) => ({ legacy_id: String(key), record: noteRecords[i] }));
      const orphanFiles = fileKeys.map(String).filter(k => !bookIds.has(k));
      const manifest = {
        format: 'exreader-legacy-pack', version: 1,
        exporter: { name: 'exr-legacy-export.js', version: VERSION, read_only: true },
        source: {
          kind: 'indexeddb', database: name, version: db.version, stores, note_indexes: noteIndexes,
          unknown_stores: stores.filter(s => !KNOWN_STORES.includes(s)),
          origin: global.location ? global.location.origin : null,
          user_agent: global.navigator ? global.navigator.userAgent : null,
          exported_at: new Date().toISOString(),
        },
        counts: { books: books.length, notes: notes.length, files: fileKeys.length, originals: books.filter(b => b.file.present).length, orphan_files: orphanFiles.length },
        stats: { max_original_bytes: maxOriginal, total_original_bytes: totalOriginal },
        books, notes, orphans: { files: orphanFiles }, warnings,
      };
      const manifestBytes = encoder.encode(JSON.stringify(manifest));
      const manifestOffset = offset;
      const digest = await sha256(manifestBytes);
      await put(manifestBytes);
      await put(encoder.encode(TRAILER_MAGIC));
      await put(u64(manifestOffset));
      await put(u64(manifestBytes.byteLength));
      await put(fromHex(digest));
      const result = await sink.close();
      const summary = { database: name, version: db.version, books: books.length, notes: notes.length, originals: manifest.counts.originals, orphan_files: orphanFiles.length, max_original_bytes: maxOriginal, total_original_bytes: totalOriginal, manifest_sha256: digest, bytes: offset };
      if (options.download !== false && result instanceof Blob && global.document) {
        const url = URL.createObjectURL(result);
        const a = global.document.createElement('a');
        a.href = url; a.download = options.filename || `${name}.exrpack`;
        global.document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
      }
      return { blob: result, summary };
    } finally {
      db.close();
    }
  }
  exportLegacy.LegacyExportError = LegacyExportError;
  exportLegacy.version = VERSION;
  global.exrLegacyExport = exportLegacy;
})(typeof globalThis !== 'undefined' ? globalThis : window);
