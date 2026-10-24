/* SPDX-License-Identifier: MIT */
/* EXReaderThumbnails 0.1.0: bounded cover / first-page thumbnails over the frozen
   reading SDK (3.40.0, ABI 1). Public C ABI; no thread is ever created.

   Ownership: a cache and every borrowed SDK handle (exr_library,
   exr_fixed_document) belong to the thread that opened/created them; every call
   runs synchronously on that thread. Every entry point that takes a cache
   (open, stats, clear, find, find/cover/preview, close) refuses a call from another
   thread, and refuses re-entry from a control callback, with RTH_ARGUMENT; such a
   refusal changes nothing and rth_cache_close leaves the cache alive. No C++
   exception crosses the ABI: allocation and filesystem failures return RTH_MEMORY
   or RTH_IO, the output box is left empty (width/height/origin 0, pixels NULL) and
   nothing leaks - a failed open holds no lock and a failed cover keeps the cache
   usable for a retry.

   Two origins are never mixed: RTH_ORIGIN_AUTHOR_COVER is an image the book
   declares as its cover; RTH_ORIGIN_FIRST_PAGE_PREVIEW is a page rendered from a
   fixed-layout (PDF/CBZ) book. A book without a stored cover is the normal
   placeholder state (RTH_OK, origin RTH_ORIGIN_NONE, no pixels). Bounded
   source/file EPUB imports store no cover; this module does not open the ZIP or
   load the whole book to invent one.

   rth_limits.max_entries / max_total_bytes are a hard bound on the directory that
   holds this cache: a cache handle exists only while the directory holds no more own
   entry files or bytes than those limits allow, and only one cache handle owns a
   directory at a time (RTH_BUSY otherwise). They bound nothing else. Decoding an
   author cover
   allocates the full decoded source image (width*height*4 bytes) transiently;
   rth_limits.max_source_pixels bounds that, and rth_thumbnail.decoded_bytes /
   rth_stats.peak_decoded_bytes report it separately from cache bytes. */
