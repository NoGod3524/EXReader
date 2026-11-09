/* SPDX-License-Identifier: MIT */
#ifndef EXR_FONT_MANAGER_H
#define EXR_FONT_MANAGER_H
#include "text.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Font discovery, index, selection and fallback, shared by hosts and the engine.

   Additive API: exr_font_open()/exr_font_create() keep their exact semantics.
   A manager is built once by exr_font_manager_create()/exr_font_manager_open()
   and is immutable afterwards. Every const query below may run concurrently
   from any number of threads without external locking. The only write is the
   optional index cache, done at most once inside create(), via a private
   temporary file renamed over the cache path.

   All strings are UTF-8. Borrowed strings stay valid until the manager is freed.

   Fallback chain for (family, style), shared by pick() and create_font():
     1. requested family (or each family of a CSS-like comma list), nearest style
     2. other styles of the requested family
     3. options.fallback_families, in order (nearest style, then other styles)
     4. system serif families (options.serif_families or platform defaults)
     5. system sans-serif families (options.sans_serif_families or defaults)
     6. remaining discovered faces, color-capable faces first (emoji sequences),
        then greatest additional scalar coverage;
        nearest style breaks ties, then discovery order
   In stages 1-5, each family contributes its nearest-weight face per style
   category (four at most), so duplicates cannot crowd out later families. Faces
   already listed or adding no scalar coverage are omitted; the first face is
   always retained. Setting both system family lists to "" disables stage 6.
   This coverage compaction preserves the first matching face for each scalar.
   The discovered tail respects the manager's 256 MiB font input budget. The chain holds at most
   EXR_FONT_CHAIN_MAX faces. pick() returns the first chain face whose Unicode
   cmap covers the code point. create_font() loads the same chain in the same
   order into an exr_font whose base-face order is preserved by layout/shaping
   (exr_glyph.font_index, EXR_GLYPH_MISSING). Embedded @font-face rules retain
   their existing CSS priority: the automatic tail is shortened when necessary
   to fit embedded faces within the 32-face/256-MiB limits. Disable embedded_fonts to enforce only this
   chain. Returned exr_font objects have the usual exr_font concurrency rules
   (one per layout worker), unlike the immutable, shareable manager. */

#define EXR_FONT_CHAIN_MAX 32u

/* Style bits match EXR_GLYPH_BOLD / EXR_GLYPH_ITALIC. */
enum {
  EXR_FONT_STYLE_REGULAR = 0, EXR_FONT_STYLE_BOLD = 1, EXR_FONT_STYLE_ITALIC = 2,
  EXR_FONT_STYLE_BOLD_ITALIC = 3
};
/* Script coverage bits, derived from the Unicode cmap. LATIN: at least 40 of
   the 52 basic Latin letters. CJK: at least one Han, Kana, Hangul or CJK
   symbol/punctuation scalar. OTHER: any letter-range scalar outside those
   (Greek, Cyrillic, Arabic, Indic, ...). */
enum { EXR_FONT_SCRIPT_LATIN = 1, EXR_FONT_SCRIPT_CJK = 2, EXR_FONT_SCRIPT_OTHER = 4 };

/* One discovery input. Directories are scanned recursively (depth <= 8) for
   .ttf/.otf/.ttc/.otc; every face of a collection is indexed. A required
   location that is missing or unreadable fails create() with EXR_IO and names
   the path; no bundled or system font is substituted silently. */
enum { EXR_FONT_LOCATION_DIRECTORY = 0, EXR_FONT_LOCATION_FILE = 1 };
enum { EXR_FONT_LOCATION_OPTIONAL = 1 };
typedef struct {
  const char *path;
  unsigned kind;  /* EXR_FONT_LOCATION_DIRECTORY or EXR_FONT_LOCATION_FILE. */
  unsigned flags; /* EXR_FONT_LOCATION_OPTIONAL: missing path is recorded, not fatal. */
} exr_font_location;

/* Appends the platform user font directory, then the system font directories,
   after options.locations, all OPTIONAL. Windows: %LOCALAPPDATA%\Microsoft\
   Windows\Fonts, %WINDIR%\Fonts. macOS: ~/Library/Fonts, /Library/Fonts,
   /System/Library/Fonts. Linux: $XDG_DATA_HOME/fonts (or ~/.local/share/fonts),
   ~/.fonts, /usr/local/share/fonts, /usr/share/fonts. Android: /system/fonts,
   /product/fonts. */
