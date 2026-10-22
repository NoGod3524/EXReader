/* SPDX-License-Identifier: MIT */
/* Stand-alone consumer: catalog -> (follow sections) -> (search) -> page through results ->
   pick a publication -> download -> open with the public EXReader SDK.
   opds_consume --start URL --out DIR [--follow TITLE]... [--search TERMS] [--pick TITLE]
                [--type MIME] [--max-pages N] [--replace] [--auth-env VAR [--auth-origin URL]]
   Prints one JSON line. Exit 0 only when the book was published and the SDK read it. */
#include "opds.h"
#include "opds_sdk.h"
#include "exreader.h"
#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static opds_status fail(opds_error *e, opds_status c, const char *fmt, ...) {
  va_list ap;
  e->code = c;
  va_start(ap, fmt);
  vsnprintf(e->message, sizeof e->message, fmt, ap);
  va_end(ap);
  return c;
}

static void json_str(const char *s) {
  putchar('"');
  for (; s && *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
    else if (c < 0x20) printf("\\u%04x", c);
    else putchar(c);
  }
  putchar('"');
}

static void safe_name(const char *title, const char *type, char *out, size_t cap) {
  size_t n = 0;
  const char *ext = type && strstr(type, "epub") ? ".epub" : type && strstr(type, "pdf") ? ".pdf" : ".bin";
  for (; title && *title && n + 8 < cap; title++) {
    unsigned char c = (unsigned char)*title;
    out[n++] = (c < 0x80 && (isalnum(c) || c == '-' || c == '_')) ? (char)c : '_';
  }
  if (!n) out[n++] = 'b';
  snprintf(out + n, cap - n, "%s", ext);
}

static const opds_entry *find_entry(const opds_feed *f, const char *needle, int want_publication, const char *type) {
  for (size_t i = 0; i < f->entry_count; i++) {
    const opds_entry *e = &f->entries[i];
    if (needle && !strstr(e->title, needle)) continue;
    if (want_publication) {
      if (e->is_publication && opds_entry_acquisition(e, type)) return e;
    } else {
      for (size_t k = 0; k < e->link_count; k++)
        if (e->links[k].kind == OPDS_REL_SUBSECTION || (e->links[k].kind == OPDS_REL_OTHER && !e->is_publication && e->links[k].type &&
            strstr(e->links[k].type, "opds"))) return e;
    }
  }
  return NULL;
}

static const char *nav_href(const opds_entry *e) {
  for (size_t k = 0; k < e->link_count; k++) if (e->links[k].acq == OPDS_ACQ_NONE && e->links[k].kind != OPDS_REL_IMAGE && e->links[k].kind != OPDS_REL_THUMBNAIL) return e->links[k].href;
  return NULL;
}

