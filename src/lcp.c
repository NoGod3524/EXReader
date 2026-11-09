/* SPDX-License-Identifier: MIT */
#include "lcp_internal.h"
#include <expat.h>
#include <time.h>
#ifdef EXR_ENABLE_LCP
#include <mbedtls/aes.h>
#include <mbedtls/base64.h>
#include <mbedtls/platform_util.h>
#include <mbedtls/sha256.h>
#endif

#define LCP_AES "http://www.w3.org/2001/04/xmlenc#aes256-cbc"
#define LCP_SHA "http://www.w3.org/2001/04/xmlenc#sha256"
#define LCP_BASIC "http://readium.org/lcp/basic-profile"
#define LCP_KEY "http://readium.org/2014/01/lcp#EncryptedContentKey"
#define LCP_MEMBER_LIMIT (32u * 1024u * 1024u)

typedef struct {
  char *path;
  size_t length;
  int method, has_length;
} lcp_resource;
typedef struct {
  unsigned char key[32];
  lcp_resource *resources;
  size_t count, capacity;
} lcp;

void exr_lcp_free(void *context) {
  lcp *p = context;
  size_t i;
  if (!p) return;
  for (i = 0; i < p->count; i++) free(p->resources[i].path);
  free(p->resources);
#ifdef EXR_ENABLE_LCP
  mbedtls_platform_zeroize(p->key, sizeof(p->key));
#endif
  free(p);
}
static const lcp_resource *resource(const void *context, const char *path) {
  const lcp *p = context;
  size_t i;
  if (p) for (i = 0; i < p->count; i++)
    if (!strcmp(p->resources[i].path, path)) return &p->resources[i];
  return NULL;
}
int exr_lcp_has(const void *context, const char *path) { return resource(context, path) != NULL; }

#ifdef EXR_ENABLE_LCP
/* Bounded, schema-directed JSON reader. Unknown extension values are validated
   and skipped; strings are decoded before matching names or using key_check. */
enum { J_ID, J_PROFILE, J_CONTENT_ALGORITHM, J_CONTENT_KEY, J_USER_ALGORITHM,
       J_CHECK, J_HINT, J_END, J_START, J_SIGNATURE, J_FIELDS };
