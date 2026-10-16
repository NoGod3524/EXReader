// SPDX-License-Identifier: GPL-3.0-only
import { createLibrary } from './index.js';
export const library = createLibrary();
export const allBooks = () => library.listBooks();
export const allNotes = () => library.listNotes();
export const bookNotes = id => library.listNotes(id);
export const getFile = id => library.getFile(id);
export const removeBook = id => library.removeBook(id);
export const deleteNote = id => library.removeNote(id);
export const saveNote = note => library.saveNote(note.bookId, Object.fromEntries(Object.entries(note).filter(([key]) => !['bookId', 'created'].includes(key))));
export async function saveBook(book) {
  const fields = ['title', 'author', 'tags', 'favorite', 'status', 'cover'];
  await library.updateBook(book.id, Object.fromEntries(fields.filter(key => key in book).map(key => [key, book[key]])));
  if (book.lastRead) return library.saveProgress(book.id, book);
  return library.getBook(book.id);
}
