/* Fixed 42-page Latin gate. SHA-256: LE width/height/channels + active RGBA rows. */
#include "exreader.h"
#include <windows.h>
#include <wincrypt.h>
#include <stdio.h>

static int pixels(const exr_bitmap *b, size_t page) {
  HCRYPTPROV provider = 0;
  HCRYPTHASH hash = 0;
  BYTE digest[32];
  DWORD length = sizeof(digest), header[] = {b->width, b->height, b->channels};
  char hex[65];
  int ok = CryptAcquireContextW(&provider, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT) &&
           CryptCreateHash(provider, CALG_SHA_256, 0, 0, &hash);
  if (ok) ok = CryptHashData(hash, (BYTE *)header, sizeof(header), 0);
  for (size_t y = 0; ok && y < b->height; y++)
    ok = CryptHashData(hash, b->pixels + y*b->stride, b->width*b->channels, 0);
  if (ok) ok = CryptGetHashParam(hash, HP_HASHVAL, digest, &length, 0);
  if (hash) CryptDestroyHash(hash);
  if (provider) CryptReleaseContext(provider, 0);
  if (!ok) return 0;
  for (size_t i = 0; i < sizeof(digest); i++) snprintf(hex+2*i, 3, "%02x", digest[i]);
  printf("{\"page\":%zu,\"sha256\":\"%s\"}\n", page, hex);
  return 1;
}

int main(int argc, char **argv) {
  exr_publication *pub = NULL;
  exr_font *font = NULL;
  exr_document *doc = NULL;
  exr_pager *pager = NULL;
  exr_layout *page = NULL;
  exr_bitmap bitmap = {0};
  exr_error error = {0};
  exr_status status;
  size_t parts = 0, pages = 0;
  int failed = 1;
  exr_layout_config config = exr_layout_config_defaults();
  config.page = (exr_layout_options){800,1040,36,28,1.5f,10};
  if (argc != 3) return 2;
  if ((status = exr_font_open(argv[2], &font, &error))) goto done;
  if ((status = exr_publication_open(argv[1], &pub, &error))) goto done;
  exr_publication_parts(pub, &parts);
  for (size_t part = 0; part < parts; part++) {
    if ((status = exr_publication_load(pub, part, &doc, &error))) goto done;
    if ((status = exr_pager_create(doc, font, &config, &pager, &error))) goto done;
    for (;;) {
      if ((status = exr_pager_next(pager, &page, &error))) goto done;
      if (!page) break;
      if ((status = exr_render_page_color(page, exr_layout_font(page), 0, &bitmap, &error))) goto done;
      if (bitmap.width != 800 || bitmap.height != 1040 || bitmap.channels != 4 ||
          !pixels(&bitmap, ++pages)) goto done;
      exr_bitmap_free(&bitmap); exr_layout_free(page); page = NULL;
    }
    exr_pager_free(pager); pager = NULL; exr_document_free(doc); doc = NULL;
  }
  failed = pages != 42;
done:
  if (status) fprintf(stderr, "%s\n", error.message);
  exr_bitmap_free(&bitmap); exr_layout_free(page); exr_pager_free(pager);
  exr_document_free(doc); exr_publication_free(pub); exr_font_free(font);
  return failed;
}