enum { EXR_FONT_MANAGER_PLATFORM_DIRECTORIES = 1 };

typedef struct {
  size_t struct_size;                 /* sizeof(exr_font_manager_options). */
  const exr_font_location *locations; /* Scanned in order; earlier locations win ties. */
  size_t location_count;
  const char *const *fallback_families; /* Chain step 3, in order. May be NULL. */
  size_t fallback_count;
  const char *serif_families;      /* Comma list; NULL selects platform defaults. */
  const char *sans_serif_families; /* Comma list; NULL selects platform defaults. */
  const char *cache_path;          /* Persistent index file; NULL disables the cache. */
  unsigned flags;                  /* EXR_FONT_MANAGER_*. */
} exr_font_manager_options;

typedef struct exr_font_manager exr_font_manager;

/* Scans, indexes and (with cache_path) reuses/writes the persistent index.
   Options and the strings they point to are only read during the call.
   Failure leaves *out NULL: EXR_ARGUMENT for invalid options, EXR_IO for a
   missing/unreadable required location (message names the path), EXR_FONT
   when no usable Unicode face was found at all, EXR_MEMORY, EXR_LIMIT
   (more than 65536 faces). Damaged or non-font files never fail create();
   they are recorded as skips. An unreadable/stale/corrupt cache is ignored and
   rebuilt; a failed cache write is reported in the summary, not as failure. */
EXR_API exr_status exr_font_manager_create(const exr_font_manager_options *options,
                                           exr_font_manager **out, exr_error *error);

/* Loads a line-based UTF-8 configuration file and calls create().
   Format (one "key = value" per line, '#' comments, blank lines ignored):
     version = 1                (required, first key)
     font_dir = <dir>           required directory
     font_dir? = <dir>          optional directory
     font_file = <file>         required single font file (font_file? optional)
     platform_dirs = yes|no     EXR_FONT_MANAGER_PLATFORM_DIRECTORIES
     fallback = <family>        repeated, chain step 3 in order
     serif = <family, ...>      chain step 4 (replaces platform defaults)
     sans_serif = <family, ...> chain step 5 (replaces platform defaults)
     cache = <file>             persistent index path
   Relative paths resolve against the configuration file's directory.
   Unknown keys, a missing/unsupported version or malformed lines fail with
   EXR_FORMAT and the line number in the message. */
EXR_API exr_status exr_font_manager_open(const char *config_path, exr_font_manager **out,
                                         exr_error *error);
EXR_API void exr_font_manager_free(exr_font_manager *manager);

enum { EXR_FONT_CACHE_DISABLED = 0, EXR_FONT_CACHE_MISS = 1, EXR_FONT_CACHE_PARTIAL = 2,
       EXR_FONT_CACHE_HIT = 3 };
typedef struct {
  size_t struct_size;     /* Initialize to sizeof(exr_font_manager_summary). */
  size_t families;        /* Distinct family names (case-insensitive). */
  size_t files;           /* Font files that contributed at least one face. */
  size_t faces;           /* Indexed faces. */
  size_t skipped;         /* exr_font_manager_skip() count. */
  size_t parsed_files;    /* Files opened with FreeType during this create(). */
  size_t cached_files;    /* Files restored from the cache without parsing. */
  unsigned cache;         /* EXR_FONT_CACHE_*. */
  unsigned cache_written; /* 1 when the index file was (re)written. */
  exr_status cache_write_status; /* EXR_OK unless writing the cache failed. */
  double elapsed_ms;      /* Wall time of create(), including cache I/O. */
} exr_font_manager_summary;
EXR_API exr_status exr_font_manager_summary_get(const exr_font_manager *manager,
                                                exr_font_manager_summary *out, exr_error *error);

enum {
  EXR_FONT_SKIP_NOT_FONT = 1,     /* Extension is not .ttf/.otf/.ttc/.otc. */
  EXR_FONT_SKIP_DAMAGED = 2,      /* FreeType cannot open the file/face. */
  EXR_FONT_SKIP_UNSUPPORTED = 3,  /* No Unicode cmap, or not a scalable/CBDT face. */
  EXR_FONT_SKIP_IO = 4,           /* Cannot stat/read the file. */
  EXR_FONT_SKIP_MISSING = 5       /* Optional location does not exist. */
};
typedef struct {
  const char *path;   /* Borrowed. */
  unsigned reason;    /* EXR_FONT_SKIP_*. */
  const char *detail; /* Borrowed human-readable reason. */
} exr_font_skip;
/* Borrowed skip record; returns 0 when index is out of range. */
EXR_API int exr_font_manager_skip(const exr_font_manager *manager, size_t index, exr_font_skip *out);

