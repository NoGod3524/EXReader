/* SPDX-License-Identifier: MIT */
#ifndef READER_PREFERENCES_H
#define READER_PREFERENCES_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define READER_PREFERENCES_VERSION_STRING "0.1.0"
#define READER_PREFERENCES_ABI_VERSION 1u

#if defined(_WIN32) && defined(READER_PREFERENCES_BUILD_SHARED)
#define READER_PREFERENCES_API __declspec(dllexport)
#elif defined(_WIN32) && defined(READER_PREFERENCES_USE_SHARED)
#define READER_PREFERENCES_API __declspec(dllimport)
#else
#define READER_PREFERENCES_API
#endif

/* Portable reading-appearance settings. This package only stores, validates and
   imports values; it never creates a layout, paginates, paints or observes the
   platform theme. The host applies the values through the public SDK and its own
   UI. Every value is device-local: no wire entity, product schema table or SDK
   table is read or written.

   Struct lifetime: reader_preferences, the legacy record and the report are plain
   caller-owned values. The library never retains a pointer to them. Paths are
   borrowed UTF-8 for the duration of one call and are never retained. */
typedef enum {
  READER_PREFERENCES_OK = 0,
  READER_PREFERENCES_ARGUMENT = 1,  /* null/invalid struct, enum or option */
  READER_PREFERENCES_IO = 2,        /* open/read/write/rename/fsync failed */
  READER_PREFERENCES_FORMAT = 3,    /* not the canonical document shape */
  READER_PREFERENCES_VERSION = 4,   /* valid document, unsupported format version */
  READER_PREFERENCES_RANGE = 5,     /* NaN, infinity or a value outside its range */
  READER_PREFERENCES_CANCELLED = 6, /* caller control asked to stop */
  READER_PREFERENCES_LIMIT = 7      /* file exceeds max_file_bytes */
} reader_preferences_status;

typedef enum {
  READER_PREFERENCES_THEME_LIGHT = 1,
  READER_PREFERENCES_THEME_DARK = 2,
  READER_PREFERENCES_THEME_SYSTEM = 3
} reader_preferences_theme;

typedef enum {
  READER_PREFERENCES_TURN_LTR = 1,
  READER_PREFERENCES_TURN_RTL = 2,
  READER_PREFERENCES_TURN_VERTICAL = 3
} reader_preferences_turn_direction;

typedef enum {
  READER_PREFERENCES_INPUT_TAP = 1,
  READER_PREFERENCES_INPUT_SWIPE = 2,
  READER_PREFERENCES_INPUT_TAP_AND_SWIPE = 3,
  READER_PREFERENCES_INPUT_HARDWARE_KEYS = 4
} reader_preferences_turn_input;

/* Zero-initialize the struct and set struct_size. */
typedef struct {
  uint32_t struct_size;
  reader_preferences_status status;
  int system_error; /* errno or GetLastError when status is IO, else 0 */
  size_t offset;    /* byte offset in the document for FORMAT/VERSION/RANGE */
  char message[192];
} reader_preferences_error;

/* Return nonzero to cancel. Called synchronously on the calling thread. */
typedef int (*reader_preferences_cancel_fn)(void *context);
typedef struct {
  reader_preferences_cancel_fn cancelled;
  void *context;
} reader_preferences_control;

typedef struct {
  uint32_t struct_size;
  reader_preferences_control control;
  size_t max_file_bytes; /* 0 = 65536; may only lower it. Larger values return ARGUMENT. */
} reader_preferences_load_options;

typedef struct {
  uint32_t struct_size;
  reader_preferences_control control;
} reader_preferences_save_options;

/* Appearance record. All fields are significant; reserved words must be zero.
   font_size, paragraph_spacing and margin are points; line_spacing is the
   dimensionless multiplier used by exr_layout_options.line_height.
   fixed_page_zoom is an integer percentage for exr_fixed_render's scale.
   Colors are sRGB bytes in R,G,B,A order; alpha 255 is opaque. */
typedef struct {
  uint32_t struct_size;
  uint32_t abi_version;
  float font_size;
  float line_spacing;
  float paragraph_spacing;
  float margin;
  uint32_t theme;               /* reader_preferences_theme */
  uint32_t page_turn_direction; /* reader_preferences_turn_direction */
  uint32_t page_turn_input;     /* reader_preferences_turn_input */
  uint32_t fixed_page_zoom;     /* 25..400 percent */
  uint8_t light_foreground[4];
  uint8_t light_background[4];
  uint8_t dark_foreground[4];
  uint8_t dark_background[4];
  uint32_t reserved[8];
} reader_preferences;

