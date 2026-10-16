// SPDX-License-Identifier: GPL-3.0-only
export function createStore(name = 'exreader') {
  let database;
  async function db() {
    if (!database) database = new Promise((resolve, reject) => {
      const req = indexedDB.open(name, 1);
      req.onupgradeneeded = () => {
        const d = req.result;
        d.createObjectStore('books', { keyPath: 'id' });
        d.createObjectStore('files');
        d.createObjectStore('notes', { keyPath: 'id' }).createIndex('bookId', 'bookId');
      };
      req.onsuccess = () => { req.result.onversionchange = () => { req.result.close(); database = undefined; }; resolve(req.result); };
      req.onerror = () => { database = undefined; reject(req.error); };
    });
    return database;
  }
  async function transaction(stores, mode, run) {
    const d = await db();
    return new Promise((resolve, reject) => {
      const tx = d.transaction(stores, mode);
      let result;
      try { result = run(tx); } catch (e) { tx.abort(); reject(e); return; }
      tx.oncomplete = () => resolve(result?.result);
      tx.onabort = tx.onerror = event => reject(event.target.error || tx.error || new Error('保存失败，请检查可用空间'));
    });
  }
  const allBooks = () => transaction(['books'], 'readonly', tx => tx.objectStore('books').getAll());
  const allNotes = () => transaction(['notes'], 'readonly', tx => tx.objectStore('notes').getAll());
  const bookNotes = id => transaction(['notes'], 'readonly', tx => tx.objectStore('notes').index('bookId').getAll(id));
  const getFile = async id => {
    const record = await transaction(['files'], 'readonly', tx => tx.objectStore('files').get(id));
    return !record || record instanceof Blob ? record : new File([record.bytes], record.name, { type: record.type, lastModified: record.modified });
  };
  const saveBook = book => transaction(['books'], 'readwrite', tx => tx.objectStore('books').put(book));
  const saveNote = note => transaction(['notes'], 'readwrite', tx => tx.objectStore('notes').put(note));
  const deleteNote = id => transaction(['notes'], 'readwrite', tx => tx.objectStore('notes').delete(id));
  const fileRecord = async file => ({ bytes: await file.arrayBuffer(), name: file.name, type: file.type, modified: file.lastModified });
  const addBook = async (book, file) => {
    const record = await fileRecord(file);
    return transaction(['books', 'files'], 'readwrite', tx => {
      tx.objectStore('books').add(book);
      tx.objectStore('files').add(record, book.id);
    });
  };
  const removeBook = id => transaction(['books', 'files', 'notes'], 'readwrite', tx => {
    tx.objectStore('books').delete(id);
    tx.objectStore('files').delete(id);
    const req = tx.objectStore('notes').index('bookId').openCursor(IDBKeyRange.only(id));
    req.onsuccess = () => { const c = req.result; if (c) { c.delete(); c.continue(); } };
  });
  const restore = async (books, files, notes) => {
    const records = await Promise.all(files.map(fileRecord));
    return transaction(['books', 'files', 'notes'], 'readwrite', tx => {
      books.forEach((b, i) => { tx.objectStore('books').put(b); tx.objectStore('files').put(records[i], b.id); });
      notes.forEach(n => tx.objectStore('notes').put(n));
    });
  };

  async function close() { if (database) { (await database).close(); database = undefined; } }
  return { db, allBooks, allNotes, bookNotes, getFile, saveBook, saveNote, deleteNote, addBook, removeBook, restore, close };
}
