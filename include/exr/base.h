/* SPDX-License-Identifier: MIT */
#ifndef EXR_BASE_H
#define EXR_BASE_H
#include <stddef.h>
#include <stdint.h>
#if defined(EXR_STATIC)
#define EXR_API
#elif defined(_WIN32)
#if defined(EXR_BUILD)
#define EXR_API __declspec(dllexport)
#else
#define EXR_API __declspec(dllimport)
#endif
#else
#define EXR_API __attribute__((visibility("default")))
#endif
#define EXR_VERSION "3.34.2"
#define EXR_ABI_VERSION 1u
#define EXR_CORE_VERSION "3.34.2"
#ifdef __cplusplus
extern "C" {
#endif
typedef enum {
  EXR_OK = 0,
  EXR_ARGUMENT,
  EXR_MEMORY,
  EXR_IO,
  EXR_ENCODING,
  EXR_FORMAT,
  EXR_LIMIT,
  EXR_DATABASE,
  EXR_FONT,
  EXR_CANCELLED,
  EXR_PASSWORD, /* Missing or incorrect PDF password; caller may retry opening. */
  EXR_UNSUPPORTED /* Recognized feature requires an unavailable/unsupported component. */
} exr_status;
typedef enum {
  EXR_CUSTOM = 0, /* Constructed through exr_document_create(), without a file decoder. */
  EXR_TXT = 1,
  EXR_HTML,
  EXR_FB2,
  EXR_EPUB,
  EXR_DOCX,
  EXR_RTF,
  EXR_MOBI,
  EXR_PDF,
  EXR_CBZ
} exr_format;
typedef struct {
  exr_status code;
  char message[256];
} exr_error;
typedef enum {
  EXR_STAGE_READ = 1, EXR_STAGE_STYLE, EXR_STAGE_LAYOUT, EXR_STAGE_SHAPE, EXR_STAGE_RENDER, EXR_STAGE_EXPORT
} exr_stage;
/* Synchronous callbacks on the calling thread. total==0 means unknown work.
   Callbacks must not destroy/reenter active objects. Context is borrowed. */
typedef struct {
  int (*cancelled)(void *context);
  void (*progress)(void *context, exr_stage stage, uint64_t completed, uint64_t total);
  void *context;
} exr_control;
typedef struct exr_document exr_document;
typedef struct exr_font exr_font;
typedef struct exr_layout exr_layout;
typedef struct exr_library exr_library;
typedef struct exr_publication exr_publication;
typedef struct exr_session exr_session;
typedef struct exr_pager exr_pager;

typedef void (*exr_context_release_fn)(void *context);
/* Immutable, seekable byte source. read_at returns bytes supplied (short reads
   are retried); zero before the advertised end is EXR_IO. No network policy is
   imposed on host callbacks. Built-in file sources only access the chosen file.
   Context ownership transfers only on successful open. Retained documents may
   outlive their publication; release runs after the last source reference. */
typedef size_t (*exr_read_at_fn)(void *context, uint64_t offset, void *buffer, size_t size);
typedef struct {
  uint64_t size;
  exr_read_at_fn read_at;
  exr_context_release_fn release;
  void *context;
  exr_control control;
} exr_source;
typedef struct exr_bitmap exr_bitmap;
struct exr_bitmap {
  uint32_t width, height, stride;
  unsigned char *pixels;
  uint32_t channels; /* 1 (gray) or 4 (RGBA); zero accepted as gray on write. */
};
/* Format-independent fixed-page coordinates. bounds are [x0,y0,x1,y1],
   unit_scale is positive, rotation is clockwise 0/90/180/270. */
typedef struct {
  double bounds[4],unit_scale;
  unsigned rotation,y_down;
} exr_page_geometry;
typedef struct {
  double width,height;
  double matrix[6],inverse[6]; /* x'=a*x+c*y+e, y'=b*x+d*y+f */
} exr_viewport;
/* Maps a source page to a top-left, y-down viewport at the selected scale.
   Both transforms are returned for painting and hit testing; no allocation. */
EXR_API exr_status exr_viewport_create(const exr_page_geometry *page,double scale,
                                        exr_viewport *out,exr_error *error);
/* UTF-8 key/value metadata, independent of a file format. Provider values are
   borrowed until its next operation; load_metadata returns owned copies. */
typedef struct { const char *key,*value; } exr_metadata_entry;
EXR_API void exr_metadata_free(exr_metadata_entry *entries,size_t count);
/* All input/output strings are UTF-8. Returned views belong to their owner. */
EXR_API const char *exr_version(void);
/* Binary layout/calling-contract epoch, independent from release/schema versions. */
EXR_API uint32_t exr_abi_version(void);
EXR_API void exr_free(void *memory);
EXR_API exr_status exr_bitmap_write_png(const exr_bitmap *bitmap, const char *path,
                                        exr_error *error);
EXR_API void exr_bitmap_free(exr_bitmap *bitmap);
EXR_API exr_status exr_bitmap_write_bmp(const exr_bitmap *bitmap, const char *path,
                                        exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
