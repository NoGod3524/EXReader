/* SPDX-License-Identifier: MIT */
/* WP15 OPDS 1.x (Atom) / OPDS 2 (JSON) standalone client.
   Independent of the EXReader SDK: networking, credentials and the download
   location belong to the host. See docs/WP15-OPDS.md for the support table. */
#ifndef OPDS_H
#define OPDS_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define OPDS_MODULE_VERSION "0.2.0"

typedef enum {
  OPDS_OK = 0,
  OPDS_ARGUMENT,
  OPDS_MEMORY,
  OPDS_IO,
  OPDS_FORMAT,        /* feed/XML/JSON is malformed or not an OPDS document */
  OPDS_LIMIT,         /* a configured budget was exceeded */
  OPDS_CANCELLED,
  OPDS_TIMEOUT,
  OPDS_HTTP,          /* non-success HTTP status, see error.http_status */
  OPDS_AUTH_REQUIRED, /* 401: host must supply credentials for the origin */
  OPDS_UNSUPPORTED,   /* recognised but outside the frozen support table */
  OPDS_NEEDS_HOST,    /* https, payment, borrowing or DRM: host capability required */
  OPDS_EXISTS,        /* destination exists with different content */
  OPDS_MISMATCH,      /* content does not match the declared media type */
  OPDS_UNREADABLE,    /* the verifier rejected the downloaded book */
  OPDS_ABORTED        /* internal: a transport callback stopped the transfer */
} opds_status;

typedef struct {
  opds_status code;
  int http_status;               /* 0 when no response was received */
  char message[200];
  char auth_scheme[24];          /* scheme token of a 401 challenge, never a secret */
} opds_error;

const char *opds_status_name(opds_status status);

/* ---- budgets: all independent of the SDK's own budgets ---- */
typedef struct {
  size_t max_feed_bytes;         /* default 4 MiB */
  size_t max_elements;           /* XML elements / JSON values, default 200000 */
  size_t max_entries;            /* default 2000 */
  size_t max_links_per_entry;    /* default 128 */
  size_t max_depth;              /* nesting, default 48 */
  size_t max_redirects;          /* per request, default 5 */
  size_t max_pages;              /* feed fetches per crawl, default 50 */
  uint64_t max_download_bytes;   /* default 256 MiB */
  unsigned timeout_ms;           /* per request, default 10000 */
} opds_limits;
void opds_limits_defaults(opds_limits *limits);

/* ---- model ---- */
typedef enum {
  OPDS_REL_OTHER = 0, OPDS_REL_SELF, OPDS_REL_START, OPDS_REL_UP, OPDS_REL_NEXT,
  OPDS_REL_PREVIOUS, OPDS_REL_FIRST, OPDS_REL_LAST, OPDS_REL_SEARCH, OPDS_REL_SUBSECTION,
  OPDS_REL_ACQUISITION, OPDS_REL_IMAGE, OPDS_REL_THUMBNAIL
} opds_rel_kind;
typedef enum {
  OPDS_ACQ_NONE = 0, OPDS_ACQ_GENERIC, OPDS_ACQ_OPEN_ACCESS, OPDS_ACQ_BORROW,
  OPDS_ACQ_BUY, OPDS_ACQ_SAMPLE, OPDS_ACQ_SUBSCRIBE
} opds_acq_kind;
enum { OPDS_LINK_TEMPLATED = 1, OPDS_LINK_PRICED = 2, OPDS_LINK_INDIRECT = 4, OPDS_LINK_PROTECTED = 8 };

/* All strings are owned by the feed; unknown rel/type values are kept verbatim.
   href is absolute (resolved against xml:base / the document URL) when a base
   was known, otherwise it equals raw_href. */
typedef struct {
  const char *rel;        /* verbatim, multiple relations joined by one space */
  const char *href, *raw_href, *type, *title;
  const char *indirect_type; /* first nested opds:indirectAcquisition type */
  opds_rel_kind kind;
  opds_acq_kind acq;
  unsigned flags;
} opds_link;

typedef struct {
  const char *id, *title, *updated, *summary, *identifier, *language, *publisher, *group;
  const char *const *authors;
  size_t author_count;
  const opds_link *links;
  size_t link_count;
  int is_publication;     /* has at least one acquisition link */
} opds_entry;