static int consume(int argc, char **argv) {
  const char *start = NULL, *out_dir = NULL, *search = NULL, *pick = NULL, *type = "application/epub+zip", *auth_env = NULL, *auth_origin = NULL;
  const char *follow[8];
  size_t nfollow = 0, max_pages = 20, pages = 0;
  int replace = 0;
  opds_config cfg;
  opds_client *client;
  opds_feed feed, next;
  opds_error err;
  opds_status st;
  char url[4096], dest[1024], name[200];
  opds_download_result dr;
  opds_download_options opt;
  const char *stage = "start";
  const opds_entry *chosen = NULL;
  const opds_link *link = NULL;
  char *auth_value = NULL;
  char title[256] = "", detail[200] = "";
  size_t parts = 0;
  int ok = 0;

  for (int i = 1; i < argc; i++) {
    const char *a = argv[i];
    if (!strcmp(a, "--start") && i + 1 < argc) start = argv[++i];
    else if (!strcmp(a, "--out") && i + 1 < argc) out_dir = argv[++i];
    else if (!strcmp(a, "--search") && i + 1 < argc) search = argv[++i];
    else if (!strcmp(a, "--pick") && i + 1 < argc) pick = argv[++i];
    else if (!strcmp(a, "--type") && i + 1 < argc) type = argv[++i];
    else if (!strcmp(a, "--follow") && i + 1 < argc && nfollow < 8) follow[nfollow++] = argv[++i];
    else if (!strcmp(a, "--max-pages") && i + 1 < argc) max_pages = (size_t)strtoul(argv[++i], NULL, 10);
    else if (!strcmp(a, "--auth-env") && i + 1 < argc) auth_env = argv[++i];
    else if (!strcmp(a, "--auth-origin") && i + 1 < argc) auth_origin = argv[++i];
    else if (!strcmp(a, "--replace")) replace = 1;
    else { fprintf(stderr, "unknown or incomplete option %s\n", a); return 2; }
  }
  if (!start || !out_dir) { fprintf(stderr, "usage: opds_consume --start URL --out DIR [...]\n"); return 2; }
  opds_config_defaults(&cfg);
  cfg.limits.max_pages = max_pages;
  if (auth_env) {
    const char *v = getenv(auth_env);
    if (v && *v) { auth_value = (char *)malloc(strlen(v) + 1); if (auth_value) strcpy(auth_value, v); }
    cfg.credential_origin = auth_origin ? auth_origin : start;
    cfg.authorization = auth_value;
  }
  client = opds_client_create(&cfg);
  if (!client) { fprintf(stderr, "cannot create client\n"); return 2; }
  memset(&err, 0, sizeof err); memset(&feed, 0, sizeof feed); memset(&dr, 0, sizeof dr);
  opds_client_begin_crawl(client);

  stage = "catalog";
  st = opds_fetch_feed(client, start, NULL, &feed, &err);
  for (size_t i = 0; st == OPDS_OK && i < nfollow; i++) {
    const opds_entry *e = find_entry(&feed, follow[i], 0, NULL);
    const char *href = e ? nav_href(e) : NULL;
    stage = "navigate";
    if (!href) { st = fail(&err, OPDS_FORMAT, "no navigation entry matching '%s'", follow[i]); break; }
    snprintf(url, sizeof url, "%s", href);
    opds_feed_free(&feed);
    st = opds_fetch_feed(client, url, NULL, &feed, &err);
  }
  if (st == OPDS_OK && search) {
    stage = "search";
    st = opds_search_url(client, &feed, search, 1, NULL, url, sizeof url, &err);
    if (st == OPDS_OK) { opds_feed_free(&feed); st = opds_fetch_feed(client, url, NULL, &feed, &err); }
  }
  stage = "select";
  while (st == OPDS_OK) {
    int has_next = 0;
    pages++;
    chosen = find_entry(&feed, pick, 1, type);
    if (chosen) break;
    st = opds_fetch_next(client, &feed, NULL, &next, &has_next, &err);
    if (st != OPDS_OK) break;
    if (!has_next) { st = fail(&err, OPDS_FORMAT, "no publication with an acquisition of %s", type); break; }
    opds_feed_free(&feed);
    feed = next;
  }
  if (st == OPDS_OK && chosen) {
    link = opds_entry_acquisition(chosen, type);
    safe_name(chosen->title, type, name, sizeof name);
    snprintf(dest, sizeof dest, "%s/%s", out_dir, name);
    memset(&opt, 0, sizeof opt);
    opt.media_type = link->type;
    opt.existing = replace ? OPDS_EXISTING_REPLACE : OPDS_EXISTING_FAIL;
    opt.verify = opds_sdk_verify;
    stage = "download";
    st = opds_download(client, link, dest, &opt, NULL, &dr, &err);
    if (st == OPDS_OK) {
      stage = "read";
      if (opds_sdk_read_title(dest, title, sizeof title, &parts, detail, sizeof detail) == OPDS_OK) ok = dr.readable == OPDS_READ_OK;
    }
  }
  {
    unsigned req, red, drop;
    opds_client_stats(client, &req, &red, &drop);
    printf("{\"schema\":1,\"module\":\"opds-client\",\"engine\":");
    json_str(exr_version());
    printf(",\"stage\":"); json_str(stage);
    printf(",\"status\":"); json_str(opds_status_name(st));
    printf(",\"message\":"); json_str(st == OPDS_OK ? "" : err.message);
    printf(",\"http_status\":%d,\"pages\":%zu,\"requests\":%u,\"redirects\":%u,\"credentials_dropped\":%u", err.http_status, pages, req, red, drop);
    printf(",\"selected\":"); json_str(chosen ? chosen->title : "");
    printf(",\"published\":%s,\"already_present\":%s,\"bytes\":%llu,\"sha256\":", dr.published ? "true" : "false", dr.already_present ? "true" : "false", (unsigned long long)dr.bytes);
    json_str(dr.sha256);
    printf(",\"sniffed_type\":"); json_str(dr.sniffed_type);
    printf(",\"readable\":\"%s\",\"sdk_title\":", dr.readable == OPDS_READ_OK ? "ok" : dr.readable == OPDS_READ_FAILED ? "failed" : "unknown");
    json_str(title);
    printf(",\"sdk_parts\":%zu}\n", parts);
  }
  opds_feed_free(&feed);
  opds_client_free(client);
  if (auth_value) { memset(auth_value, 0, strlen(auth_value)); free(auth_value); }
  return ok ? 0 : 1;
}

#define example_main consume
#include "entry.h"
