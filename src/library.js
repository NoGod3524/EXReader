// SPDX-License-Identifier: GPL-3.0-only
import { createStore } from './store.js';
import { supports } from './registry.js';

const statuses = ['unread', 'reading', 'finished'];
const text = value => typeof value === 'string';
const validCover = value => value === '' || /^data:image\/(png|jpeg|webp|gif);base64,/.test(value);
function validateNote(note) {
  if (note.bookmark !== undefined && typeof note.bookmark !== 'boolean') throw new TypeError('书签标识无效');
  if (!text(note.quote) || !text(note.note)) throw new TypeError('标注正文必须是文字');
  if (note.value !== undefined && !text(note.value) || note.page !== undefined && (!Number.isInteger(note.page) || note.page < 1) || note.seconds !== undefined && (!Number.isFinite(note.seconds) || note.seconds < 0)) throw new TypeError('标注位置无效');
  if (note.rects !== undefined && (!Array.isArray(note.rects) || note.rects.length > 20000 || !note.rects.every(r => ['x', 'y', 'w', 'h'].every(k => Number.isFinite(r[k]) && r[k] >= -0.01 && r[k] <= 1.01)))) throw new TypeError('标注范围无效');
}

export function createLibrary({ name = 'exreader', storage = createStore(name) } = {}) {
  // Serialize mutations within this instance so metadata and progress updates cannot overwrite each other.
  let pending = Promise.resolve();
  const mutate = action => { const result = pending.then(action); pending = result.catch(() => {}); return result; };
  const getBook = async id => {
    const book = (await storage.allBooks()).find(book => book.id === id);
    if (!book) throw new Error('书籍不存在');
    return book;
  };
  const api = {
    getBook,
    getFile: id => storage.getFile(id),
    async listBooks({ query = '', filter = 'all', sort = 'recent' } = {}) {
      if (!['all', 'reading', 'favorite', 'audio', 'finished'].includes(filter) || !['recent', 'added', 'title'].includes(sort)) throw new TypeError('书库筛选或排序无效');
      const q = query.toLocaleLowerCase();
      const books = (await storage.allBooks()).filter(b => filter === 'all' || filter === 'reading' && b.progress > 0 && b.status !== 'finished' || filter === 'favorite' && b.favorite || filter === 'audio' && b.audio || filter === 'finished' && b.status === 'finished').filter(b => `${b.title} ${b.author} ${(b.tags || []).join(' ')}`.toLocaleLowerCase().includes(q));
      return books.sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title, 'zh') : sort === 'added' ? b.added - a.added : (b.lastRead || b.added) - (a.lastRead || a.added));
    },
    importFile: file => mutate(async () => {
      if (!file || !text(file.name) || !Number.isFinite(file.size) || file.size <= 0) throw new TypeError('请选择非空书籍文件');
      if (!supports(file.name)) throw new Error('不支持此格式');
      const existing = (await storage.allBooks()).find(b => b.filename === file.name && b.size === file.size && b.modified === file.lastModified);
      if (existing) return { book: existing, duplicate: true };
      const metadata = await (await import('./formats.js')).readMetadata(file);
      const book = { ...metadata, id: crypto.randomUUID(), filename: file.name, size: file.size, modified: file.lastModified, added: Date.now(), progress: 0, favorite: false, tags: [], status: 'unread' };
      await storage.addBook(book, file);
      return { book, duplicate: false };
    }),
    updateBook: (id, changes) => mutate(async () => {
      const allowed = ['title', 'author', 'tags', 'favorite', 'status', 'cover'];
      if (!changes || Object.keys(changes).some(k => !allowed.includes(k))) throw new TypeError('只能编辑书库元数据');
      const next = { ...await getBook(id), ...changes };
      if (!text(next.title) || !next.title.trim() || next.title.length > 300 || !text(next.author) || next.author.length > 300 || !Array.isArray(next.tags) || !next.tags.every(text) || typeof next.favorite !== 'boolean' || !statuses.includes(next.status) || next.cover !== undefined && !validCover(next.cover)) throw new TypeError('书库元数据无效');
      next.title = next.title.trim();
      await storage.saveBook(next);
      return next;
    }),
    async setCover(id, file) {
      const cover = file ? await (await import('./formats.js')).coverImage(file) : '';
      return api.updateBook(id, { cover });
    },
    saveProgress: (id, location) => mutate(async () => {
      const patch = Object.fromEntries(Object.entries(location).filter(([key]) => ['progress', 'cfi', 'page', 'seconds'].includes(key)));
      if (patch.progress !== undefined && (!Number.isFinite(patch.progress) || patch.progress < 0 || patch.progress > 1) || patch.cfi !== undefined && !text(patch.cfi) || patch.page !== undefined && (!Number.isInteger(patch.page) || patch.page < 1) || patch.seconds !== undefined && (!Number.isFinite(patch.seconds) || patch.seconds < 0)) throw new TypeError('阅读进度无效');
      const book = { ...await getBook(id), ...patch, lastRead: Date.now() };
      if (book.status === 'unread') book.status = 'reading';
      await storage.saveBook(book);
      return book;
    }),
    removeBook: id => mutate(() => storage.removeBook(id)),
    listNotes: bookId => bookId === undefined ? storage.allNotes() : storage.bookNotes(bookId),
    saveNote: (bookId, data) => mutate(async () => {
      await getBook(bookId);
      const fields = ['id', 'quote', 'note', 'value', 'page', 'seconds', 'rects', 'bookmark'];
      if (!data || Object.keys(data).some(key => !fields.includes(key))) throw new TypeError('标注字段无效');
      const notes = await storage.allNotes();
      const existing = data.id ? notes.find(note => note.id === data.id) : undefined;
      if (existing && existing.bookId !== bookId) throw new Error('不能覆盖其他书籍的标注');
      const note = { id: crypto.randomUUID(), quote: '', note: '', ...data, bookId, created: existing?.created || Date.now() };
      if (!text(note.id) || !/^[\w-]{1,100}$/.test(note.id)) throw new TypeError('标注 ID 无效');
      validateNote(note);
      await storage.saveNote(note);
      return note;
    }),
    removeNote: id => mutate(() => storage.deleteNote(id)),
    async exportBook(id, format = 'original') {
      return (await import('./transfer.js')).convert(await storage.getFile(id), await getBook(id), format);
    },
    createBackup: () => mutate(async () => (await import('./transfer.js')).backup(storage)),
    restoreBackup: file => mutate(async () => (await import('./transfer.js')).restoreBackup(file, storage)),
    async exportNotes() { return (await import('./transfer.js')).notesExport(await storage.allNotes(), await storage.allBooks()); },
    close: () => mutate(() => storage.close?.()),
  };
  return api;
}