struct opds_arena;
typedef struct {
  int version;            /* 1 = Atom, 2 = JSON */
  const char *id, *title, *updated, *base_url;
  int64_t total_results, items_per_page, start_index, current_page; /* -1 unknown */
  const opds_entry *entries;
  size_t entry_count;
  const opds_link *links;
  size_t link_count;
  int declared_type_mismatch; /* Content-Type header disagreed with the body syntax */
  struct opds_arena *arena;
} opds_feed;

void opds_feed_free(opds_feed *feed);
/* Parses an in-memory document. base_url may be NULL. content_type may be NULL. */
opds_status opds_feed_parse(const void *data, size_t size, const char *content_type,
                            const char *base_url, const opds_limits *limits,
                            opds_feed *out, opds_error *error);
/* First link of the given kind, or NULL. */
const opds_link *opds_feed_find(const opds_feed *feed, opds_rel_kind kind);
/* Facet links retain the normal resolved URL and host-controlled transport.
   All pointers are borrowed from the feed and expire with opds_feed_free(). */
typedef struct {
  opds_link link;
  int64_t number_of_items; /* -1 when not supplied. */
  int active;
} opds_facet_choice;
typedef struct {
  const char *title; /* Empty for ungrouped OPDS 1 facets. */
  const opds_facet_choice *choices;
  size_t choice_count;
} opds_facet;
/* OPDS 1 facetGroup/activeFacet/thr:count and OPDS 2 facets/self/numberOfItems.
   Groups and total choices each use max_entries; a group uses the per-entry
   link limit. NULL feed/count are allowed. Existing public model sizes stay fixed. */
const opds_facet *opds_feed_facets(const opds_feed *feed, size_t *count);
/* First acquisition link of an entry whose type equals media_type (NULL = any usable). */
const opds_link *opds_entry_acquisition(const opds_entry *entry, const char *media_type);
/* NEEDS_HOST for borrow/buy/subscribe/priced/protected links, OK otherwise. */
opds_status opds_link_acquirable(const opds_link *link, opds_error *error);

/* ---- URLs ---- */
/* RFC 3986 resolution plus percent-encoding of unsafe bytes (no double encoding). */
opds_status opds_url_resolve(const char *base, const char *ref, char *out, size_t cap);
/* Normalises a media type: lower-case, parameters removed. */
void opds_media_type(const char *value, char *out, size_t cap);
/* Expands OpenSearch {searchTerms}/{startPage?} and RFC 6570 {?query,page}/{query}.
   Required unknown variables are refused with OPDS_UNSUPPORTED. */
opds_status opds_template_expand(const char *tmpl, const char *terms, unsigned page,
                                 char *out, size_t cap, opds_error *error);
/* OpenSearch description: first atom-typed (or OPDS2) Url template. */
opds_status opds_opensearch_template(const void *data, size_t size, const opds_limits *limits,
                                     char *out, size_t cap, opds_error *error);
/* Redacts userinfo and secret-looking query values for logs/reports. */
void opds_redact_url(const char *url, char *out, size_t cap);
void opds_sha256_hex(const void *data, size_t size, char out[65]);

/* ---- transport (host replaceable) ---- */
typedef struct {
  int (*cancelled)(void *context); /* nonzero cancels */
  void *context;
} opds_control;

typedef struct {
  const char *method;        /* "GET" */
  const char *url;
  const char *accept;        /* may be NULL */
  const char *authorization; /* full header value or NULL; only set for the credential origin */
} opds_request;
typedef struct {
  int status;
  const char *location, *content_type, *www_authenticate; /* NULL when absent */
  int64_t content_length;    /* -1 unknown */
} opds_response;
/* head returns nonzero to skip the body; body returns nonzero to stop the transfer. */
typedef int (*opds_head_fn)(void *user, const opds_response *response);
typedef int (*opds_body_fn)(void *user, const void *data, size_t size);
typedef struct opds_transport {
  /* One request, never following redirects. Return OPDS_ABORTED if body stopped. */
  opds_status (*fetch)(void *context, const opds_request *request, unsigned timeout_ms,
                       const opds_control *control, opds_head_fn head, opds_body_fn body,
                       void *user, opds_error *error);
  void *context;
} opds_transport;
/* Reference transport: plain HTTP/1.1 over sockets (Winsock on Windows). https:// is
   refused with OPDS_NEEDS_HOST; supply a host transport for TLS. */
