/* SPDX-License-Identifier: MIT */
#include "reader_opds_import.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

typedef struct {
  uint32_t h[8];
  uint64_t len;
  unsigned char buf[64];
  size_t n;
} sha_ctx;

static const uint32_t K[64] = {
  0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
  0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
  0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
  0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
  0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
  0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
  0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
  0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
#define ROR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static void sha_block(sha_ctx *c, const unsigned char *p) {
  uint32_t w[64], a, b, d, e, f, g, h, cc;
  int i;
  for (i = 0; i < 16; i++)
    w[i] = ((uint32_t)p[4 * i] << 24) | ((uint32_t)p[4 * i + 1] << 16) | ((uint32_t)p[4 * i + 2] << 8) | p[4 * i + 3];
  for (i = 16; i < 64; i++) {
    uint32_t s0 = ROR(w[i - 15], 7) ^ ROR(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = ROR(w[i - 2], 17) ^ ROR(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  a = c->h[0]; b = c->h[1]; cc = c->h[2]; d = c->h[3]; e = c->h[4]; f = c->h[5]; g = c->h[6]; h = c->h[7];
  for (i = 0; i < 64; i++) {
    uint32_t S1 = ROR(e, 6) ^ ROR(e, 11) ^ ROR(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = h + S1 + ch + K[i] + w[i];
    uint32_t S0 = ROR(a, 2) ^ ROR(a, 13) ^ ROR(a, 22);
    uint32_t mj = (a & b) ^ (a & cc) ^ (b & cc);
    uint32_t t2 = S0 + mj;
    h = g; g = f; f = e; e = d + t1; d = cc; cc = b; b = a; a = t1 + t2;
  }
  c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d; c->h[4] += e; c->h[5] += f; c->h[6] += g; c->h[7] += h;
}

static void sha_init(sha_ctx *c) {
  static const uint32_t init[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
  memcpy(c->h, init, sizeof init);
  c->len = 0;
  c->n = 0;
}

static void sha_update(sha_ctx *c, const unsigned char *d, size_t n) {
  c->len += n;
  while (n) {
    size_t take = 64 - c->n;
    if (take > n) take = n;
    memcpy(c->buf + c->n, d, take);
    c->n += take; d += take; n -= take;
    if (c->n == 64) { sha_block(c, c->buf); c->n = 0; }
  }
}

static void sha_final(sha_ctx *c, char hex[65]) {
  static const char digits[] = "0123456789abcdef";
  uint64_t bits = c->len * 8;
  unsigned char pad = 0x80, zero = 0, len[8];
  int i;
  sha_update(c, &pad, 1);
  while (c->n != 56) sha_update(c, &zero, 1);
  for (i = 0; i < 8; i++) len[i] = (unsigned char)(bits >> (56 - 8 * i));
  sha_update(c, len, 8);
  for (i = 0; i < 8; i++) {
    int k;
    for (k = 0; k < 4; k++) {
      unsigned char byte = (unsigned char)(c->h[i] >> (24 - 8 * k));
      hex[i * 8 + k * 2] = digits[byte >> 4];
      hex[i * 8 + k * 2 + 1] = digits[byte & 15];
    }
  }
  hex[64] = 0;
}

static FILE *open_read(const char *path) {
#ifdef _WIN32
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, NULL, 0);
  wchar_t *wide;
  FILE *f;
  if (count <= 0) return NULL;
  wide = (wchar_t *)malloc((size_t)count * sizeof(*wide));
  if (!wide) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, path, -1, wide, count)) { free(wide); return NULL; }
  f = _wfopen(wide, L"rb");
  free(wide);
  return f;
#else
  return fopen(path, "rb");
#endif
}

static void set_error(exr_error *error, exr_status code, const char *message) {
  if (!error) return;
  error->code = code;
  snprintf(error->message, sizeof error->message, "%s", message);
}

/* Returns 0 when the file has exactly the recorded size and digest. */
static int check_staged(const reader_opds_acquired *staged, const exr_control *control, exr_error *error,
                        exr_status *status) {
  FILE *f = open_read(staged->path);
  unsigned char buffer[65536];
  sha_ctx c;
  uint64_t total = 0;
  char hex[65];
  size_t n;
  if (!f) { *status = EXR_IO; set_error(error, EXR_IO, "Cannot open the staged file"); return 1; }
  sha_init(&c);
  while ((n = fread(buffer, 1, sizeof buffer, f)) > 0) {
    if (control && control->cancelled && control->cancelled(control->context)) {
      fclose(f);
      *status = EXR_CANCELLED;
      set_error(error, EXR_CANCELLED, "Cancelled while verifying the staged file");
      return 1;
    }
    total += n;
    if (total > staged->bytes) break;
    sha_update(&c, buffer, n);
  }
  if (ferror(f)) { fclose(f); *status = EXR_IO; set_error(error, EXR_IO, "Cannot read the staged file"); return 1; }
  fclose(f);
  if (total != staged->bytes) {
    *status = EXR_IO;
    set_error(error, EXR_IO, "Staged file size differs from the network phase");
    return 1;
  }
  sha_final(&c, hex);
  if (strcmp(hex, staged->sha256)) {
    *status = EXR_IO;
    set_error(error, EXR_IO, "Staged file digest differs from the network phase");
    return 1;
  }
  return 0;
}

exr_status reader_opds_import_staged(exr_library *library, const reader_opds_acquired *staged,
                                     const char *title, const exr_control *control,
                                     exr_sideload_result *result, exr_error *error) {
  exr_format format;
  exr_sideload_options options;
  exr_status status = EXR_OK;
  if (error) { memset(error, 0, sizeof *error); }
  if (result) { memset(result, 0, sizeof *result); result->struct_size = sizeof *result; }
  if (!library || !staged || !result || staged->struct_size < sizeof *staged || !staged->path[0]) {
    set_error(error, EXR_ARGUMENT, "library, staged file and result are required");
    return EXR_ARGUMENT;
  }
  if (staged->bytes == 0 || strlen(staged->sha256) != 64) {
    set_error(error, EXR_ARGUMENT, "the staged descriptor has no size or digest");
    return EXR_ARGUMENT;
  }
  if (!strcmp(staged->media_type, "application/epub+zip")) format = EXR_EPUB;
  else if (!strcmp(staged->media_type, "application/pdf")) format = EXR_PDF;
  else if (!strcmp(staged->media_type, "application/vnd.comicbook+zip") || !strcmp(staged->media_type, "application/x-cbz")) format = EXR_CBZ;
  else {
    set_error(error, EXR_UNSUPPORTED, "Staged media type cannot be imported");
    return EXR_UNSUPPORTED;
  }
  if (check_staged(staged, control, error, &status)) return status;
  memset(&options, 0, sizeof options);
  options.struct_size = sizeof options;
  if (control) options.control = *control;
  return exr_sideload_import_file(library, format, staged->path, title && *title ? title : "OPDS book", &options,
                                  result, error);
}
