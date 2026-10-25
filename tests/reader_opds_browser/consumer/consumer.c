/* SPDX-License-Identifier: MIT */
/* Installed-package consumer (C): the network phase of reader_opds_browser against the
   Actions-only fixture origins. Writes one JSON object per named case to the output file
   and exits non-zero when any case failed. */
#include "reader_opds_browser.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/stat.h>
#endif

static FILE *g_out;
static int g_failures;
static const char *g_plain;
static const char *g_secure;
static const char *g_other;
static const char *g_staging;
static reader_opds_browser *g_busy_browser;
static const char *g_busy_url;
static int g_busy_seen;
static int g_busy_status;

static void json_escape(FILE *f, const char *text) {
  for (; text && *text; text++) {
    unsigned char ch = (unsigned char)*text;
    if (ch == '"' || ch == '\\') fprintf(f, "\\%c", ch);
    else if (ch == '\n') fputs("\\n", f);
    else if (ch == '\r') fputs("\\r", f);
    else if (ch == '\t') fputs("\\t", f);
    else if (ch < 0x20) fprintf(f, "\\u%04x", ch);
    else fputc((int)ch, f);
  }
}

static void record(const char *id, int ok, const char *fmt, ...) {
  va_list ap;
  char detail[1200];
  va_start(ap, fmt);
  vsnprintf(detail, sizeof detail, fmt, ap);
  va_end(ap);
  fprintf(g_out, "{\"id\":\"%s\",\"ok\":%s,\"detail\":\"", id, ok ? "true" : "false");
  json_escape(g_out, detail);
  fputs("\"}\n", g_out);
  fflush(g_out);
  if (!ok) g_failures++;
}

static unsigned long long now_ms(void) {
#ifdef _WIN32
  return (unsigned long long)GetTickCount64();
#else
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (unsigned long long)ts.tv_sec * 1000ull + (unsigned long long)(ts.tv_nsec / 1000000);
#endif
}

typedef struct {
  int trip_ms;
  unsigned long long start;
  int armed;
} canceller;

static int cancel_after(void *ctx) {
  canceller *c = (canceller *)ctx;
  if (!c->armed) return 0;
  return (now_ms() - c->start) >= (unsigned long long)c->trip_ms;
}

static void arm(canceller *c, int trip_ms) {
  c->trip_ms = trip_ms;
  c->start = now_ms();
  c->armed = 1;
}

/* Reentrant control: asks the same browser for another page while a call is active. */
static int busy_probe(void *ctx) {
  (void)ctx;
  if (!g_busy_seen) {
    reader_opds_page *page = NULL;
    opds_error error;
    g_busy_seen = 1;
    g_busy_status = (int)reader_opds_open(g_busy_browser, g_busy_url, NULL, &page, &error);
    reader_opds_page_free(page);
  }
  return 0;
}

static const char *join(const char *base, const char *path, char *buf, size_t cap) {
  snprintf(buf, cap, "%s%s", base, path);
  return buf;
}

static reader_opds_browser *make_browser(const char *staging, const char *credential_origin,
                                         const char *authorization, const opds_limits *limits) {
  reader_opds_config config;
  opds_error error;
  reader_opds_config_defaults(&config);
  if (staging) config.staging_dir = staging;
  if (limits) config.limits = *limits;
  config.credential_origin = credential_origin;
  config.authorization = authorization;
  {
    reader_opds_browser *browser = reader_opds_browser_create(&config, &error);
    if (!browser) fprintf(stderr, "create failed: %s\n", error.message);
    return browser;
  }
}

static int find_link(const reader_opds_page *page, int acquire, size_t *entry, size_t *link) {
  size_t i, k;
  for (i = 0; i < page->entry_count; i++)
    for (k = 0; k < page->entries[i].link_count; k++)
      if (page->entries[i].links[k].acquire == acquire) {
        *entry = i;
        *link = k;
        return 1;
      }
  return 0;
}