const opds_transport *opds_socket_transport(void);

/* ---- client ---- */
typedef struct {
  const opds_transport *transport; /* NULL = opds_socket_transport() */
  opds_limits limits;
  /* Credentials are bound to one origin (scheme://host:port). They are attached
     only to requests (and redirects) for exactly that origin. The host owns the
     string; the client never logs it. */
  const char *credential_origin;
  const char *authorization;       /* e.g. "Basic ..." or "Bearer ..." */
  const char *user_agent;
  void (*log)(void *context, const char *line); /* redacted request lines only */
  void *log_context;
} opds_config;
typedef struct opds_client opds_client;
void opds_config_defaults(opds_config *config);
opds_client *opds_client_create(const opds_config *config);
void opds_client_free(opds_client *client);
/* Starts a crawl: resets the page counter and visited-URL loop detection. */
void opds_client_begin_crawl(opds_client *client);
/* Request counters of the client since creation (for reports). */
void opds_client_stats(const opds_client *client, unsigned *requests, unsigned *redirects,
                       unsigned *credentials_dropped);

/* Fetches and parses a feed (counts against max_pages and refuses revisits). */
opds_status opds_fetch_feed(opds_client *client, const char *url, const opds_control *control,
                            opds_feed *out, opds_error *error);
/* Fetches the next page (rel=next). *out_url is set to NULL when there is none. */
opds_status opds_fetch_next(opds_client *client, const opds_feed *feed, const opds_control *control,
                            opds_feed *out, int *has_next, opds_error *error);
/* Resolves the feed's search link for terms/page into a feed URL. Fetches an
   OpenSearch description when the link points at one. */
opds_status opds_search_url(opds_client *client, const opds_feed *feed, const char *terms,
                            unsigned page, const opds_control *control,
                            char *out, size_t cap, opds_error *error);

/* ---- download ---- */
typedef enum { OPDS_READ_UNKNOWN = 0, OPDS_READ_OK, OPDS_READ_FAILED } opds_read_state;
/* Runs on the same-directory temporary file before publication. Return OPDS_OK when
   the book opens; OPDS_UNSUPPORTED means "cannot judge this type" (published, readable
   stays OPDS_READ_UNKNOWN); anything else prevents publication. */
typedef opds_status (*opds_verify_fn)(void *context, const char *path, const char *media_type,
                                      char *detail, size_t detail_cap);
typedef enum { OPDS_EXISTING_FAIL = 0, OPDS_EXISTING_REPLACE } opds_existing_policy;
typedef struct {
  const char *media_type;        /* declared by the acquisition link; NULL = accept any */
  opds_existing_policy existing;
  opds_verify_fn verify;
  void *verify_context;
  uint64_t max_bytes;            /* 0 = client limit */
} opds_download_options;
typedef struct {
  uint64_t bytes;
  char sha256[65];
  char sniffed_type[48];         /* empty when the content has no recognisable signature */
  int header_type_mismatch;      /* Content-Type header differed from the declared type */
  int already_present;           /* identical file already at the destination */
  int published;                 /* destination now holds the book */
  opds_read_state readable;      /* UNKNOWN when no verifier ran */
  char detail[160];
} opds_download_result;
/* dest_path: final file (host chosen). The directory must exist and the name must
   be a plain file name without traversal. Temp file lives next to it.
   Cancellation is polled after verification, during existing-file comparison,
   and immediately before atomic publication; a completed publication is not undone.
   No-replace fails with OPDS_IO when the filesystem lacks an atomic primitive. */
opds_status opds_download(opds_client *client, const opds_link *link,
                          const char *dest_path, const opds_download_options *options,
                          const opds_control *control, opds_download_result *result,
                          opds_error *error);
opds_status opds_download_url(opds_client *client, const char *url, const char *dest_path,
                              const opds_download_options *options, const opds_control *control,
                              opds_download_result *result, opds_error *error);

#ifdef __cplusplus
}
#endif
#endif