typedef struct { const char *at, *end; char *values[J_FIELDS]; size_t nodes; } json;
typedef struct { int parent; const char *name; int child, field; } json_field;
static const json_field fields[] = {
  {1,"id",0,J_ID}, {1,"encryption",2,-1}, {1,"rights",5,-1}, {1,"signature",6,-1},
  {2,"profile",0,J_PROFILE}, {2,"content_key",3,-1}, {2,"user_key",4,-1},
  {3,"algorithm",0,J_CONTENT_ALGORITHM}, {3,"encrypted_value",0,J_CONTENT_KEY},
  {4,"algorithm",0,J_USER_ALGORITHM}, {4,"key_check",0,J_CHECK}, {4,"text_hint",0,J_HINT},
  {5,"end",0,J_END}, {5,"start",0,J_START}, {6,"algorithm",0,J_SIGNATURE}
};
static void whitespace(json *j) {
  while (j->at < j->end && *j->at && strchr(" \r\n\t", *j->at)) j->at++;
}
static int take(json *j, char c) {
  whitespace(j);
  if (j->at == j->end || *j->at != c) return 0;
  j->at++; return 1;
}
static int hex4(json *j, uint32_t *value) {
  unsigned i;
  *value = 0;
  if (j->end - j->at < 4) return 0;
  for (i = 0; i < 4; i++) {
    unsigned char c = (unsigned char)*j->at++;
    unsigned v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 :
                 c >= 'A' && c <= 'F' ? c - 'A' + 10 : 16;
    if (v == 16) return 0;
    *value = (*value << 4) | v;
  }
  return 1;
}
static int string(json *j, char **out) {
  static const char escapes[] = "\"\\/bfnrt", escaped[] = "\"\\/\b\f\n\r\t";
  exr_buffer b = {0};
  int ok = 0;
  *out = NULL;
  if (!take(j, '"')) return 0;
  while (j->at < j->end) {
    unsigned char c = (unsigned char)*j->at++;
    if (c == '"') { ok = 1; break; }
    if (c < 32) break;
    if (c == '\\') {
      const char *escape;
      uint32_t cp, low;
      if (j->at == j->end) break;
      c = (unsigned char)*j->at++;
      if (c == 'u') {
        if (!hex4(j, &cp)) break;
        if (cp >= 0xd800 && cp <= 0xdbff) {
          if (j->end - j->at < 6 || j->at[0] != '\\' || j->at[1] != 'u') break;
          j->at += 2;
          if (!hex4(j, &low) || low < 0xdc00 || low > 0xdfff) break;
          cp = 0x10000 + ((cp - 0xd800) << 10) + low - 0xdc00;
        }
        /* Embedded NULs cannot be represented in the C-string license schema. */
        if (!cp || (cp >= 0xd800 && cp <= 0xdfff) || !exr_codepoint(&b, cp)) break;
        continue;
      }
      escape = strchr(escapes, c);
      if (!escape || !c) break;
      c = (unsigned char)escaped[escape - escapes];
    }
    if (!exr_append(&b, &c, 1)) break;
  }
  if (ok) {
    size_t at = 0;
    uint32_t cp;
    while (at < b.size) if (!exr_next(b.data, b.size, &at, &cp)) { ok = 0; break; }
  }
  if (ok) *out = b.data ? b.data : exr_copy("", 0);
  else free(b.data);
  return ok && *out;
}
static int digit(json *j) { return j->at < j->end && *j->at >= '0' && *j->at <= '9'; }
static int value(json *j, int context, unsigned depth) {
  unsigned seen = 0;
  if (depth > 32 || ++j->nodes > 8192) return 0;
  whitespace(j);
  if (j->at == j->end) return 0;
  if (context && *j->at != '{') return 0;
  if (take(j, '{')) {
    if (take(j, '}')) return 1;
    do {
      char *key = NULL;
      size_t k;
      int child = 0, field = -1, ok;
      if (!string(j, &key)) return 0;
      for (k = 0; k < sizeof(fields) / sizeof(*fields); k++)
        if (fields[k].parent == context && !strcmp(key, fields[k].name)) {
          if (seen & (1u << k)) { free(key); return 0; }
          seen |= 1u << k; child = fields[k].child; field = fields[k].field; break;
        }
      free(key);
      if (!take(j, ':')) return 0;
      ok = field >= 0 ? string(j, &j->values[field]) : value(j, child, depth + 1);
      if (!ok) return 0;
      if (take(j, '}')) return 1;
    } while (take(j, ','));
    return 0;
  }
  if (take(j, '[')) {
    if (take(j, ']')) return 1;
    do {
      if (!value(j, 0, depth + 1)) return 0;
      if (take(j, ']')) return 1;
    } while (take(j, ','));
    return 0;
  }
  if (*j->at == '"') { char *s = NULL; int ok = string(j, &s); free(s); return ok; }
  if (*j->at == '-' || digit(j)) {
    if (*j->at == '-') j->at++;
    if (!digit(j)) return 0;
    if (*j->at == '0') j->at++;
    else while (digit(j)) j->at++;
    if (j->at < j->end && *j->at == '.') {
      j->at++; if (!digit(j)) return 0; while (digit(j)) j->at++;
    }
    if (j->at < j->end && (*j->at == 'e' || *j->at == 'E')) {
      j->at++;
      if (j->at < j->end && (*j->at == '+' || *j->at == '-')) j->at++;
      if (!digit(j)) return 0;
      while (digit(j)) j->at++;
    }
    return 1;
  }
  { const char *words[] = {"true", "false", "null"}; size_t i;
    for (i = 0; i < 3; i++) { size_t n = strlen(words[i]);
      if ((size_t)(j->end - j->at) >= n && !memcmp(j->at, words[i], n)) { j->at += n; return 1; }
    }
  }
  return 0;
}
/* RFC3339 with offsets and fractional seconds, independent of local timezone. */
static int digits(const char **at, unsigned count, int *out) {
  unsigned i;
  *out = 0;
  for (i = 0; i < count; i++) {
    unsigned char c = (unsigned char)**at;
    if (c < '0' || c > '9') return 0;
    *out = *out * 10 + c - '0'; (*at)++;
  }
  return 1;
}
static int timestamp(const char *s, double *out) {
  int year, month, day, hour, minute, second, oh = 0, om = 0, sign = 1, y, m;
  int64_t days = 0;
  double fraction = 0, scale = 0.1;
  static const int months[] = {31,28,31,30,31,30,31,31,30,31,30,31};
  if (!digits(&s,4,&year) || *s++ != '-' || !digits(&s,2,&month) || *s++ != '-' ||
      !digits(&s,2,&day) || (*s != 'T' && *s != 't')) return 0;
  s++;
  if (!digits(&s,2,&hour) || *s++ != ':' || !digits(&s,2,&minute) || *s++ != ':' ||
      !digits(&s,2,&second) || year < 1 || month < 1 || month > 12 || day < 1 ||
      day > months[month-1] + (month == 2 && !(year%4) && (year%100 || !(year%400))) ||
      hour > 23 || minute > 59 || second > 59) return 0;
  if (*s == '.') {
    s++; if (*s < '0' || *s > '9') return 0;
    while (*s >= '0' && *s <= '9') { fraction += (*s++ - '0') * scale; scale *= 0.1; }
  }
  if (*s == 'Z' || *s == 'z') s++;
  else {
    if (*s != '+' && *s != '-') return 0;
    if (*s++ == '-') sign = -1;
    if (!digits(&s,2,&oh) || *s++ != ':' || !digits(&s,2,&om) || oh > 23 || om > 59) return 0;
  }
  if (*s) return 0;
  y = year - 1;
  days = (int64_t)y * 365 + y/4 - y/100 + y/400 - 719162;
  for (m = 1; m < month; m++) days += months[m-1] + (m == 2 && !(year%4) && (year%100 || !(year%400)));
  days += day - 1;
  *out = (double)days * 86400 + hour * 3600 + minute * 60 + second + fraction - sign * (oh * 3600 + om * 60);
  return 1;
}
/* XML Encryption CBC: IV prefix, final byte gives 1..16 padding octets.
   The preceding padding bytes are arbitrary, not necessarily PKCS#7 repeats. */