typedef struct {
  size_t struct_size;  /* Initialize to sizeof(exr_font_face_info). */
  const char *family;  /* Typographic family (name ID 16, else FreeType family). Borrowed. */
  const char *style_name; /* Borrowed. */
  const char *path;    /* Borrowed. */
  unsigned face_index; /* Face within a collection. */
  unsigned style;      /* EXR_FONT_STYLE_*. */
  unsigned weight;     /* OS/2 usWeightClass, 400 when absent. */
  unsigned scripts;    /* EXR_FONT_SCRIPT_* bits. */
  size_t location;     /* Index of the discovery location (options + platform order). */
  size_t codepoints;   /* Number of Unicode scalars mapped by the cmap. */
} exr_font_face_info;
EXR_API size_t exr_font_manager_face_count(const exr_font_manager *manager);
/* Fills *out with borrowed views. EXR_ARGUMENT for a bad index or struct_size. */
EXR_API exr_status exr_font_manager_face(const exr_font_manager *manager, size_t index,
                                         exr_font_face_info *out, exr_error *error);
/* Indexed cmap coverage (no file access); 0 for invalid input. */
EXR_API int exr_font_manager_face_covers(const exr_font_manager *manager, size_t index,
                                         uint32_t codepoint);
/* Case-insensitive match against the family or any localized family name. */
EXR_API int exr_font_manager_has_family(const exr_font_manager *manager, const char *family);

enum {
  EXR_FONT_STEP_NONE = 0,       /* No indexed face in the chain covers the scalar. */
  EXR_FONT_STEP_REQUESTED = 1,  /* Requested family, nearest style. */
  EXR_FONT_STEP_FAMILY_STYLE = 2, /* Requested family, another style. */
  EXR_FONT_STEP_FALLBACK = 3,   /* Configured fallback family. */
  EXR_FONT_STEP_SERIF = 4,      /* System serif. */
  EXR_FONT_STEP_SANS_SERIF = 5, /* System sans-serif. */
  EXR_FONT_STEP_DISCOVERED = 6 /* Additional coverage from the discovered inventory. */
};
typedef struct { size_t face; unsigned step; } exr_font_chain_link;

/* Owned fallback chain (see top of file), freed with exr_free(). family may be
   a single name, a CSS-like comma list, or the generic "serif"/"sans-serif"
   (which select steps 4/5 as the requested family). An unknown family is not
   an error: the chain starts at step 3. An empty chain returns NULL/0 with
   EXR_OK. Failure clears outputs. */
EXR_API exr_status exr_font_manager_chain(const exr_font_manager *manager, const char *family,
                                          unsigned style, exr_font_chain_link **out,
                                          size_t *count, exr_error *error);

typedef struct {
  size_t struct_size; /* Initialize to sizeof(exr_font_pick_result). */
  size_t face;        /* Manager face index, SIZE_MAX when nothing covers the scalar. */
  unsigned step;      /* EXR_FONT_STEP_*; EXR_FONT_STEP_NONE with face SIZE_MAX. */
  size_t chain_position; /* Position in exr_font_manager_chain(), SIZE_MAX when none. */
} exr_font_pick_result;
/* Best face able to render one scalar. A scalar no chain face covers is an
   observable EXR_OK result (face SIZE_MAX, step NONE), never a silent blank.
   EXR_ARGUMENT for NULL manager/out, bad struct_size or a non-scalar code point. */
EXR_API exr_status exr_font_manager_pick(const exr_font_manager *manager, const char *family,
                                         unsigned style, uint32_t codepoint,
                                         exr_font_pick_result *out, exr_error *error);

/* Loads the chain into a new exr_font (free with exr_font_free) for
   layout/shaping. Faces are read from disk now; a face whose file changed or
   vanished since indexing, or which would exceed the managed 256 MiB
   total, is left out. exr_font_create() retains its 128 MiB limit.
   *faces (optional, owned, exr_free) maps every
   exr_font face index -> manager face index, so exr_glyph.font_index identifies
   the manager face, and EXR_GLYPH_MISSING means no chain face covered it.
   EXR_FONT when no chain face could be loaded. Failure leaves outputs NULL/0. */
EXR_API exr_status exr_font_manager_create_font(const exr_font_manager *manager,
                                                const char *family, unsigned style,
                                                exr_font **out, size_t **faces,
                                                size_t *count, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
