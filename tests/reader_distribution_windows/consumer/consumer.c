/* SPDX-License-Identifier: MIT */
/* Installed-distribution C consumer.
 *
 * Built only from an extracted prefix: no source-tree include path and no
 * source-tree library. It loads an installed example font and an installed
 * example publication, paginates bounded pages, renders one page and reads its
 * text, then reports the numbers as JSON so a relocated prefix is proven to be
 * functionally usable rather than merely linkable. */
#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <string.h>
#include <exreader.h>

#define MAX_PAGES 3

static void escape(const char *value, char *output, size_t capacity) {
  size_t used = 0;
  for (const char *cursor = value; *cursor && used + 3 < capacity; cursor++) {
    unsigned char byte = (unsigned char)*cursor;
    if (byte == '\\' || byte == '"') {
      output[used++] = '\\';
      output[used++] = (char)byte;
    } else if (byte < 0x20) {
      used += (size_t)snprintf(output + used, capacity - used, "\\u%04x", byte);
    } else {
      output[used++] = (char)byte;
    }
  }
  output[used] = '\0';
}

static int run(const char *font_path, const char *book_path, const char *output_path) {
  exr_font *font = NULL;
  exr_publication *publication = NULL;
  exr_document *document = NULL;
  exr_pager *pager = NULL;
  exr_layout *page = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_layout_config config = exr_layout_config_defaults();
  size_t parts = 0, pages = 0, text_bytes = 0, completed_parts = 0;
  int status = 1;
  config.page = (exr_layout_options){720, 1040, 36, 28, 1.5f, 10};
  if (exr_font_open(font_path, &font, &error) != EXR_OK) {
    goto done;
  }
  if (exr_publication_open(book_path, &publication, &error) != EXR_OK) {
    goto done;
  }
  if (!exr_publication_parts(publication, &parts) || parts == 0) {
    goto done;
  }
  for (size_t part = 0; part < parts; part++) {
    size_t length = 0;
    if (exr_publication_load(publication, part, &document, &error) != EXR_OK) {
      goto done;
    }
    if (!exr_document_text(document, &length) && length) {
      goto done;
    }
    text_bytes += length;
    if (exr_pager_create(document, font, &config, &pager, &error) != EXR_OK) {
      goto done;
    }
    for (;;) {
      if (exr_pager_next(pager, &page, &error) != EXR_OK) {
        goto done;
      }
      if (!page) {
        break;
      }
      if (pages >= MAX_PAGES) {
        exr_layout_free(page);
        page = NULL;
        break;
      }
      if (exr_render_page_color(page, exr_layout_font(page), 0, &bitmap, &error) != EXR_OK) {
        goto done;
      }
      if (!bitmap.pixels || bitmap.width != 720 || bitmap.height != 1040 || bitmap.channels != 4) {
        goto done;
      }
      exr_bitmap_free(&bitmap);
      exr_layout_free(page);
      page = NULL;
      pages++;
    }
    exr_pager_free(pager);
    pager = NULL;
    exr_document_free(document);
    document = NULL;
    completed_parts++;
  }
  status = 0;
done:
  exr_bitmap_free(&bitmap);
  exr_layout_free(page);
  exr_pager_free(pager);
  exr_document_free(document);
  exr_publication_free(publication);
  exr_font_free(font);
  {
    FILE *stream = fopen(output_path, "wb");
    char version[256];
    if (!stream) {
      return status;
    }
    escape(exr_version(), version, sizeof(version));
    fprintf(stream,
            "{\"schema\":\"reader-distribution-windows-consumer-v1\",\"consumer\":\"c11\","
            "\"sdk_version\":\"%s\",\"abi\":%u,\"status\":%d,\"parts\":%u,"
            "\"completed_parts\":%u,\"pages\":%u,\"text_bytes\":%u,\"passed\":%s}\n",
            version, (unsigned)exr_abi_version(), status, (unsigned)parts,
            (unsigned)completed_parts, (unsigned)pages, (unsigned)text_bytes,
            status == 0 && pages > 0 && text_bytes > 0 ? "true" : "false");
    fclose(stream);
  }
  return status == 0 && pages > 0 && text_bytes > 0 ? 0 : 1;
}

int main(int argc, char **argv) {
  if (argc != 4) {
    fprintf(stderr, "usage: consumer-c <font> <book> <output.json>\n");
    return 2;
  }
  return run(argv[1], argv[2], argv[3]) == 0 ? 0 : 1;
}
