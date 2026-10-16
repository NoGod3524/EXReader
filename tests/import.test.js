import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createLibrary, extension, supports, supportedFormats } from '../src/index.js';
test('entry point has no DOM, storage initialization or UI side effects', () => {
  assert.equal(typeof globalThis.document, 'undefined');
  const library = createLibrary({ name: 'node-import-only' });
  assert.equal(typeof library.listBooks, 'function');
  assert.equal(extension('BOOK.FB2.ZIP'), 'fb2.zip');
  assert.equal(supports('book.cbr'), false);
  assert.equal(supports('book.CBZ'), true);
  assert.ok(supportedFormats().find(f => f.extension === 'm4b').requiresDeviceDecoder);
});
