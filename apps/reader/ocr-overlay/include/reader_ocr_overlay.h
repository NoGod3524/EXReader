/* SPDX-License-Identifier: MIT */
#ifndef READER_OCR_OVERLAY_H
#define READER_OCR_OVERLAY_H
#include <stddef.h>
#include <stdint.h>
#include <exr/document.h>
#ifdef __cplusplus
extern "C" {
#endif
#define READER_OCR_OVERLAY_VERSION "0.1.0"

/* Temporary OCR text/region snapshot for one rendered fixed page.

   What it is: the result of running the optional EXReaderOCR adapter (Tesseract)
   on a bitmap that the frozen SDK rendered (exr_fixed_render) or that the host
   rendered with the same exr_page_geometry and scale. Line and word records carry
   UTF-8 text, a Tesseract confidence (0..100, not a calibrated probability) and
   an exact page-space quad. The snapshot is labelled: info->source is always
   "tesseract-ocr"; native_text and permanent_anchor are always 0.

   What it is not: native PDF/page text. Nothing here writes SDK notes, the
   library, reading progress, a text layer or the source bytes; no file is
   created or opened except the language models read by the OCR backend. No
   exr_fixed_anchor / reading anchor is produced. A host that selects or searches
   the text (reader_ocr_overlay_to_fixed_text) must keep it session-local and
   must not persist offsets or the fixed text as a permanent anchor.

   Threads and reentry: an engine belongs to the thread that opened it. A call,
   close included, from another thread returns READER_OCR_OVERLAY_THREAD and
   changes nothing. A call made from inside an exr_control / still_current
   callback of the same engine returns READER_OCR_OVERLAY_BUSY and changes
   nothing. An exr_fixed_document passed to recognize_page is borrowed for that
   call and follows the SDK's own nonconcurrent/nonreentrant draw rule. A
   committed snapshot is immutable: its accessors may be called from any thread
   while no thread frees it. Free exactly once, not concurrently with reads.

   Memory ownership: input bitmaps and geometry are borrowed for the synchronous
   call only and never retained. An SDK-rendered bitmap is freed before return.
   The snapshot owns private copies of every string, record and the page id, so
   it outlives the bitmap, the fixed document and the engine.

   Commit boundary: a snapshot exists only on READER_OCR_OVERLAY_OK. Any other
   status leaves *out NULL and no partial records. After recognition and record
   building the call polls cancellation once more, then (if given) calls
   still_current; a zero result discards the work with READER_OCR_OVERLAY_STALE.

   Limits (values above a hard cap are refused with READER_OCR_OVERLAY_ARGUMENT):
   max_pixels 64,000,000; max_items 20,000; max_snapshot_bytes 4 MiB;
   timeout_ms 300,000; scale in (0,16]. Defaults: 16,000,000 pixels, 5,000
   records, 1 MiB, 30 s. Exceeding a budget returns LIMIT. The pixel limit is
   checked from the viewport size before any render. The deadline covers render
   and recognition as elapsed time and is cooperative; it is not a hard RSS/CPU
   cap (isolate the backend in a process if one is needed). Model loading in
   engine_open is outside it. The backend also bounds its own raw output to four
   times max_snapshot_bytes before records are reduced to lines and words. */
typedef enum {
  READER_OCR_OVERLAY_OK=0,
  READER_OCR_OVERLAY_ARGUMENT,      /* NULL, invalid option, bitmap/geometry mismatch, bad language */
  READER_OCR_OVERLAY_MEMORY,
  READER_OCR_OVERLAY_LIMIT,         /* pixel, record or snapshot-byte budget; no result */
  READER_OCR_OVERLAY_CANCELLED,     /* exr_control cancelled */
  READER_OCR_OVERLAY_TIMEOUT,       /* timeout_ms elapsed */
  READER_OCR_OVERLAY_MODEL_MISSING, /* <language>.traineddata absent or empty in the model directory */
  READER_OCR_OVERLAY_BACKEND,       /* model failed to initialize or recognition failed; sdk_code is exr_status */
  READER_OCR_OVERLAY_RENDER,        /* the SDK could not render the page; sdk_code is exr_status */
  READER_OCR_OVERLAY_STALE,         /* page/geometry/scale/pixels differ, or still_current returned 0 */
  READER_OCR_OVERLAY_BUSY,
  READER_OCR_OVERLAY_THREAD
} reader_ocr_overlay_status;
typedef struct {
  reader_ocr_overlay_status code;
  int sdk_code;
  char message[160];
} reader_ocr_overlay_error;

typedef struct reader_ocr_engine reader_ocr_engine;
typedef struct reader_ocr_overlay reader_ocr_overlay;

/* Package version of this module (READER_OCR_OVERLAY_VERSION), independent of
   the SDK release, the SDK ABI epoch, the product schema and any wire version. */
const char *reader_ocr_overlay_version(void);

/* Loads the caller-selected models. languages is "eng" or "eng+chi_sim" (each
   name [A-Za-z0-9_], at most 8 names, 64 bytes). Every <tessdata>/<name>.traineddata
   must be a nonempty regular file or the result is MODEL_MISSING. Model files and
   their licences are the host's to ship and register; this module bundles none. */
reader_ocr_overlay_status reader_ocr_engine_open(const char *tessdata_dir,const char *languages,
  reader_ocr_engine **out,reader_ocr_overlay_error *error);
/* Refused (handle kept) from another thread or from inside a callback. NULL is OK. */
reader_ocr_overlay_status reader_ocr_engine_close(reader_ocr_engine *engine,reader_ocr_overlay_error *error);

typedef struct {
  size_t struct_size;        /* sizeof this struct, set by options_default */
  exr_control control;       /* borrowed for the call */
  double scale;              /* render scale for recognize_page; must match the bitmap for recognize_bitmap */
  unsigned base_dpi;         /* dpi of the raster at scale 1; the backend sees round(base_dpi*scale), 70..2400 */
  unsigned content_rotation; /* 0/90/180/270: text is already rotated clockwise by this inside the unrotated page */
  unsigned timeout_ms;
  size_t max_pixels, max_items, max_snapshot_bytes;
  float min_confidence;      /* records below this Tesseract score are dropped, 0..100 */
  int (*still_current)(void *context); /* optional commit guard; 0 -> STALE */
  void *current_context;
} reader_ocr_overlay_options;
void reader_ocr_overlay_options_default(reader_ocr_overlay_options *options);

/* Renders `page` with exr_fixed_render(scale) on an opaque white canvas, then
   recognizes it and maps every quad back to page coordinates with
   exr_viewport_create(geometry, scale).inverse. The bitmap handed to the backend
   is orientation-corrected by (720 - geometry.rotation - content_rotation) % 360
   degrees clockwise, so page-space quads are independent of that rotation. */
reader_ocr_overlay_status reader_ocr_overlay_recognize_page(reader_ocr_engine *engine,exr_fixed_document *document,
  size_t page,const reader_ocr_overlay_options *options,reader_ocr_overlay **out,reader_ocr_overlay_error *error);
/* Same for a host-rendered bitmap (gray or RGBA) of the page at options->scale.
   Its size must equal the viewport size rounded up. page_id is copied. */
reader_ocr_overlay_status reader_ocr_overlay_recognize_bitmap(reader_ocr_engine *engine,const char *page_id,
  const exr_page_geometry *geometry,const exr_bitmap *bitmap,const reader_ocr_overlay_options *options,
  reader_ocr_overlay **out,reader_ocr_overlay_error *error);
void reader_ocr_overlay_free(reader_ocr_overlay *overlay);

enum { READER_OCR_LINE=1, READER_OCR_WORD=2 };
typedef struct {
  uint32_t level;                 /* READER_OCR_LINE or READER_OCR_WORD */
  float confidence;               /* Tesseract 0..100 */
  size_t text_offset, text_bytes; /* UTF-8 slice of reader_ocr_overlay_text */
  double page_quad[8];            /* TL,TR,BR,BL of the recognized (upright) text, page coordinates */
  double pixel_quad[8];           /* the same corners in the rendered bitmap */
} reader_ocr_overlay_item;
typedef struct {
  const char *source;   /* always "tesseract-ocr" */
  const char *backend;  /* Tesseract version string */
  const char *languages;
  const char *page_id;
  exr_page_geometry geometry;
  double scale;
  uint32_t bitmap_width, bitmap_height;
  unsigned dpi, clockwise; /* what the backend saw: effective dpi and total orientation correction */
  uint64_t pixel_fnv1a;    /* identity hint of the recognized pixels (FNV-1a 64), not a security hash */
  int native_text, permanent_anchor; /* always 0 */
  size_t count, text_bytes, memory_bytes;
} reader_ocr_overlay_info;
/* Borrowed views, valid until reader_ocr_overlay_free. A page without text is a
   success with count==0 and an empty string. Items are line records, then word records. */
const reader_ocr_overlay_info *reader_ocr_overlay_get_info(const reader_ocr_overlay *overlay);
const reader_ocr_overlay_item *reader_ocr_overlay_items(const reader_ocr_overlay *overlay,size_t *count);
const char *reader_ocr_overlay_text(const reader_ocr_overlay *overlay,size_t *bytes);

/* OK when page id, geometry and scale equal the snapshot's and, if bitmap is
   given, its size and pixel hash too; otherwise STALE. Nothing is retained. */
reader_ocr_overlay_status reader_ocr_overlay_check_current(const reader_ocr_overlay *overlay,const char *page_id,
  const exr_page_geometry *geometry,double scale,const exr_bitmap *bitmap,reader_ocr_overlay_error *error);
/* Copies one level into an independent SDK fixed text (one record per line/word,
   joined by '\n', page-space quads) for session-local find/select/hit. Free with
   exr_fixed_text_free. This is temporary OCR text, not a persistent anchor source. */
reader_ocr_overlay_status reader_ocr_overlay_to_fixed_text(const reader_ocr_overlay *overlay,unsigned level,
  const exr_control *control,exr_fixed_text **out,reader_ocr_overlay_error *error);
#ifdef __cplusplus
}
#endif
#endif
