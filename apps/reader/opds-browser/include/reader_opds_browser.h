/* SPDX-License-Identifier: MIT */
/* Reader-side OPDS browser: paged catalogue/search/acquire adapter over the
   frozen standalone OPDS module (extras/opds, OPDS_MODULE_VERSION 0.2.0).
   It adds immutable snapshots, feed-bound pagination cursors, facet display,
   acquisition policy and a two-phase download -> SDK-owner import split.
   It never parses feeds itself, never pays, never borrows and never handles DRM. */
#ifndef READER_OPDS_BROWSER_H
#define READER_OPDS_BROWSER_H
#include <stddef.h>
#include <stdint.h>
#include "opds.h"

#ifdef __cplusplus
extern "C" {
#endif

#define READER_OPDS_BROWSER_VERSION "0.1.0"
#define READER_OPDS_BROWSER_ABI 1

/* ---- hard limits (new here; the module's own opds_limits are never raised) ----
   READER_OPDS_SNAPSHOT_BYTES   copied display data of one page, all strings included.
   READER_OPDS_SEQUENCES        feed sequences (one open/search plus its pages) kept at once;
                                the least recently used one is evicted and its cursor goes stale.
   READER_OPDS_SEARCH_BYTES     UTF-8 search terms.
   READER_OPDS_URL_BYTES        any URL accepted from the host.
   READER_OPDS_STAGING_BYTES    staging directory path plus file name.
   A page, a cursor and a staged file are bounded by these values; nothing grows
   without a limit. */
#define READER_OPDS_SNAPSHOT_BYTES (16u * 1024u * 1024u)
#define READER_OPDS_SEQUENCES 8u
#define READER_OPDS_SEARCH_BYTES 256u
#define READER_OPDS_URL_BYTES 4096u
#define READER_OPDS_STAGING_BYTES 1024u
#define READER_OPDS_IDENTITY_BYTES 65u /* 64 hex digits + NUL */
#define READER_OPDS_CURSOR_BYTES 36u   /* "c1-" + 32 hex digits + NUL */

/* Status values 0..15 are the module's opds_status values, unchanged. */
typedef enum {
  READER_OPDS_OK = OPDS_OK,
  READER_OPDS_ARGUMENT = OPDS_ARGUMENT,
  READER_OPDS_MEMORY = OPDS_MEMORY,
  READER_OPDS_IO = OPDS_IO,
  READER_OPDS_FORMAT = OPDS_FORMAT,
  READER_OPDS_LIMIT = OPDS_LIMIT,
  READER_OPDS_CANCELLED = OPDS_CANCELLED,
  READER_OPDS_TIMEOUT = OPDS_TIMEOUT,
  READER_OPDS_HTTP = OPDS_HTTP,
  READER_OPDS_AUTH_REQUIRED = OPDS_AUTH_REQUIRED,
  READER_OPDS_UNSUPPORTED = OPDS_UNSUPPORTED,
  READER_OPDS_NEEDS_HOST = OPDS_NEEDS_HOST, /* buy/borrow/subscribe/price/DRM/indirect, or no TLS */
  READER_OPDS_EXISTS = OPDS_EXISTS,
  READER_OPDS_MISMATCH = OPDS_MISMATCH,
  READER_OPDS_UNREADABLE = OPDS_UNREADABLE, /* the structural check rejected the download */
  READER_OPDS_ABORTED = OPDS_ABORTED,
  READER_OPDS_CURSOR = 16, /* cursor unknown, stale, evicted or bound to another feed */
  READER_OPDS_BUSY = 17    /* another call on this browser is still running (reentry/thread) */
} reader_opds_status;
const char *reader_opds_status_name(int status);

/* ---- transport ----
   Dispatches http:// to the module's reference socket transport and https:// to the
   platform TLS transport (WinHTTP on Windows, libcurl with the system trust store
   elsewhere), with host-name and certificate verification, no redirect following,
   no proxy, no cookies and identity encoding only. Credentials are never added
   here: the request's authorization field is the only source, and the module sets
   it for one origin only.
   Built with READER_OPDS_TLS=OFF, https:// returns NEEDS_HOST.
   The returned object is static and thread-safe; each fetch uses only its own state. */
const opds_transport *reader_opds_default_transport(void);
/* 1 when this build carries a TLS transport. */
int reader_opds_tls_available(void);

/* ---- snapshot (immutable, self-contained) ---- */
typedef enum {
  READER_OPDS_ACQ_NOT = 0,   /* not an acquisition link */
  READER_OPDS_ACQ_FREE,      /* open access / unpriced generic acquisition: may be downloaded */
  READER_OPDS_ACQ_SAMPLE,    /* a sample is not the publication: refused */
  READER_OPDS_ACQ_BORROW,
  READER_OPDS_ACQ_BUY,
  READER_OPDS_ACQ_SUBSCRIBE,
  READER_OPDS_ACQ_PRICED,    /* any link that carries a price */
  READER_OPDS_ACQ_PROTECTED, /* DRM / license documents (LCP, Adept, ...) */
  READER_OPDS_ACQ_INDIRECT   /* needs another hop or a templated href */
} reader_opds_acquire_kind;
const char *reader_opds_acquire_name(int kind);

/* All strings are UTF-8, never NULL (empty when absent) and owned by the page.
   Every display field of the module's opds_link survives the copy: rel, resolved
   href, raw_href, type, title, indirect_type, kind, acquisition class and flags.
   Classification order is protected, buy, borrow, subscribe, sample, priced,
   indirect; everything else is FREE. */
typedef struct {
  const char *rel, *href, *raw_href, *type, *title;
  const char *indirect_type; /* first nested indirect acquisition type, or empty */
  int kind;       /* opds_rel_kind of the module */
  int acquire;    /* reader_opds_acquire_kind */
  int navigation; /* 1: leads to another OPDS feed */
  unsigned flags; /* OPDS_LINK_* of the module */
} reader_opds_link;

typedef struct {
  const char *id, *title, *updated, *summary, *identifier, *language, *publisher, *group;
  const char *const *authors;
  size_t author_count;
  const reader_opds_link *links;
  size_t link_count;
  int is_publication;
  /* Index into links of the first link that may be downloaded, or -1. A paid, borrowed,
     DRM-protected, sample or indirect link never qualifies. */
  int free_link;
  size_t restricted_links; /* acquisition links that are not FREE */
} reader_opds_entry;

typedef struct {
  const char *title; /* empty for ungrouped OPDS 1 facets */
  const struct reader_opds_facet_choice *choices;
  size_t choice_count;
} reader_opds_facet;
typedef struct reader_opds_facet_choice {
  const char *rel, *title, *href, *type;
  unsigned flags;          /* OPDS_LINK_* of the module, as copied */
  int64_t number_of_items; /* -1 when not supplied */
  int active;
} reader_opds_facet_choice;

typedef struct reader_opds_page {
  int version;        /* 1 = Atom, 2 = JSON */
  const char *id, *title, *updated, *base_url;
  int64_t total_results, items_per_page, start_index, current_page; /* -1 unknown */
  const reader_opds_entry *entries;
  size_t entry_count;
  const reader_opds_link *links; /* feed-level links */
  size_t link_count;
  const reader_opds_facet *facets;
  size_t facet_count;
  /* Opaque feed-sequence identity: the first page's request URL (or the resolved search URL)
     hashed with SHA-256, lower-case hex. Every page of one sequence carries the same value. */
  char identity[READER_OPDS_IDENTITY_BYTES];
  unsigned page_number;   /* 1-based within the sequence */
  int has_search;         /* a search link was advertised */
  int has_next;           /* cursor is valid */
  char cursor[READER_OPDS_CURSOR_BYTES]; /* empty when has_next is 0 */
  int next_refused;       /* a rel=next existed but left the feed's origin or looped: no cursor */
  int declared_type_mismatch;
  void *storage_;         /* private */
} reader_opds_page;
/* Releases the page. It does not depend on the browser that produced it. NULL is allowed. */
void reader_opds_page_free(reader_opds_page *page);

/* ---- browser ---- */
typedef struct reader_opds_browser reader_opds_browser;
typedef struct {
  size_t struct_size;
  /* Per-field limits of the OPDS module. 0 selects the module default and a larger
     value is clamped to it, so a caller can only lower a budget. max_pages bounds the
     pages of one sequence. */
  opds_limits limits;
  const opds_transport *transport; /* NULL = reader_opds_default_transport() */
  /* Credentials are copied, bound to one origin (scheme://host:port) and only attached to
     requests for exactly that origin, including redirects. Never logged. */
  const char *credential_origin;
  const char *authorization;
  /* Existing directory (UTF-8, no trailing separator needed) that receives downloads.
     Validated at create time. Required for acquire only. */
  const char *staging_dir;
  /* The frozen module's request format fixes the User-Agent; a host value is not
     forwarded, so the browser exposes no such field. */
} reader_opds_config;
void reader_opds_config_defaults(reader_opds_config *config);

/* Network phase. A browser never touches the SDK, creates no thread and keeps no global
   state. It is owned by one caller at a time: a call made while another call (including one
   from inside the control callback) is active returns READER_OPDS_BUSY without side effects.
   Different browsers are independent. Calls use the transport's connection/read timeout
   budgets; these are not a hard whole-call deadline for slowly streaming responses.
   `control` (borrowed for the call only, NULL allowed) cancels it. Cancellation and
   errors leave the sequence's cursor valid so the same call can be repeated: no page is
   recorded as visited unless the call returns it. */
reader_opds_browser *reader_opds_browser_create(const reader_opds_config *config, opds_error *error);
void reader_opds_browser_free(reader_opds_browser *browser); /* NULL allowed; not during a call */

/* Request counters of the internal OPDS client since creation. credentials_dropped counts
   requests whose origin did not match the credential origin; it is the observable proof of
   cross-origin credential isolation. NULL outputs are ignored. */
void reader_opds_browser_stats(const reader_opds_browser *browser, unsigned *requests,
                               unsigned *redirects, unsigned *credentials_dropped);

/* Starts a new sequence at url (http or https) and snapshots its first page. The result
   is owned by the caller (reader_opds_page_free). On failure *page is NULL. */
reader_opds_status reader_opds_open(reader_opds_browser *browser, const char *url,
                                    const opds_control *control, reader_opds_page **page,
                                    opds_error *error);
/* Resolves the search link advertised by `from` (OpenSearch description or URI template) for
   `terms` (valid UTF-8, 1..READER_OPDS_SEARCH_BYTES bytes, no control characters) and starts
   a new sequence whose identity covers the resolved URL, hence the terms. */
reader_opds_status reader_opds_search(reader_opds_browser *browser, const reader_opds_page *from,
                                      const char *terms, const opds_control *control,
                                      reader_opds_page **page, opds_error *error);
/* Fetches the page behind `cursor`. `identity` must be the identity of the sequence the cursor
   was issued for, else READER_OPDS_CURSOR. A cursor is valid until the next successful page of
   its sequence replaces it, or its sequence is evicted. Pages beyond limits.max_pages, a page
   already seen in the sequence, and a next link to another origin are refused/not offered. */
reader_opds_status reader_opds_resume(reader_opds_browser *browser, const char *identity,
                                      const char *cursor, const opds_control *control,
                                      reader_opds_page **page, opds_error *error);
/* reader_opds_resume with the identity and cursor of `page`; needs has_next. */
reader_opds_status reader_opds_next(reader_opds_browser *browser, const reader_opds_page *page,
                                    const opds_control *control, reader_opds_page **out,
                                    opds_error *error);
/* Starts a new sequence at a navigation link of a page (subsection, start, up or any link the
   module typed as an OPDS document). A facet choice is not a reader_opds_link: open it with
   reader_opds_open(browser, choice.href, ...). */
reader_opds_status reader_opds_follow(reader_opds_browser *browser, const reader_opds_link *link,
                                      const opds_control *control, reader_opds_page **page,
                                      opds_error *error);

/* ---- acquisition ---- */
typedef struct {
  size_t struct_size;
  int replace_existing;  /* default: an existing file with other content gives EXISTS */
  uint64_t max_bytes;    /* 0 = module limit; may only lower it */
} reader_opds_acquire_options;
typedef struct {
  size_t struct_size;
  char path[READER_OPDS_STAGING_BYTES]; /* UTF-8 staged file */
  char media_type[96];                  /* application/epub+zip, application/pdf, application/vnd.comicbook+zip */
  char sha256[65];
  char sniffed_type[48];
  uint64_t bytes;
  int already_present;     /* identical bytes already staged under the same name */
  int header_type_mismatch;
} reader_opds_acquired;
/* Downloads entries[entry].links[link] of `page` to the staging directory.
   Only READER_OPDS_ACQ_FREE links of importable types (EPUB, PDF, CBZ) are fetched; buy, borrow,
   subscribe, priced, DRM and indirect links return NEEDS_HOST and a sample returns UNSUPPORTED,
   all before any request. The file name is "opds-" plus 24 hex digits of the link's identity
   plus an extension chosen from the declared media type, never from the URL or the title. The
   body goes to a temporary file next to it; declared type vs content signature (MISMATCH), a
   structural check of the container (UNREADABLE) and the size budget run before the single
   atomic publication. Cancellation is honoured while receiving and before publication; after
   publication the result is returned. No SDK call is made; a published file is still untrusted
   until reader_opds_import_staged accepted it. */
reader_opds_status reader_opds_acquire(reader_opds_browser *browser, const reader_opds_page *page,
                                       size_t entry, size_t link,
                                       const reader_opds_acquire_options *options,
                                       const opds_control *control, reader_opds_acquired *out,
                                       opds_error *error);
/* Removes a file produced by acquire. Refuses any other name. Missing files are fine. */
reader_opds_status reader_opds_staged_discard(const reader_opds_acquired *staged, opds_error *error);

#ifdef __cplusplus
}
#endif
#endif