#ifndef READER_THUMBNAILS_H
#define READER_THUMBNAILS_H
#include <exr/library.h>
#ifdef __cplusplus
extern "C" {
#endif
#define RTH_VERSION "0.1.0"
#define RTH_EDGE_HARD_MAX 1024u
#define RTH_ENTRIES_HARD_MAX 4096u
#define RTH_TOTAL_BYTES_HARD_MAX (512ull * 1024ull * 1024ull)
#define RTH_TOTAL_BYTES_MIN 4096ull
#define RTH_SOURCE_PIXELS_HARD_MAX 16777216ull
#define RTH_ENCODED_HARD_MAX (16u * 1024u * 1024u)

typedef enum {
  RTH_OK = 0, RTH_ARGUMENT, RTH_MEMORY, RTH_IO, RTH_FORMAT, RTH_LIMIT,
  RTH_CANCELLED, RTH_UNSUPPORTED, RTH_SDK,
  RTH_BUSY /* the directory is already owned by another cache (another handle,
              process or a not-yet-collected dead one: the OS releases the lock) */
} rth_status;
typedef struct {
  rth_status code;
  int sdk_code; /* exr_status of the failing SDK call, or -1 */
  char message[256];
} rth_error;
typedef enum {
  RTH_ORIGIN_NONE = 0, /* placeholder: no image */
  RTH_ORIGIN_AUTHOR_COVER = 1,
  RTH_ORIGIN_FIRST_PAGE_PREVIEW = 2
} rth_origin;

/* Set struct_size, then override. Zero fields are refused except by defaults(). */
typedef struct {
  size_t struct_size;
  uint32_t max_edge;          /* output width/height bound, <= RTH_EDGE_HARD_MAX */
  uint32_t max_entries;       /* <= RTH_ENTRIES_HARD_MAX */
  uint64_t max_total_bytes;   /* cache directory bytes, RTH_TOTAL_BYTES_MIN..HARD_MAX */
  uint64_t max_source_pixels; /* decoded source pixels, <= RTH_SOURCE_PIXELS_HARD_MAX */
  uint32_t max_encoded_bytes; /* encoded cover bytes, <= RTH_ENCODED_HARD_MAX */
} rth_limits;
rth_limits rth_limits_defaults(void);

/* Polled on the calling thread; nonzero cancels. The call then returns
   RTH_CANCELLED, outputs are cleared and no cache entry is published. */
typedef struct {
  int (*cancelled)(void *context);
  void *context;
} rth_control;

/* Verified original-book identity supplied by the host: exr_format code 1..9 and
   the lowercase hex SHA-256 of the original bytes (rth_sha256_hex). */
typedef struct {
  int format;
  char sha256[65];
} rth_book;

/* Output box (contain-fit, never upscaled). page/background apply only to
   previews; background is 0xRRGGBBAA. */
typedef struct {
  size_t struct_size;
  uint32_t width, height;
  uint32_t page;
  uint32_t background;
} rth_request;
rth_request rth_request_defaults(void);

/* RGBA8, straight alpha, stride == width*4. origin NONE: width/height 0, pixels NULL. */
typedef struct {
  rth_origin origin;
  uint32_t width, height, stride;
  unsigned char *pixels;
  int from_cache;           /* 1 when served from the cache file */
  int stored;               /* 1 when this call published a new cache entry */
  uint32_t source_width, source_height;
  uint64_t decoded_bytes;   /* transient decoded/rendered source bytes of this call (0 on a hit) */
} rth_thumbnail;
void rth_thumbnail_free(rth_thumbnail *thumbnail);

typedef struct {
  size_t struct_size;
  uint32_t entries;
  uint64_t bytes;
  uint64_t hits, misses, stores, evictions, corrupt_rebuilt, rejected, store_failures;
  uint64_t last_decoded_bytes, peak_decoded_bytes;
  /* Publishing and scanning accounting. index_failures counts index publications
     whose atomic replace failed (rth_cache_open and rth_cache_clear return RTH_IO
     instead of hiding such a failure). scanned_files is the number of directory
     entries one successful open inspected, own_candidates the subset that are
     cache files of this module, scan_deleted the own entry files removed during
     that scan (damaged, over the count/byte cap, or larger than max_total_bytes),
     and peak_retained_entries the largest entry map it ever held: at most max_entries
     retained entries plus the one candidate being admitted (max_entries + 1), because
     the candidate takes part in the eviction choice. */
  uint64_t index_failures, scanned_files, own_candidates, scan_deleted, peak_retained_entries;
} rth_stats;

typedef struct rth_cache rth_cache;
/* Opens/creates the directory, takes its owner lock and adopts valid entries in ONE
   pass over the directory with a bounded working set (at most max_entries entries
   plus one name are ever held). Only files it recognises as its own are deleted.
   Every call that returns RTH_OK leaves the directory in a state where the sum of
   its own entry files is <= max_entries and their bytes <= max_total_bytes: surplus
   and damaged entries are deleted during the pass, so the limits are a hard bound on
   the directory, not on an observed prefix. A directory holding more own entry files
   than the scan ceiling (max(4096, max_entries*64), at most 65536) is refused with
   RTH_LIMIT instead of being adopted partially.

   One cache per directory: the owner lock is an OS lock on "rth-owner.lock" (flock on
   POSIX, an exclusive open without sharing on Windows). A second open - another
   handle in the same process, another process, or one whose holder died and whose
   handle the OS already released - returns RTH_BUSY when the lock is held. The lock
   is released when the cache is closed or the holding process dies. Files are created
   exclusively under an unpredictable per-open temporary name and published with a
   same-directory atomic replace; open removes temporaries of the pre-0.1.0 naming at
   once and temporaries of the current naming only when older than 600 s.

   Returns RTH_IO when the index cannot be published atomically, RTH_LIMIT when the
   directory exceeds the scan ceiling, RTH_MEMORY on allocation failure; in every one
   of those cases *out is NULL, no lock is held and the directory can be retried. */
rth_status rth_cache_open(const char *directory_utf8, const rth_limits *limits, rth_cache **out, rth_error *error);
void rth_cache_close(rth_cache *cache); /* persists LRU order */
rth_status rth_cache_clear(rth_cache *cache, rth_error *error);
rth_status rth_cache_stats(const rth_cache *cache, rth_stats *stats, rth_error *error);

/* Cache-only lookup (author cover stored from a library, or a preview); found=0
   is not an error. */
rth_status rth_cache_find(rth_cache *cache, const rth_book *book, rth_origin origin, const rth_request *request,
                          rth_thumbnail *out, int *found, rth_error *error);

/* Author cover from exr_library_blob(cover=1). The library is borrowed. */
rth_status rth_cover_from_library(rth_cache *cache, exr_library *library, int64_t book_id, const rth_book *book,
                                  const rth_request *request, const rth_control *control,
                                  rth_thumbnail *out, rth_error *error);
/* Host-verified encoded cover (data may be NULL/0 for "no cover"). */
rth_status rth_cover_from_encoded(rth_cache *cache, const rth_book *book, const void *data, size_t size,
                                  const rth_request *request, const rth_control *control,
                                  rth_thumbnail *out, rth_error *error);
/* First-page (request->page) preview of a PDF/CBZ document; borrowed. */
rth_status rth_preview_from_fixed(rth_cache *cache, exr_fixed_document *document, const rth_book *book,
                                  const rth_request *request, const rth_control *control,
                                  rth_thumbnail *out, rth_error *error);

/* 64 lowercase hex digits plus NUL. */
void rth_sha256_hex(const void *data, size_t size, char out[65]);
#ifdef __cplusplus
}
#endif
#endif