/* opds-<24 lower-case hex>.(epub|pdf|cbz) */
static int staged_name_ok(const char *path) {
  const char *name = path, *p;
  size_t n, i;
  for (p = path; *p; p++)
    if (*p == '/' || *p == '\\') name = p + 1;
  n = strlen(name);
  if (n < 34 || strncmp(name, "opds-", 5)) return 0;
  for (i = 5; i < 29; i++)
    if (!((name[i] >= '0' && name[i] <= '9') || (name[i] >= 'a' && name[i] <= 'f'))) return 0;
  return !strcmp(name + 29, ".epub") || !strcmp(name + 29, ".pdf") || !strcmp(name + 29, ".cbz");
}

int main(int argc, char **argv) {
  opds_limits limits;
  reader_opds_browser *browser;
  reader_opds_page *catalog = NULL, *page2 = NULL, *page3 = NULL;
  opds_error error;
  reader_opds_status status;
  size_t i, k, entry = 0, link = 0;
  char buffer[1200];

  if (argc < 6) {
    fprintf(stderr, "usage: %s <staging-dir> <plain-base> <tls-base> <other-base> <out-jsonl>\n", argv[0]);
    return 2;
  }
  g_staging = argv[1];
  g_plain = argv[2];
  g_secure = argv[3];
  g_other = argv[4];
  g_out = fopen(argv[5], "wb");
  if (!g_out) return 2;
  memset(&error, 0, sizeof error);
  opds_limits_defaults(&limits);

  browser = make_browser(g_staging, NULL, NULL, NULL);
  record("browser_create", browser != NULL, "%s", browser ? "created" : error.message);
  if (!browser) {
    fclose(g_out);
    return 1;
  }
  g_busy_url = join(g_plain, "/opds1/page2.xml", buffer, sizeof buffer);

  /* ---- OPDS 1 snapshot ---- */
  status = reader_opds_open(browser, join(g_plain, "/opds1/catalog.xml", buffer, sizeof buffer), NULL, &catalog, &error);
  record("opds1_open", status == READER_OPDS_OK && catalog != NULL, "%s %s", reader_opds_status_name(status),
         error.message);
  if (catalog) {
    int unicode = strstr(catalog->entries[0].title, "\346\227\245\346\234\254\350\252\236") != NULL &&
                  strstr(catalog->entries[0].title, "\303\234n\303\257code") != NULL;
    int author = catalog->entries[0].author_count == 1 &&
                 strstr(catalog->entries[0].authors[0], "L\303\270vstr\303\266m") != NULL;
    record("opds1_display_fields",
           catalog->version == 1 && catalog->entry_count == 3 && unicode && author &&
               catalog->entries[0].language[0] != 0 && catalog->entries[0].identifier[0] != 0 &&
               catalog->entries[0].publisher[0] != 0 && catalog->entries[0].summary[0] != 0,
           "version=%d entries=%zu unicode=%d author=%d lang=%s", catalog->version, catalog->entry_count, unicode,
           author, catalog->entries[0].language);
    record("opds1_identity", strlen(catalog->identity) == 64 && catalog->page_number == 1, "identity=%.12s page=%u",
           catalog->identity, catalog->page_number);
    record("opds1_cursor_format",
           catalog->has_next && strlen(catalog->cursor) == 35 && !strncmp(catalog->cursor, "c1-", 3),
           "cursor=%s has_next=%d", catalog->cursor, catalog->has_next);
    {
      const reader_opds_link *first = &catalog->entries[0].links[0];
      record("opds1_snapshot_links",
             first->raw_href[0] != 0 && strstr(first->href, "/books/ok.epub") != NULL &&
                 strstr(first->raw_href, "/books/ok.epub") != NULL,
             "raw=%.40s href=%.60s", first->raw_href, first->href);
    }
    {
      int indirect = 0, protected_link = 0, priced = 0, sample = 0;
      for (k = 0; k < catalog->entries[0].link_count; k++) {
        const reader_opds_link *l = &catalog->entries[0].links[k];
        if (l->acquire == READER_OPDS_ACQ_INDIRECT && l->indirect_type[0]) indirect = 1;
        if (l->acquire == READER_OPDS_ACQ_PROTECTED) protected_link = 1;
        if (l->acquire == READER_OPDS_ACQ_PRICED) priced = 1;
        if (l->acquire == READER_OPDS_ACQ_SAMPLE) sample = 1;
      }
      record("opds1_link_classes", indirect && protected_link && priced && sample,
             "indirect=%d protected=%d priced=%d sample=%d", indirect, protected_link, priced, sample);
    }
    record("opds1_free_link",
           catalog->entries[0].free_link >= 0 && catalog->entries[0].restricted_links >= 5 &&
               catalog->entries[0].is_publication,
           "free=%d restricted=%zu publication=%d", catalog->entries[0].free_link,
           catalog->entries[0].restricted_links, catalog->entries[0].is_publication);
    record("opds1_facets",
           catalog->facet_count == 1 && catalog->facets[0].choice_count == 3 &&
               catalog->facets[0].choices[1].active && catalog->facets[0].choices[0].number_of_items == 2 &&
               catalog->facets[0].choices[0].href[0] != 0,
           "groups=%zu choices=%zu active=%d count=%lld", catalog->facet_count,
           catalog->facet_count ? catalog->facets[0].choice_count : 0,
           catalog->facet_count ? catalog->facets[0].choices[1].active : -1,
           catalog->facet_count ? (long long)catalog->facets[0].choices[0].number_of_items : -1LL);
    record("opds1_search_advertised", catalog->has_search == 1, "has_search=%d", catalog->has_search);
    record("opds1_feed_links", catalog->link_count >= 4, "feed_links=%zu", catalog->link_count);
  }

  /* ---- pagination and cursors ---- */
  if (catalog) {
    status = reader_opds_next(browser, catalog, NULL, &page2, &error);
    record("opds1_next_page",
           status == READER_OPDS_OK && page2 && page2->page_number == 2 && !strcmp(page2->identity, catalog->identity),
           "%s page=%u", reader_opds_status_name(status), page2 ? page2->page_number : 0);
  }
  if (page2) {
    status = reader_opds_next(browser, page2, NULL, &page3, &error);
    record("opds1_next_third_page", status == READER_OPDS_OK && page3 && page3->page_number == 3, "%s page=%u",
           reader_opds_status_name(status), page3 ? page3->page_number : 0);
  }
  if (page3) {
    record("opds1_loop_refused", page3->has_next == 0 && page3->next_refused == 1, "has_next=%d refused=%d",
           page3->has_next, page3->next_refused);
  }
  if (catalog && page2) {
    reader_opds_page *repeat = NULL;
    opds_error stale;
    status = reader_opds_resume(browser, catalog->identity, catalog->cursor, NULL, &repeat, &stale);
    record("cursor_stale_after_advance", status == READER_OPDS_CURSOR, "%s %s", reader_opds_status_name(status),
           stale.message);
    reader_opds_page_free(repeat);
    repeat = NULL;
    status = reader_opds_resume(browser, page2->identity, "c1-00000000000000000000000000000000", NULL, &repeat, &stale);
    record("cursor_wrong_value", status == READER_OPDS_CURSOR, "%s", reader_opds_status_name(status));
    reader_opds_page_free(repeat);
  }
  {
    reader_opds_page *chain = NULL;
    opds_error chain_error;
    status = reader_opds_open(browser, join(g_plain, "/opds1/chain/1.xml", buffer, sizeof buffer), NULL, &chain,
                              &chain_error);
    if (status == READER_OPDS_OK && chain && catalog) {
      reader_opds_page *repeat = NULL;
      opds_error mismatched;
      status = reader_opds_resume(browser, chain->identity, catalog->cursor, NULL, &repeat, &mismatched);
      record("cursor_other_feed_refused", status == READER_OPDS_CURSOR, "%s %s", reader_opds_status_name(status),
             mismatched.message);
      reader_opds_page_free(repeat);
    } else {
      record("cursor_other_feed_refused", 0, "chain open failed: %s", reader_opds_status_name(status));
    }
    reader_opds_page_free(chain);
  }

  /* ---- search ---- */
  if (catalog) {
    reader_opds_page *found = NULL;
    status = reader_opds_search(browser, catalog, "\346\227\245\346\234\254\350\252\236 book", NULL, &found, &error);
    record("search_opensearch_utf8",
           status == READER_OPDS_OK && found && strstr(found->title, "\346\227\245\346\234\254\350\252\236") != NULL &&
               strcmp(found->identity, catalog->identity) != 0,
           "%s title=%.60s", reader_opds_status_name(status), found ? found->title : "");
    reader_opds_page_free(found);
    found = NULL;
    status = reader_opds_search(browser, catalog, "line\nbreak", NULL, &found, &error);
    record("search_terms_refused", status == READER_OPDS_ARGUMENT, "%s", reader_opds_status_name(status));
    reader_opds_page_free(found);
  }

  /* ---- OPDS 2 ---- */
  {
    reader_opds_page *json = NULL;
    status = reader_opds_open(browser, join(g_plain, "/opds2/catalog.json", buffer, sizeof buffer), NULL, &json, &error);
    record("opds2_snapshot",
           status == READER_OPDS_OK && json && json->version == 2 && json->facet_count == 1 &&
               json->entry_count >= 3,
           "%s version=%d entries=%zu facets=%zu", reader_opds_status_name(status), json ? json->version : 0,
           json ? json->entry_count : 0, json ? json->facet_count : 0);
    if (json) {
      int navigation = 0;
      for (i = 0; i < json->entry_count; i++)
        for (k = 0; k < json->entries[i].link_count; k++)
          if (json->entries[i].links[k].navigation) navigation = 1;
      record("opds2_navigation", navigation == 1, "navigation=%d", navigation);
      record("opds2_facet_counts",
             json->facet_count == 1 && json->facets[0].choice_count == 2 &&
                 json->facets[0].choices[0].number_of_items == 2 && json->facets[0].choices[1].active,
             "groups=%zu choices=%zu count=%lld active=%d", json->facet_count,
             json->facet_count ? json->facets[0].choice_count : 0,
             json->facet_count ? (long long)json->facets[0].choices[0].number_of_items : -1LL,
             json->facet_count ? json->facets[0].choices[1].active : -1);
      {
        reader_opds_page *found = NULL;
        opds_error search_error;
        reader_opds_status st = reader_opds_search(browser, json, "term", NULL, &found, &search_error);
        record("opds2_search_template", st == READER_OPDS_OK && found && strstr(found->title, "term") != NULL,
               "%s title=%.60s", reader_opds_status_name(st), found ? found->title : "");
        reader_opds_page_free(found);
      }
    }
    reader_opds_page_free(json);
  }

  /* ---- acquisition ---- */
  if (catalog && find_link(catalog, READER_OPDS_ACQ_FREE, &entry, &link)) {
    reader_opds_acquired staged;
    status = reader_opds_acquire(browser, catalog, entry, link, NULL, NULL, &staged, &error);
    record("acquire_free_epub",
           status == READER_OPDS_OK && staged.bytes > 0 && strlen(staged.sha256) == 64 &&
               !strcmp(staged.media_type, "application/epub+zip") && !staged.already_present &&
               staged_name_ok(staged.path),
           "%s bytes=%llu sha=%.12s path=%s", reader_opds_status_name(status),
           (unsigned long long)staged.bytes, staged.sha256, staged.path);
    if (status == READER_OPDS_OK) {
      reader_opds_acquired again;
      opds_error duplicate;
      reader_opds_status st2 = reader_opds_acquire(browser, catalog, entry, link, NULL, NULL, &again, &duplicate);
      record("acquire_duplicate",
             st2 == READER_OPDS_OK && again.already_present == 1 && !strcmp(again.sha256, staged.sha256) &&
                 !strcmp(again.path, staged.path),
             "%s already=%d", reader_opds_status_name(st2), again.already_present);
      {
        reader_opds_acquired receipt = again;
        opds_error denied;
        int setup_ok, restored;
        reader_opds_status removal;
#ifdef _WIN32
        HANDLE held = CreateFileA(again.path, GENERIC_READ, 0, NULL, OPEN_EXISTING,
                                  FILE_ATTRIBUTE_NORMAL, NULL);
        setup_ok = held != INVALID_HANDLE_VALUE;
        removal = reader_opds_staged_discard(&again, &denied);
        restored = setup_ok ? CloseHandle(held) != 0 : 0;
#else
        struct stat mode;
        setup_ok = stat(g_staging, &mode) == 0 && chmod(g_staging, 0) == 0;
        removal = reader_opds_staged_discard(&again, &denied);
        restored = setup_ok && chmod(g_staging, mode.st_mode & 0777) == 0;
#endif
        record("discard_denied_preserves_receipt", setup_ok && restored &&
               removal == READER_OPDS_IO && !memcmp(&again, &receipt, sizeof again),
               "setup=%d restored=%d status=%s", setup_ok, restored,
               reader_opds_status_name(removal));
      }
      {
        opds_error discarded;
        int first = reader_opds_staged_discard(&again, &discarded) == READER_OPDS_OK;
        int second = reader_opds_staged_discard(&again, &discarded) == READER_OPDS_OK;
        record("staged_discard", first && second, "first=%d second=%d", first, second);
      }
      {
        reader_opds_acquired forged;
        opds_error refused;
        memset(&forged, 0, sizeof forged);
        forged.struct_size = sizeof forged;
        snprintf(forged.path, sizeof forged.path, "%s/not-opds-file.epub", g_staging);
        record("discard_foreign_name", reader_opds_staged_discard(&forged, &refused) == READER_OPDS_ARGUMENT, "%s",
               reader_opds_status_name(reader_opds_staged_discard(&forged, &refused)));
      }
    }
  } else {
    record("acquire_free_epub", 0, "no free acquisition link in the catalogue");
  }
  if (catalog) {
    static const struct {
      const char *id;
      int kind;
      int expected;
    } refusals[] = {{"acquire_buy_refused", READER_OPDS_ACQ_BUY, READER_OPDS_NEEDS_HOST},
                    {"acquire_borrow_refused", READER_OPDS_ACQ_BORROW, READER_OPDS_NEEDS_HOST},
                    {"acquire_protected_refused", READER_OPDS_ACQ_PROTECTED, READER_OPDS_NEEDS_HOST},
                    {"acquire_priced_refused", READER_OPDS_ACQ_PRICED, READER_OPDS_NEEDS_HOST},
                    {"acquire_indirect_refused", READER_OPDS_ACQ_INDIRECT, READER_OPDS_NEEDS_HOST},
                    {"acquire_sample_refused", READER_OPDS_ACQ_SAMPLE, READER_OPDS_UNSUPPORTED}};
    for (i = 0; i < sizeof refusals / sizeof refusals[0]; i++) {
      reader_opds_acquired staged;
      opds_error refused;
      if (!find_link(catalog, refusals[i].kind, &entry, &link)) {
        record(refusals[i].id, 0, "fixture lacks that link class");
        continue;
      }
      status = reader_opds_acquire(browser, catalog, entry, link, NULL, NULL, &staged, &refused);
      record(refusals[i].id, status == (reader_opds_status)refusals[i].expected, "%s expected %s",
             reader_opds_status_name(status), reader_opds_status_name(refusals[i].expected));
    }
  }
  {
    static const struct {
      const char *id;
      const char *feed;
      int expected;
    } book_cases[] = {{"acquire_fake_extension_mismatch", "/opds1/fake.xml", READER_OPDS_MISMATCH},
                      {"acquire_broken_published", "/opds1/broken.xml", READER_OPDS_OK}};
    for (i = 0; i < sizeof book_cases / sizeof book_cases[0]; i++) {
      reader_opds_page *feed = NULL;
      opds_error feed_error;
      status = reader_opds_open(browser, join(g_plain, book_cases[i].feed, buffer, sizeof buffer), NULL, &feed,
                                &feed_error);
      if (status == READER_OPDS_OK && feed && find_link(feed, READER_OPDS_ACQ_FREE, &entry, &link)) {
        reader_opds_acquired staged;
        opds_error acquire_error;
        status = reader_opds_acquire(browser, feed, entry, link, NULL, NULL, &staged, &acquire_error);
        record(book_cases[i].id, status == (reader_opds_status)book_cases[i].expected, "%s %s",
               reader_opds_status_name(status), acquire_error.message);
      } else {
        record(book_cases[i].id, 0, "feed open failed: %s", reader_opds_status_name(status));
      }
      reader_opds_page_free(feed);
    }
  }

  /* ---- cancellation, reentry, limits ---- */
  {
    reader_opds_page *feed = NULL;
    opds_error stall_error;
    status = reader_opds_open(browser, join(g_plain, "/opds1/stall.xml", buffer, sizeof buffer), NULL, &feed,
                              &stall_error);
    if (status == READER_OPDS_OK && feed && find_link(feed, READER_OPDS_ACQ_FREE, &entry, &link)) {
      reader_opds_acquired staged;
      opds_error cancel_error;
      canceller c;
      opds_control control;
      arm(&c, 400);
      control.cancelled = cancel_after;
      control.context = &c;
      status = reader_opds_acquire(browser, feed, entry, link, NULL, &control, &staged, &cancel_error);
      record("acquire_cancel", status == READER_OPDS_CANCELLED, "%s %s", reader_opds_status_name(status),
             cancel_error.message);
    } else {
      record("acquire_cancel", 0, "stall feed open failed: %s", reader_opds_status_name(status));
    }
    reader_opds_page_free(feed);
    feed = NULL;
    status = reader_opds_open(browser, join(g_plain, "/opds1/catalog.xml", buffer, sizeof buffer), NULL, &feed, &error);
    record("browser_usable_after_cancel", status == READER_OPDS_OK && feed && feed->entry_count == 3, "%s entries=%zu",
           reader_opds_status_name(status), feed ? feed->entry_count : 0);
    reader_opds_page_free(feed);
  }
  {
    reader_opds_page *feed = NULL;
    opds_error busy_error;
    opds_control control;
    g_busy_browser = browser;
    g_busy_seen = 0;
    g_busy_status = -1;
    control.cancelled = busy_probe;
    control.context = NULL;
    status = reader_opds_open(browser, g_busy_url, &control, &feed, &busy_error);
    record("busy_reentry", status == READER_OPDS_OK && g_busy_seen == 1 && g_busy_status == READER_OPDS_BUSY,
           "%s inner=%s", reader_opds_status_name(status), reader_opds_status_name(g_busy_status));
    reader_opds_page_free(feed);
  }
  {
    opds_limits limited_limits;
    reader_opds_browser *limited;
    reader_opds_page *chain = NULL;
    opds_error chain_error;
    size_t pages = 1;
    opds_limits_defaults(&limited_limits);
    limited_limits.max_pages = 3;
    limited = make_browser(g_staging, NULL, NULL, &limited_limits);
    status = reader_opds_open(limited, join(g_plain, "/opds1/chain/1.xml", buffer, sizeof buffer), NULL, &chain,
                              &chain_error);
    while (status == READER_OPDS_OK && chain && chain->has_next && pages < 12) {
      reader_opds_page *following = NULL;
      status = reader_opds_next(limited, chain, NULL, &following, &chain_error);
      reader_opds_page_free(chain);
      chain = following;
      if (status != READER_OPDS_OK) break;
      pages++;
    }
    record("limits_max_pages", status == READER_OPDS_LIMIT && pages == 3, "%s pages=%zu",
           reader_opds_status_name(status), pages);
    reader_opds_page_free(chain);
    reader_opds_browser_free(limited);
    limited_limits.max_entries = 1;
    limited = make_browser(g_staging, NULL, NULL, &limited_limits);
    chain = NULL;
    status = reader_opds_open(limited, join(g_plain, "/opds1/catalog.xml", buffer, sizeof buffer), NULL, &chain,
                              &chain_error);
    record("limits_lowered_entries", status == READER_OPDS_LIMIT, "%s", reader_opds_status_name(status));
    reader_opds_page_free(chain);
    reader_opds_browser_free(limited);
  }
  {
    reader_opds_browser *bare = make_browser(NULL, NULL, NULL, NULL);
    reader_opds_page *feed = NULL;
    opds_error bare_error;
    status = reader_opds_open(bare, join(g_plain, "/opds1/catalog.xml", buffer, sizeof buffer), NULL, &feed, &bare_error);
    if (status == READER_OPDS_OK && find_link(feed, READER_OPDS_ACQ_FREE, &entry, &link)) {
      reader_opds_acquired staged;
      status = reader_opds_acquire(bare, feed, entry, link, NULL, NULL, &staged, &bare_error);
    }
    record("staging_required", status == READER_OPDS_ARGUMENT, "%s", reader_opds_status_name(status));
    reader_opds_page_free(feed);
    reader_opds_browser_free(bare);
  }

  /* ---- credentials and origins ---- */
  {
    reader_opds_browser *authed = make_browser(g_staging, g_other, "Bearer test-token", NULL);
    reader_opds_page *feed = NULL;
    unsigned requests = 0, redirects = 0, dropped = 0;
    status = reader_opds_open(authed, join(g_other, "/auth/catalog.xml", buffer, sizeof buffer), NULL, &feed, &error);
    record("auth_origin_accepted", status == READER_OPDS_OK && feed && feed->entry_count >= 1, "%s",
           reader_opds_status_name(status));
    reader_opds_page_free(feed);
    feed = NULL;
    status = reader_opds_open(authed, join(g_other, "/redirect/to-plain", buffer, sizeof buffer), NULL, &feed, &error);
    reader_opds_browser_stats(authed, &requests, &redirects, &dropped);
    record("cross_origin_redirect", status == READER_OPDS_OK && feed && feed->entry_count == 3 && redirects == 1,
           "%s redirects=%u", reader_opds_status_name(status), redirects);
    record("cross_origin_credentials_dropped", dropped >= 1, "dropped=%u requests=%u", dropped, requests);
    reader_opds_page_free(feed);
    reader_opds_browser_free(authed);
  }
  {
    reader_opds_browser *anonymous = make_browser(g_staging, NULL, NULL, NULL);
    reader_opds_page *feed = NULL;
    status = reader_opds_open(anonymous, join(g_other, "/auth/catalog.xml", buffer, sizeof buffer), NULL, &feed, &error);
    record("auth_required", status == READER_OPDS_AUTH_REQUIRED, "%s", reader_opds_status_name(status));
    reader_opds_page_free(feed);
    reader_opds_browser_free(anonymous);
  }

  /* ---- TLS ---- */
  {
    reader_opds_browser *secure = make_browser(g_staging, NULL, NULL, NULL);
    reader_opds_page *feed = NULL;
    if (!reader_opds_tls_available()) {
      record("tls_available", 0, "this build carries no TLS transport");
    } else {
      record("tls_available", 1, "https transport built");
      status = reader_opds_open(secure, join(g_secure, "/opds1/catalog.xml", buffer, sizeof buffer), NULL, &feed, &error);
      record("tls_open", status == READER_OPDS_OK && feed && feed->entry_count == 3, "%s %s",
             reader_opds_status_name(status), error.message);
      if (status == READER_OPDS_OK && feed && find_link(feed, READER_OPDS_ACQ_FREE, &entry, &link)) {
        reader_opds_acquired staged;
        status = reader_opds_acquire(secure, feed, entry, link, NULL, NULL, &staged, &error);
        record("tls_acquire", status == READER_OPDS_OK && staged.bytes > 0, "%s", reader_opds_status_name(status));
        if (status == READER_OPDS_OK) reader_opds_staged_discard(&staged, NULL);
      } else {
        record("tls_acquire", 0, "no free link over TLS: %s", reader_opds_status_name(status));
      }
    }
    reader_opds_page_free(feed);
    reader_opds_browser_free(secure);
  }

  reader_opds_page_free(catalog);
  reader_opds_page_free(page2);
  reader_opds_page_free(page3);
  reader_opds_browser_free(browser);
  fclose(g_out);
  return g_failures ? 1 : 0;
}