static int decrypt(const unsigned char key[32], unsigned char *data, size_t *size) {
  mbedtls_aes_context aes;
  unsigned char iv[16];
  size_t n = *size;
  unsigned padding;
  int rc;
  if (n < 32 || n % 16) return 0;
  memcpy(iv, data, 16);
  mbedtls_aes_init(&aes);
  rc = mbedtls_aes_setkey_dec(&aes, key, 256);
  if (!rc) rc = mbedtls_aes_crypt_cbc(&aes, MBEDTLS_AES_DECRYPT, n - 16, iv, data + 16, data + 16);
  mbedtls_aes_free(&aes);
  mbedtls_platform_zeroize(iv, sizeof(iv));
  if (rc) return 0;
  padding = data[n-1];
  if (!padding || padding > 16 || padding > n - 16) return 0;
  *size = n - 16 - padding;
  memmove(data, data + 16, *size);
  mbedtls_platform_zeroize(data + *size, n - *size);
  return 1;
}
static int decoded(const char *s, unsigned char *out, size_t capacity, size_t *size) {
  return s && mbedtls_base64_decode(out, capacity, size, (const unsigned char *)s, strlen(s)) == 0;
}
static exr_status license(const void *bytes, size_t n, const char *passphrase, lcp *p, exr_error *e) {
  json j = {0};
  unsigned char user[32] = {0}, check[2048] = {0}, content[64] = {0};
  size_t size = 0, i;
  double start = 0, end = 0, now = (double)time(NULL);
  exr_status status = EXR_DRM_LICENSE_INVALID;
  char **v = j.values;
  j.at = bytes; j.end = j.at + n;
  if (!value(&j, 1, 0)) goto malformed;
  whitespace(&j);
  if (j.at != j.end || !v[J_ID] || !*v[J_ID] || strlen(v[J_ID]) > 1024 ||
      !v[J_PROFILE] || !v[J_CONTENT_ALGORITHM] || !v[J_CONTENT_KEY] ||
      !v[J_USER_ALGORITHM] || !v[J_CHECK]) goto malformed;
  if (strcmp(v[J_PROFILE], LCP_BASIC) || strcmp(v[J_CONTENT_ALGORITHM], LCP_AES) ||
      strcmp(v[J_USER_ALGORITHM], LCP_SHA) || (v[J_SIGNATURE] &&
      strcmp(v[J_SIGNATURE], "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"))) {
    status = exr_fail(e, EXR_DRM_UNSUPPORTED, "Unsupported LCP profile or algorithm: %.100s", v[J_PROFILE]);
    goto done;
  }
  if ((v[J_END] && !timestamp(v[J_END], &end)) || (v[J_START] && !timestamp(v[J_START], &start)) ||
      (v[J_END] && v[J_START] && end < start)) goto malformed;
  if (now == -1) { status = exr_fail(e, EXR_IO, "Cannot read clock for LCP license validity"); goto done; }
  if (v[J_END] && now >= end) {
    status = exr_fail(e, EXR_DRM_LICENSE_EXPIRED, "LCP license expired at %.100s", v[J_END]); goto done;
  }
  if (v[J_START] && now < start) {
    status = exr_fail(e, EXR_DRM_LICENSE_INVALID, "LCP license is not valid before %.100s", v[J_START]); goto done;
  }
  if (!passphrase) {
    status = exr_fail(e, EXR_DRM_PASSPHRASE_REQUIRED, "LCP passphrase required. %.180s", v[J_HINT] ? v[J_HINT] : "");
    goto done;
  }
  size = strlen(passphrase);
  if (size > 65536) { status = exr_fail(e, EXR_LIMIT, "LCP passphrase exceeds 64 KiB"); goto done; }
  { size_t at = 0; uint32_t cp;
    while (at < size) if (!exr_next(passphrase, size, &at, &cp)) {
      status = exr_fail(e, EXR_ENCODING, "LCP passphrase must be UTF-8"); goto done;
    }
  }
  if (mbedtls_sha256((const unsigned char *)passphrase, size, user, 0)) goto malformed;
  if (!decoded(v[J_CHECK], check, sizeof(check), &size) || size < 32 || size % 16) goto malformed;
  if (!decrypt(user, check, &size) || size != strlen(v[J_ID]) || memcmp(check, v[J_ID], size)) {
    status = exr_fail(e, EXR_DRM_PASSPHRASE_INCORRECT, "Incorrect LCP passphrase (license key_check mismatch)");
    goto done;
  }
  if (!decoded(v[J_CONTENT_KEY], content, sizeof(content), &size) ||
      !decrypt(user, content, &size) || size != 32) goto malformed;
  memcpy(p->key, content, 32); status = EXR_OK; goto done;
malformed:
  status = exr_fail(e, EXR_DRM_LICENSE_INVALID, "Malformed LCP license, validity dates, or encrypted key");
done:
  for (i = 0; i < J_FIELDS; i++) free(v[i]);
  mbedtls_platform_zeroize(user, sizeof(user));
  mbedtls_platform_zeroize(check, sizeof(check));
  mbedtls_platform_zeroize(content, sizeof(content));
  return status;
}