/* Explicit legacy import. Only fields whose bit is present in 'present' are
   read. Unlisted fields keep the caller's current value. Unknown present bits
   are an ARGUMENT error and nothing is applied. */
enum {
  READER_PREFERENCES_LEGACY_FONT_SIZE = 1u << 0,
  READER_PREFERENCES_LEGACY_LINE_SPACING = 1u << 1,
  READER_PREFERENCES_LEGACY_PARAGRAPH_SPACING = 1u << 2,
  READER_PREFERENCES_LEGACY_MARGIN = 1u << 3,
  READER_PREFERENCES_LEGACY_THEME = 1u << 4,
  READER_PREFERENCES_LEGACY_TURN_DIRECTION = 1u << 5,
  READER_PREFERENCES_LEGACY_TURN_INPUT = 1u << 6,
  READER_PREFERENCES_LEGACY_FIXED_ZOOM = 1u << 7,
  READER_PREFERENCES_LEGACY_LIGHT_FOREGROUND = 1u << 8,
  READER_PREFERENCES_LEGACY_LIGHT_BACKGROUND = 1u << 9,
  READER_PREFERENCES_LEGACY_DARK_FOREGROUND = 1u << 10,
  READER_PREFERENCES_LEGACY_DARK_BACKGROUND = 1u << 11,
  READER_PREFERENCES_LEGACY_ALL = 0xfffu
};

typedef struct {
  uint32_t struct_size;
  uint32_t present; /* READER_PREFERENCES_LEGACY_* bits */
  float font_size;
  float line_spacing;
  float paragraph_spacing;
  float margin;
  uint32_t theme;
  uint32_t page_turn_direction;
  uint32_t page_turn_input;
  uint32_t fixed_page_zoom;
  uint8_t light_foreground[4];
  uint8_t light_background[4];
  uint8_t dark_foreground[4];
  uint8_t dark_background[4];
} reader_preferences_legacy;

typedef struct {
  uint32_t struct_size;
  uint32_t applied;   /* legacy bits copied into the record */
  uint32_t preserved; /* legacy bits absent from 'present' */
} reader_preferences_import_report;

/* ABI and defaults. defaults() sets struct_size, abi_version and reserved. */
READER_PREFERENCES_API uint32_t reader_preferences_abi_version(void);
READER_PREFERENCES_API reader_preferences reader_preferences_defaults(void);
READER_PREFERENCES_API const char *reader_preferences_status_name(reader_preferences_status status);
READER_PREFERENCES_API void reader_preferences_error_clear(reader_preferences_error *error);

/* Field validation only: struct identity, finite numbers, ranges, enums and
   zero reserved words. It does not know the host viewport; the host must also
   satisfy the SDK's composed geometry check before layout. */
READER_PREFERENCES_API reader_preferences_status
reader_preferences_validate(const reader_preferences *preferences,
                             reader_preferences_error *error);

/* Load replaces *inout only after the whole document parsed and validated.
   On every failure, including cancel and an unknown version, *inout is
   byte-for-byte untouched and the document on disk is not modified. */
READER_PREFERENCES_API reader_preferences_status
reader_preferences_load(const char *utf8_path, reader_preferences *inout,
                        const reader_preferences_load_options *options,
                        reader_preferences_error *error);

/* Save validates first. The document is written to a same-directory temporary
   file, flushed, then atomically renamed over utf8_path. Failure or cancel
   before the rename deletes the temporary and leaves the previous file whole.
   After a successful rename the result is durable and OK is returned even if
   the caller cancels late. */
READER_PREFERENCES_API reader_preferences_status
reader_preferences_save(const reader_preferences *preferences, const char *utf8_path,
                        const reader_preferences_save_options *options,
                        reader_preferences_error *error);

/* Transactional legacy import: validate the merged record first, then assign.
   On any error, *preferences and *report are untouched. report may be NULL. */
READER_PREFERENCES_API reader_preferences_status
reader_preferences_import_legacy(reader_preferences *preferences,
                                 const reader_preferences_legacy *legacy,
                                 reader_preferences_import_report *report,
                                 reader_preferences_error *error);

/* Resolves SYSTEM with the host-supplied current theme. system_theme must be
   LIGHT or DARK; SYSTEM or any other value falls back to LIGHT. A stored LIGHT
   or DARK ignores system_theme. Pure function; no notification is registered. */
READER_PREFERENCES_API reader_preferences_theme
reader_preferences_effective_theme(const reader_preferences *preferences,
                                   reader_preferences_theme system_theme);

#ifdef __cplusplus
}
#endif
#endif
