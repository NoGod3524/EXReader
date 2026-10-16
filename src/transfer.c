/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "internal.h"
#include <miniz.h>
#include <time.h>
static exr_status xml_text(const char *text, size_t size, const char *field, exr_error *e) {
  size_t at = 0;
  while (at < size) {
    size_t start = at;
    uint32_t cp;
    if (!exr_next(text, size, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Invalid UTF-8 in XML %s at byte %zu", field, start);
    if (cp != 9 && cp != 10 && cp != 13 &&
        !(cp >= 0x20 && cp <= 0xd7ff) && !(cp >= 0xe000 && cp <= 0xfffd) &&
        !(cp >= 0x10000 && cp <= 0x10ffff))
      return exr_fail(e, EXR_ENCODING, "XML 1.0 cannot represent U+%04lX in %s at byte %zu",
                      (unsigned long)cp, field, start);
  }
  return EXR_OK;
}
static int escaped(exr_buffer *b, const char *text, size_t n) {
  size_t i;
  for (i = 0; i < n; i++) {
    const char *s = NULL;
    switch (text[i]) {
    case '&':
      s = "&amp;";
      break;
    case '<':
      s = "&lt;";
      break;
    case '>':
      s = "&gt;";
      break;
    case '"':
      s = "&quot;";
      break;
    case '\'':
      s = "&apos;";
      break;
    }
    if (s) {
      if (!exr_append(b, s, strlen(s)))
        return 0;
    } else if (!exr_append(b, text + i, 1))
      return 0;
  }
  return 1;
}
static int literal(exr_buffer *b, const char *s) { return exr_append(b, s, strlen(s)); }
static int body(exr_buffer *b, const exr_document *d, const char *before, const char *after) {
  size_t i;
  for (i = 0; i < d->count; i++) {
    if (!literal(b, before) ||
        !escaped(b, d->text + d->blocks[i].start, d->blocks[i].end - d->blocks[i].start) ||
        !literal(b, after))
      return 0;
  }
  return 1;
}
static int add(mz_zip_archive *z, const char *name, const char *data, size_t n, int level) {
  return mz_zip_writer_add_mem(z, name, data, n, (mz_uint)level);
}
exr_status exr_document_export(const exr_document *d, exr_format f, void **out, size_t *n,
                               exr_error *e) {
  exr_buffer b = {0}, meta = {0};
  mz_zip_archive zip = {0};
  int zip_open = 0;
  void *bytes = NULL;
  size_t size = 0, i;
  const char *title;
  char modified[32];
  time_t now = time(NULL);
  struct tm utc;
  if (!d || !out || !n)
    return exr_fail(e, EXR_ARGUMENT, "Invalid export arguments");
  *out = NULL;
  *n = 0;
#ifdef _WIN32
  if (gmtime_s(&utc, &now))
    return exr_fail(e, EXR_IO, "Cannot read UTC time");
#else
  if (!gmtime_r(&now, &utc))
    return exr_fail(e, EXR_IO, "Cannot read UTC time");
#endif
  if (!strftime(modified, sizeof(modified), "%Y-%m-%dT%H:%M:%SZ", &utc))
    return exr_fail(e, EXR_IO, "Cannot format UTC time");
  title = d->title && d->title[0] ? d->title : "Untitled";
  if (f == EXR_HTML || f == EXR_FB2 || f == EXR_EPUB || f == EXR_DOCX) {
    exr_status status = f == EXR_DOCX ? EXR_OK : xml_text(title, strlen(title), "title", e);
    if (status == EXR_OK)
      status = xml_text(d->text, d->size, "document text", e);
    if (status != EXR_OK)
      return status;
  }
  if (f == EXR_TXT) {
    bytes = exr_copy(d->text, d->size);
    if (!bytes)
      goto failed;
    *out = bytes;
    *n = d->size;
    return EXR_OK;
  }
  if (f == EXR_HTML || f == EXR_EPUB) {
    if (!literal(&b, "<?xml version=\"1.0\" encoding=\"UTF-8\"?><html "
                     "xmlns=\"http://www.w3.org/1999/xhtml\"><head><title>") ||
        !escaped(&b, title, strlen(title)) || !literal(&b, "</title></head><body>") ||
        !body(&b, d, "<p>", "</p>\n") || !literal(&b, "</body></html>"))
      goto failed;
  } else if (f == EXR_FB2) {
    if (!literal(&b, "<?xml version=\"1.0\" encoding=\"UTF-8\"?><FictionBook "
                     "xmlns=\"http://www.gribuser.ru/xml/fictionbook/"
                     "2.0\"><description><title-info><genre>unrecognised</"
                     "genre><author><nickname>Unknown</nickname></"
                     "author><book-title>") ||
        !escaped(&b, title, strlen(title)) ||
        !literal(&b, "</book-title><lang>und</lang></title-info></"
                     "description><body><section>") ||
        !body(&b, d, "<p>", "</p>\n") || !literal(&b, "</section></body></FictionBook>"))
      goto failed;
  } else if (f == EXR_RTF) {
    size_t at = 0;
    uint32_t cp;
    if (!literal(&b, "{\\rtf1\\ansi\\ansicpg1252\\uc1 "))
      goto failed;
    while (at < d->size) {
      char value[48];
      if (!exr_next(d->text, d->size, &at, &cp))
        goto failed;
      if (cp == '\n') {
        if (!literal(&b, "\\par\n"))
          goto failed;
      } else if (cp == '\\' || cp == '{' || cp == '}') {
        value[0] = '\\';
        value[1] = (char)cp;
        if (!exr_append(&b, value, 2))
          goto failed;
      } else if (cp >= 32 && cp < 127) {
        value[0] = (char)cp;
        if (!exr_append(&b, value, 1))
          goto failed;
      } else if (cp <= 0xffff) {
        snprintf(value, sizeof(value), "\\u%d?", (cp > 32767 ? (int)cp - 65536 : (int)cp));
        if (!literal(&b, value))
          goto failed;
      } else {
        uint32_t hi = 0xd800 + ((cp - 0x10000) >> 10), lo = 0xdc00 + ((cp - 0x10000) & 1023);
        snprintf(value, sizeof(value), "\\u%d?\\u%d?", (int)hi - 65536, (int)lo - 65536);
        if (!literal(&b, value))
          goto failed;
      }
    }
    if (!literal(&b, "}"))
      goto failed;
  } else if (f == EXR_DOCX) {
    if (!literal(&b, "<?xml version=\"1.0\" encoding=\"UTF-8\"?><w:document "
                     "xmlns:w=\"http://schemas.openxmlformats.org/"
                     "wordprocessingml/2006/main\"><w:body>") ||
        !body(&b, d, "<w:p><w:r><w:t xml:space=\"preserve\">", "</w:t></w:r></w:p>\n") ||
        !literal(&b, "<w:sectPr/></w:body></w:document>"))
      goto failed;
  } else
    return exr_fail(e, EXR_FORMAT, "This export format is not implemented");
  if (f != EXR_EPUB && f != EXR_DOCX) {
    *out = b.data;
    *n = b.size;
    return EXR_OK;
  }
  if (!mz_zip_writer_init_heap(&zip, 0, 0))
    goto failed;
  zip_open = 1;
  if (f == EXR_DOCX) {
    const char *types = "<?xml version=\"1.0\"?><Types "
                        "xmlns=\"http://schemas.openxmlformats.org/package/2006/"
                        "content-types\"><Default Extension=\"rels\" "
                        "ContentType=\"application/"
                        "vnd.openxmlformats-package.relationships+xml\"/><Default "
                        "Extension=\"xml\" ContentType=\"application/xml\"/><Override "
                        "PartName=\"/word/document.xml\" "
                        "ContentType=\"application/"
                        "vnd.openxmlformats-officedocument.wordprocessingml.document.main+"
                        "xml\"/></Types>";
    const char *rels = "<?xml version=\"1.0\"?><Relationships "
                       "xmlns=\"http://schemas.openxmlformats.org/package/2006/"
                       "relationships\"><Relationship Id=\"r1\" "
                       "Type=\"http://schemas.openxmlformats.org/"
                       "officeDocument/2006/relationships/officeDocument\" "
                       "Target=\"word/document.xml\"/></Relationships>";
    if (!add(&zip, "[Content_Types].xml", types, strlen(types), 6) ||
        !add(&zip, "_rels/.rels", rels, strlen(rels), 6) ||
        !add(&zip, "word/document.xml", b.data, b.size, 6))
      goto failed;
  } else {
    const char *container = "<?xml version=\"1.0\"?><container version=\"1.0\" "
                            "xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\"><rootfiles><"
                            "rootfile full-path=\"OEBPS/book.opf\" "
                            "media-type=\"application/oebps-package+xml\"/></rootfiles></"
                            "container>";
    const char *nav = "<?xml version=\"1.0\"?><html xmlns=\"http://www.w3.org/1999/xhtml\" "
                      "xmlns:epub=\"http://www.idpf.org/2007/ops\"><head><title>Contents</"
                      "title></head><body><nav epub:type=\"toc\"><ol><li><a "
                      "href=\"text.xhtml\">Text</a></li></ol></nav></body></html>";
    if (!literal(&meta, "<?xml version=\"1.0\" encoding=\"UTF-8\"?><package "
                        "xmlns=\"http://www.idpf.org/2007/opf\" "
                        "version=\"3.0\" unique-identifier=\"id\"><metadata "
                        "xmlns:dc=\"http://purl.org/dc/elements/1.1/"
                        "\"><dc:identifier id=\"id\">urn:exreader:"))
      goto failed;
    {
      char id[20];
      snprintf(id, sizeof(id), "%08lx",
               (unsigned long)mz_crc32(0, (const unsigned char *)d->text, d->size));
      if (!literal(&meta, id))
        goto failed;
    }
    if (!literal(&meta, "</dc:identifier><dc:title>") || !escaped(&meta, title, strlen(title)) ||
        !literal(&meta, "</dc:title><dc:language>und</dc:language><meta "
                        "property=\"dcterms:modified\">") ||
        !literal(&meta, modified) ||
        !literal(&meta, "</meta></"
                        "metadata><manifest><item id=\"text\" href=\"text.xhtml\" "
                        "media-type=\"application/xhtml+xml\"/><item id=\"nav\" "
                        "href=\"nav.xhtml\" media-type=\"application/xhtml+xml\" "
                        "properties=\"nav\"/></manifest><spine><itemref "
                        "idref=\"text\"/></spine></package>"))
      goto failed;
    if (!add(&zip, "mimetype", "application/epub+zip", 20, 0) ||
        !add(&zip, "META-INF/container.xml", container, strlen(container), 6) ||
        !add(&zip, "OEBPS/book.opf", meta.data, meta.size, 6) ||
        !add(&zip, "OEBPS/nav.xhtml", nav, strlen(nav), 6) ||
        !add(&zip, "OEBPS/text.xhtml", b.data, b.size, 6))
      goto failed;
  }
  if (!mz_zip_writer_finalize_heap_archive(&zip, &bytes, &size) || size > EXR_MAX_INPUT)
    goto failed;
  *out = malloc(size);
  if (!*out)
    goto failed;
  for (i = 0; i < size; i++)
    ((unsigned char *)*out)[i] = ((unsigned char *)bytes)[i];
  *n = size;
  mz_free(bytes);
  mz_zip_writer_end(&zip);
  free(b.data);
  free(meta.data);
  return EXR_OK;
failed:
  if (bytes)
    mz_free(bytes);
  if (zip_open)
    mz_zip_writer_end(&zip);
  free(b.data);
  free(meta.data);
  return exr_fail(e, EXR_LIMIT, "Export allocation or size limit exceeded");
}
static void big32(unsigned char *p, uint32_t n) {
  p[0] = (unsigned char)(n >> 24);
  p[1] = (unsigned char)(n >> 16);
  p[2] = (unsigned char)(n >> 8);
  p[3] = (unsigned char)n;
}
static int chunk(FILE *f, const char *type, const void *data, size_t n) {
  unsigned char prefix[8], crc[4];
  mz_ulong checksum;
  big32(prefix, (uint32_t)n);
  memcpy(prefix + 4, type, 4);
  checksum = mz_crc32(0, prefix + 4, 4);
  if (n)
    checksum = mz_crc32(checksum, data, n);
  big32(crc, (uint32_t)checksum);
  return fwrite(prefix, 1, 8, f) == 8 && (!n || fwrite(data, 1, n, f) == n) &&
         fwrite(crc, 1, 4, f) == 4;
}
exr_status exr_bitmap_write_png(const exr_bitmap *b, const char *path, exr_error *e) {
  unsigned char ihdr[13] = {0}, *raw, *compressed;
  size_t bytes, y, row;
  unsigned channels;
  unsigned long capacity;
  FILE *f;
  int ok;
  if (!b)
    return exr_fail(e, EXR_ARGUMENT, "Missing bitmap");
  channels = b->channels ? b->channels : 1;
  row = (size_t)b->width * channels;
  if (!path || !b->pixels || !b->width || !b->height || b->width > 16384 || b->height > 16384 ||
      (channels != 1 && channels != 4) || b->stride < row || row * b->height > 64 * 1024 * 1024)
    return exr_fail(e, EXR_ARGUMENT, "Invalid PNG bitmap");
  bytes = (row + 1) * b->height;
  capacity = mz_compressBound((mz_ulong)bytes);
  raw = malloc(bytes);
  compressed = malloc(capacity);
  if (!raw || !compressed) {
    free(raw);
    free(compressed);
    return exr_fail(e, EXR_MEMORY, "PNG allocation failed");
  }
  for (y = 0; y < b->height; y++) {
    raw[y * (row + 1)] = 0;
    memcpy(raw + y * (row + 1) + 1, b->pixels + y * b->stride, row);
  }
  if (mz_compress2(compressed, &capacity, raw, (mz_ulong)bytes, 1) != MZ_OK) {
    free(raw);
    free(compressed);
    return exr_fail(e, EXR_FORMAT, "PNG compression failed");
  }
  free(raw);
  big32(ihdr, b->width);
  big32(ihdr + 4, b->height);
  ihdr[8] = 8;
  ihdr[9] = channels == 4 ? 6 : 0;
  f = exr_fopen(path, "wb");
  if (!f) {
    free(compressed);
    return exr_fail(e, EXR_IO, "Cannot write PNG");
  }
  ok = fwrite("\x89PNG\r\n\x1a\n", 1, 8, f) == 8 && chunk(f, "IHDR", ihdr, 13) &&
       chunk(f, "IDAT", compressed, capacity) && chunk(f, "IEND", NULL, 0);
  if (fclose(f))
    ok = 0;
  free(compressed);
  return ok ? EXR_OK : exr_fail(e, EXR_IO, "PNG write failed");
}