typedef struct {
  XML_Parser parser;
  lcp *lcp;
  mz_zip_archive *zip;
  exr_error *error;
  exr_status status;
  unsigned depth, entry_depth, seen;
  int obfuscated, licensed;
  lcp_resource entry;
} directory;
static const char *attr(const char **attrs, const char *name) {
  size_t i;
  for (i = 0; attrs && attrs[i]; i += 2) if (!strcmp(attrs[i], name)) return attrs[i+1];
  return NULL;
}
static void directory_fail(directory *d, exr_status status, const char *reason) {
  if (d->status != EXR_OK) return;
  d->status = exr_fail(d->error, status, "%s", reason);
  XML_StopParser(d->parser, XML_FALSE);
}
static int decimal(const char *s, size_t *n) {
  *n = 0;
  if (!s || !*s) return 0;
  while (*s) {
    if (*s < '0' || *s > '9' || *n > (LCP_MEMBER_LIMIT - (unsigned)(*s-'0'))/10) return 0;
    *n = *n * 10 + (unsigned)(*s++ - '0');
  }
  return 1;
}
#define ENC "http://www.w3.org/2001/04/xmlenc#|"
#define DS "http://www.w3.org/2000/09/xmldsig#|"
#define COMP "http://www.idpf.org/2016/encryption#compression|"
static void XMLCALL directory_start(void *context, const char *name, const char **attrs) {
  directory *d = context;
  const char *a;
  unsigned bit = 0;
  if (++d->depth > 32) { directory_fail(d, EXR_LIMIT, "LCP encryption XML is too deep"); return; }
  /* Unlicensed EPUBs historically permit an empty <encryption/> marker.
     Only a declared LCP license requires the OCF directory root here. */
  if (d->licensed && d->depth == 1 && strcmp(name, "urn:oasis:names:tc:opendocument:xmlns:container|encryption")) {
    directory_fail(d, EXR_DRM_LICENSE_INVALID, "Invalid EPUB encryption XML root"); return;
  }
  if (!strcmp(name, ENC "EncryptedData")) {
    if (d->entry_depth) { directory_fail(d, EXR_DRM_LICENSE_INVALID, "Nested LCP EncryptedData"); return; }
    d->entry_depth = d->depth; d->seen = 0; d->obfuscated = 0; return;
  }
  if (!d->entry_depth || d->status != EXR_OK) return;
  if (!strcmp(name, ENC "EncryptionMethod")) {
    bit = 1; a = attr(attrs, "Algorithm");
    d->obfuscated = a && (!strcmp(a, "http://www.idpf.org/2008/embedding") || !strcmp(a, "http://ns.adobe.com/pdf/enc#RC"));
    if (!a || (!d->obfuscated && strcmp(a, LCP_AES)))
      directory_fail(d, EXR_DRM_UNSUPPORTED, "Unsupported EPUB resource encryption algorithm (Adobe ADEPT is not supported)");
  } else if (!strcmp(name, DS "RetrievalMethod")) {
    const char *type = attr(attrs, "Type");
    bit = 2; a = attr(attrs, "URI");
    if (!a || !type || strcmp(type, LCP_KEY) || (strcmp(a, "license.lcpl#/encryption/content_key") &&
        strcmp(a, "license.lcp.json#/encryption/content_key")))
      directory_fail(d, EXR_DRM_UNSUPPORTED, "Unsupported LCP content key reference");
  } else if (!strcmp(name, ENC "CipherReference")) {
    char path[2048];
    bit = 4; a = attr(attrs, "URI");
    if (!a || !exr_resolve_path("", a, path) || !path[0] || strchr(a, '#') || strchr(a, '?') ||
        !strncmp(path, "META-INF/", 9) || !strcmp(path, "mimetype") ||
        mz_zip_reader_locate_file(d->zip, path, NULL, MZ_ZIP_FLAG_CASE_SENSITIVE) < 0)
      directory_fail(d, EXR_DRM_LICENSE_INVALID, "LCP encrypted resource path is unsafe or missing");
    else if (!(d->seen & bit)) {
      d->entry.path = exr_copy(path, strlen(path));
      if (!d->entry.path) directory_fail(d, EXR_MEMORY, "LCP resource path allocation failed");
    }
  } else if (!strcmp(name, COMP "Compression")) {
    bit = 8; a = attr(attrs, "Method");
    if (!a || (strcmp(a, "0") && strcmp(a, "8")))
      directory_fail(d, EXR_DRM_UNSUPPORTED, "Unsupported LCP resource compression method");
    else {
      d->entry.method = *a == '8' ? 8 : 0;
      d->entry.has_length = decimal(attr(attrs, "OriginalLength"), &d->entry.length);
      if (!d->entry.has_length) directory_fail(d, EXR_LIMIT, "Invalid LCP OriginalLength or exceeds 32 MiB");
    }
  }
  if (bit && (d->seen & bit)) directory_fail(d, EXR_DRM_LICENSE_INVALID, "Duplicate LCP encryption property");
  d->seen |= bit;
}
static void XMLCALL directory_end(void *context, const char *name) {
  directory *d = context;
  if (!strcmp(name, ENC "EncryptedData") && d->entry_depth == d->depth) {
    if ((d->seen & 5) != 5 || (!d->obfuscated && !(d->seen & 2)))
      directory_fail(d, EXR_DRM_LICENSE_INVALID, "Incomplete LCP encryption entry");
    else if (!d->obfuscated && d->status == EXR_OK) {
      if (resource(d->lcp, d->entry.path)) directory_fail(d, EXR_DRM_LICENSE_INVALID, "Duplicate LCP encrypted resource");
      else if (d->lcp->count >= 10000 || !exr_grow((void **)&d->lcp->resources, &d->lcp->capacity,
                                                 d->lcp->count + 1, sizeof(lcp_resource)))
        directory_fail(d, EXR_LIMIT, "LCP encryption directory exceeds limit");
      else { d->lcp->resources[d->lcp->count++] = d->entry; d->entry.path = NULL; }
    }
    free(d->entry.path); memset(&d->entry, 0, sizeof(d->entry)); d->entry_depth = 0;
  }
  d->depth--;
}
static void XMLCALL directory_doctype(void *context, const char *name, const char *sysid, const char *pubid, int subset) {
  (void)name; (void)sysid; (void)pubid; (void)subset;
  directory_fail(context, EXR_DRM_LICENSE_INVALID, "DTD is not allowed in LCP encryption metadata");
}
static void *metadata(mz_zip_archive *zip, int index, size_t limit, size_t *size, exr_error *e) {
  mz_zip_archive_file_stat stat;
  void *bytes;
  if (index < 0 || !mz_zip_reader_file_stat(zip, (mz_uint)index, &stat) || stat.m_is_encrypted) {
    exr_fail(e, EXR_DRM_LICENSE_INVALID, "Missing or encrypted LCP metadata"); return NULL;
  }
  if (stat.m_uncomp_size > limit) { exr_fail(e, EXR_LIMIT, "LCP metadata exceeds limit"); return NULL; }
  bytes = mz_zip_reader_extract_to_heap(zip, (mz_uint)index, size, 0);
  if (!bytes) exr_fail(e, EXR_DRM_LICENSE_INVALID, "Cannot extract LCP metadata");
  return bytes;
}
#endif

exr_status exr_lcp_open(mz_zip_archive *zip, const char *passphrase, void **out, exr_error *e) {
  int index = mz_zip_reader_locate_file(zip, "META-INF/license.lcpl", NULL, MZ_ZIP_FLAG_CASE_SENSITIVE);
  int alias = mz_zip_reader_locate_file(zip, "META-INF/license.lcp.json", NULL, MZ_ZIP_FLAG_CASE_SENSITIVE);
  int encryption = mz_zip_reader_locate_file(zip, "META-INF/encryption.xml", NULL, MZ_ZIP_FLAG_CASE_SENSITIVE);
  *out = NULL;
  if (mz_zip_reader_locate_file(zip, "META-INF/rights.xml", NULL, MZ_ZIP_FLAG_CASE_SENSITIVE) >= 0)
    return exr_fail(e, EXR_DRM_UNSUPPORTED, "Adobe ADEPT is not supported; an authorized EPUB, license and user key are required");
  if (index >= 0 && alias >= 0) return exr_fail(e, EXR_DRM_LICENSE_INVALID, "Ambiguous EPUB: two LCP licenses");
  if (index < 0) index = alias;
  if (index < 0 && encryption < 0) return EXR_OK;
#ifdef EXR_ENABLE_LCP
  {
    exr_error local = {0};
    lcp *p = calloc(1, sizeof(*p));
    size_t n = 0;
    void *bytes;
    exr_status status;
    directory d = {0};
    if (!e) e = &local;
    if (!p) return exr_fail(e, EXR_MEMORY, "LCP allocation failed");
    status = EXR_OK;
    if (index >= 0) {
      bytes = metadata(zip, index, 65536, &n, e);
      status = bytes ? license(bytes, n, passphrase, p, e) : e->code;
      mz_free(bytes);
    }
    if (status != EXR_OK) { exr_lcp_free(p); return status; }
    bytes = metadata(zip, encryption, 4u * 1024u * 1024u, &n, e);
    if (!bytes) { exr_lcp_free(p); return e->code; }
    d.lcp = p; d.zip = zip; d.error = e; d.licensed = index >= 0; d.parser = XML_ParserCreateNS(NULL, '|');
    if (!d.parser) status = exr_fail(e, EXR_MEMORY, "LCP XML parser allocation failed");
    else {
      XML_SetUserData(d.parser, &d);
      XML_SetElementHandler(d.parser, directory_start, directory_end);
      XML_SetStartDoctypeDeclHandler(d.parser, directory_doctype);
      if (XML_Parse(d.parser, bytes, (int)n, XML_TRUE) != XML_STATUS_OK || (index >= 0 && !p->count))
        status = d.status != EXR_OK ? d.status : exr_fail(e, EXR_DRM_LICENSE_INVALID, "Invalid or empty LCP encryption directory");
      XML_ParserFree(d.parser);
    }
    free(d.entry.path); mz_free(bytes);
    if (status == EXR_OK && index < 0 && p->count)
      status = exr_fail(e, EXR_DRM_LICENSE_INVALID, "LCP content key is referenced but META-INF/license.lcpl is missing");
    if (status != EXR_OK || !p->count) exr_lcp_free(p); else *out = p;
    return status;
  }
#else
  (void)passphrase;
  if (index < 0) return EXR_OK; /* Font obfuscation does not require the LCP component. */
  return exr_fail(e, EXR_DRM_UNSUPPORTED, "LCP support is disabled in this build (EXR_ENABLE_LCP=OFF)");
#endif
}

#ifdef EXR_ENABLE_LCP
static void *inflate_alloc(void *context, size_t count, size_t size) {
  const exr_resource_allocator *a = context;
  if (count && size > SIZE_MAX / count) return NULL;
  return a->allocate(a->context, count * size);
}
static void inflate_free(void *context, void *data) {
  const exr_resource_allocator *a = context;
  a->release(a->context, data);
}
#endif
exr_status exr_lcp_decode(void *context, const char *path, void **bytes, size_t *size,
                          const exr_resource_allocator *allocator, exr_error *e) {
#ifdef EXR_ENABLE_LCP
  lcp *p = context;
  const lcp_resource *r = resource(p, path);
  unsigned char *plain;
  mz_stream stream = {0};
  int rc;
  if (!r) return EXR_OK;
  if (!decrypt(p->key, *bytes, size))
    return exr_fail(e, EXR_DRM_LICENSE_INVALID, "Invalid LCP ciphertext or padding: %.160s", path);
  if (r->method == 0) {
    if (r->has_length && *size != r->length)
      return exr_fail(e, EXR_DRM_LICENSE_INVALID, "LCP OriginalLength mismatch: %.160s", path);
    return EXR_OK;
  }
  plain = allocator ? allocator->allocate(allocator->context, r->length ? r->length : 1) : malloc(r->length ? r->length : 1);
  if (!plain) return exr_fail(e, EXR_MEMORY, "LCP resource allocation rejected");
  /* Raw DEFLATE, never a ZIP or zlib wrapper. Limit both output and consumption. */
  stream.next_in = *bytes; stream.avail_in = (mz_uint)*size;
  stream.next_out = plain; stream.avail_out = (mz_uint)(r->length ? r->length : 1);
  if (allocator) { stream.zalloc = inflate_alloc; stream.zfree = inflate_free; stream.opaque = (void *)allocator; }
  rc = mz_inflateInit2(&stream, -MZ_DEFAULT_WINDOW_BITS);
  if (rc == MZ_OK) { rc = mz_inflate(&stream, MZ_FINISH); mz_inflateEnd(&stream); }
  if (rc != MZ_STREAM_END || stream.total_out != r->length || stream.total_in != *size) {
    if (allocator) allocator->release(allocator->context, plain); else free(plain);
    return exr_fail(e, rc == MZ_MEM_ERROR ? EXR_MEMORY : EXR_DRM_LICENSE_INVALID,
                    "Invalid LCP deflate stream, allocation or OriginalLength: %.150s", path);
  }
  mbedtls_platform_zeroize(*bytes, *size);
  if (allocator) allocator->release(allocator->context, *bytes); else free(*bytes);
  *bytes = plain; *size = r->length;
  return EXR_OK;
#else
  (void)context; (void)path; (void)bytes; (void)size; (void)allocator; (void)e;
  return EXR_OK;
#endif
}
