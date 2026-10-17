/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXREADER_H
#define EXREADER_H
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#if defined(EXR_BUILD)
#define EXR_API __declspec(dllexport)
#else
#define EXR_API __declspec(dllimport)
#endif
#else
#define EXR_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define EXR_VERSION "0.89.0"
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
  EXR_CANCELLED
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
  EXR_PDF
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

/* Immutable host-defined audio timeline. No codec, URI scheme, UI or device is
   assumed. Track order defines concatenation; all timestamps are milliseconds. */
typedef struct exr_audio exr_audio;
typedef struct {
  const char *id,*uri,*media_type;
  uint64_t duration_ms;
} exr_audio_track;
typedef struct {
  const char *id,*title;
  size_t parent; /* SIZE_MAX root; otherwise an earlier containing chapter. */
  uint64_t start_ms,end_ms;
} exr_audio_chapter;
typedef struct {
  const char *part_id; /* Arbitrary host text-part or fixed-page ID. */
  size_t start,end; /* Host UTF-8 byte range, not validated against a document. */
  uint64_t start_ms,end_ms;
} exr_audio_sync;
typedef struct {
  size_t struct_size;
  const char *title;
  const exr_audio_track *tracks; size_t track_count;
  const exr_audio_chapter *chapters; size_t chapter_count;
  const exr_audio_sync *sync; size_t sync_count;
} exr_audio_input;
typedef struct { size_t track; uint64_t offset_ms; } exr_audio_position;
EXR_API exr_status exr_audio_create(const exr_audio_input *input,const exr_control *control,exr_audio **out,exr_error *error);
EXR_API void exr_audio_free(exr_audio *audio);
EXR_API const char *exr_audio_title(const exr_audio *audio);
EXR_API uint64_t exr_audio_duration(const exr_audio *audio);
EXR_API const exr_audio_track *exr_audio_tracks(const exr_audio *audio,size_t *count);
EXR_API const exr_audio_chapter *exr_audio_chapters(const exr_audio *audio,size_t *count);
EXR_API const exr_audio_sync *exr_audio_syncs(const exr_audio *audio,size_t *count);
EXR_API size_t exr_audio_memory_size(const exr_audio *audio);
/* Boundary timestamps choose the next track; total duration chooses final EOF. */
EXR_API exr_status exr_audio_locate(const exr_audio *audio,uint64_t time_ms,exr_audio_position *out,exr_error *error);
/* Enumerate matches in provider order by calling again with from=index+1.
   Misses return SIZE_MAX. Sync intervals are half-open and may overlap. */
EXR_API exr_status exr_audio_sync_at(const exr_audio *audio,uint64_t time_ms,size_t from,const exr_control *control,size_t *index,exr_error *error);
EXR_API exr_status exr_audio_sync_text(const exr_audio *audio,const char *part_id,size_t start,size_t end,size_t from,
                                        const exr_control *control,size_t *index,exr_error *error);

EXR_API exr_status exr_audio_time(const exr_audio *audio,size_t track,uint64_t offset_ms,uint64_t *time_ms,exr_error *error);
typedef struct exr_audio_player exr_audio_player;
typedef enum { EXR_AUDIO_LOAD,EXR_AUDIO_PLAY,EXR_AUDIO_PAUSE,EXR_AUDIO_SEEK,EXR_AUDIO_RATE,EXR_AUDIO_CLOSE } exr_audio_command_kind;
typedef struct {
  exr_audio_command_kind kind;
  size_t track;
  const exr_audio_track *source; /* Borrowed for callback duration. LOAD opens paused. */
  uint64_t offset_ms,generation;
  double rate;
} exr_audio_command;
typedef exr_status (*exr_audio_command_fn)(void *context,const exr_audio_command *command,exr_error *error);
typedef struct {
  size_t struct_size;
  exr_audio_command_fn command;
  void *context;
  void (*release)(void *context);
} exr_audio_backend;
typedef struct {
  uint64_t time_ms,generation;
  exr_audio_position position;
  const char *track_id; /* Borrowed until player_free. */
  double rate;
  int playing,needs_reload;
} exr_audio_playback;
/* Retains audio. Backend context ownership transfers only on success. */
EXR_API exr_status exr_audio_player_create(exr_audio *audio,const exr_audio_backend *backend,exr_audio_player **out,exr_error *error);
EXR_API void exr_audio_player_free(exr_audio_player *player);
EXR_API exr_status exr_audio_player_get(const exr_audio_player *player,exr_audio_playback *out,exr_error *error);
EXR_API exr_status exr_audio_player_play(exr_audio_player *player,exr_error *error);
EXR_API exr_status exr_audio_player_pause(exr_audio_player *player,exr_error *error);
EXR_API exr_status exr_audio_player_seek(exr_audio_player *player,uint64_t time_ms,exr_error *error);
EXR_API exr_status exr_audio_player_rate(exr_audio_player *player,double rate,exr_error *error);
/* Restores paused by stable track ID, so inserting earlier tracks is harmless. */
EXR_API exr_status exr_audio_player_restore(exr_audio_player *player,const char *track_id,uint64_t offset_ms,double rate,exr_error *error);
/* Reports actual backend progress; stale generations and backwards reports are
   rejected. A matching ended report advances tracks or finishes playback. */
EXR_API exr_status exr_audio_player_report(exr_audio_player *player,uint64_t generation,size_t track,uint64_t offset_ms,int ended,exr_error *error);

typedef enum {
  EXR_DIRECTION_AUTO = 0, EXR_DIRECTION_LTR = 1, EXR_DIRECTION_RTL = 2
} exr_direction;
typedef struct exr_bidi exr_bidi;
typedef struct {
  size_t start, end;
  uint32_t codepoint;
  unsigned level; /* UINT_MAX for X9-removed controls. */
} exr_bidi_scalar;
#define EXR_TAG(a, b, c, d) (((uint32_t)(a) << 24) | ((uint32_t)(b) << 16) | \
                           ((uint32_t)(c) << 8) | (uint32_t)(d))
typedef struct { uint32_t tag, value; } exr_shape_feature;
typedef struct {
  float font_size;
  unsigned style_flags;
  exr_direction direction;
  uint32_t script, language; /* OpenType tags; zero selects automatic script/default language. */
  const exr_shape_feature *features;
  size_t feature_count;
  uint32_t context_before, context_after; /* Nearest nontransparent adjacent scalar, 0 at boundary. */
  exr_control control;
} exr_shape_options;
typedef struct {
  size_t start, end; /* UTF-8 cluster range; shared by ligatures and attached marks. */
  uint32_t glyph;
  float advance_x, advance_y, offset_x, offset_y; /* Pixels; x right, y up. */
  unsigned flags;
} exr_shaped_glyph;
typedef struct {
  size_t start, end;
  unsigned heading;
} exr_block;
/* Indices and ranges use SIZE_MAX for absent/unprojected values. */
typedef enum {
  EXR_NODE_DOCUMENT = 1,
  EXR_NODE_CHAPTER,
  EXR_NODE_ELEMENT,
  EXR_NODE_TEXT,
  EXR_NODE_SECTION,
  EXR_NODE_PARAGRAPH,
  EXR_NODE_HEADING,
  EXR_NODE_LIST,
  EXR_NODE_LIST_ITEM,
  EXR_NODE_LINK,
  EXR_NODE_IMAGE,
  EXR_NODE_TABLE,
  EXR_NODE_ROW,
  EXR_NODE_CELL,
  EXR_NODE_BREAK,
  EXR_NODE_NOTE
} exr_node_kind;
typedef struct {
  const char *name, *value;
} exr_attribute;
typedef struct {
  exr_node_kind kind;
  size_t parent, first_child, next_sibling, chapter;
  size_t start, end;       /* Range in exr_document_text(), not source bytes. */
  const char *name, *text; /* XML expanded name; decoded, uncollapsed text. */
  const exr_attribute *attributes;
  size_t attribute_count;
} exr_node;
typedef struct {
  const char *id, *path;
  size_t root, resource;
  int in_spine, linear;
} exr_chapter;
typedef struct {
  const char *id, *path, *media_type, *properties;
} exr_resource;

/* Construction inputs: node indices refer to this input's preorder node array.
   Node 0 is DOCUMENT; each direct child is a CHAPTER listed exactly once below.
   The engine computes children, siblings, chapter membership and UTF-8 ranges. */
typedef struct {
  exr_node_kind kind;
  size_t parent;           /* SIZE_MAX for node 0; otherwise an earlier ancestor. */
  const char *name, *text; /* text is required only for TEXT nodes. */
  const exr_attribute *attributes;
  size_t attribute_count;
} exr_node_input;

typedef struct {
  const char *id, *path; /* path is a canonical, relative virtual path. */
  size_t root;
  int in_reading_order; /* Zero keeps an auxiliary chapter accessible by links. */
} exr_chapter_input;

typedef struct {
  exr_resource info;
  const void *data; /* NULL/0 declares metadata without encoded bytes. */
  size_t size;
} exr_resource_input;

typedef struct {
  const char *title;
  const exr_node_input *nodes;
  size_t node_count;
  const exr_chapter_input *chapters;
  size_t chapter_count;
  const exr_resource_input *resources;
  size_t resource_count;
} exr_document_input;

/* Portable text selectors. Offsets are UTF-8 bytes in normalized document text;
   exact/prefix/suffix/chapter are owned strings from create(), or host inputs.
   NULL exact denotes a legacy offset-only anchor. chapter is an optional path scope. */
typedef struct {
  size_t start, end;
  char *exact, *prefix, *suffix, *chapter;
} exr_anchor;
typedef enum {
  EXR_ANCHOR_MISSING = 0,
  EXR_ANCHOR_FOUND,
  EXR_ANCHOR_AMBIGUOUS,
  EXR_ANCHOR_LEGACY
} exr_anchor_state;
typedef struct {
  exr_anchor_state state;
  size_t start, end; /* SIZE_MAX unless FOUND. */
} exr_anchor_match;

/* A part may be a chapter, page, or a host-defined independently laid-out unit.
   Identifiers and paths are stable metadata, not whole-book text offsets. */
typedef struct {
  const char *id, *path, *title;
  int in_reading_order;
} exr_part;
/* A successful loader transfers an independent document to the engine. */
typedef exr_status (*exr_part_load_fn)(void *context, size_t part, exr_document **out,
                                       exr_error *error);
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
/* Native RIFF/WAVE random PCM decoding; source ownership transfers on success. */
typedef struct exr_wave exr_wave;
typedef struct {
  uint32_t sample_rate,channels,bits_per_sample,valid_bits,channel_mask;
  uint64_t frames;
  int floating;
} exr_wave_info;
EXR_API exr_status exr_wave_open(const char *path,const exr_control *control,exr_wave **out,exr_error *error);
EXR_API exr_status exr_wave_open_source(const exr_source *source,exr_wave **out,exr_error *error);
EXR_API void exr_wave_free(exr_wave *wave);
EXR_API const exr_wave_info *exr_wave_format(const exr_wave *wave);
/* Interleaved float output, caller capacity >= frames*channels. At most 65536
   frames per call. Runtime error/cancellation zeros output and returns read=0. */
EXR_API exr_status exr_wave_read(exr_wave *wave,uint64_t first_frame,size_t frames,float *output,size_t *read,
                                  const exr_control *control,exr_error *error);
/* Flat navigation tree. Parent must precede its child; SIZE_MAX denotes a root
   or unresolved/ambiguous part. href is relative to base; arbitrary role labels
   permit host-defined navigation categories (e.g. toc, page-list, landmarks). */
typedef struct {
  size_t parent, part;
  const char *label, *href, *base, *role;
} exr_navigation;
typedef struct {
  const char *title;
  const exr_part *parts;
  size_t part_count;
  exr_part_load_fn load;
  void *context;
  exr_context_release_fn release;
  const exr_navigation *navigation;
  size_t navigation_count;
} exr_publication_input;
enum {
  EXR_BOUNDARY_GRAPHEME = 1,
  EXR_BOUNDARY_LINE = 2,
  EXR_BOUNDARY_MANDATORY = 4,
  EXR_BOUNDARY_GLUE = 8 /* No emergency wrapping at this boundary. */
};
enum {
  EXR_GLYPH_BOLD = 1, EXR_GLYPH_ITALIC = 2, EXR_GLYPH_HIDDEN = 4,
  EXR_GLYPH_MISSING = 8, /* No supplied face covers this visible scalar; glyph 0 is used. */
  EXR_GLYPH_SHAPED = 16, /* Advances/offsets include OpenType positioning. */
  EXR_GLYPH_UNDERLINE = 32, EXR_GLYPH_STRIKE = 64
};

typedef struct {
  const void *data; /* Encoded font bytes, copied during create(). */
  size_t size;
  unsigned face_index; /* Face within a font collection, otherwise zero. */
} exr_font_input;
typedef struct {
  size_t start, end;
  uint32_t codepoint, glyph;
  float x, baseline, advance, size;
  size_t page;
  size_t node;
  uint32_t color; /* 0xRRGGBBAA */
  unsigned flags; /* EXR_GLYPH_*; HIDDEN glyphs must not be drawn. */
  float clip_left, clip_right;
  float line_height;
  size_t cluster_start, cluster_end; /* Source UTF-8 range of this grapheme group. */
  unsigned boundaries; /* Source EXR_BOUNDARY_*; zero after the first shaped glyph in a cluster. */
  size_t font_index; /* Index in the ordered exr_font input list; glyph is face-local. */
  float offset_x, offset_y; /* Shaped glyph offset; y up relative to baseline. */
  unsigned bidi_level; /* Resolved Unicode embedding level; odd means RTL. */
} exr_glyph;
typedef struct {
  size_t start, end, glyph_start, glyph_count;
  float y;
  size_t page;
  float x, width, height;
} exr_line;
typedef struct {
  size_t start, end, line_start, line_count;
  size_t box_start, box_count;
} exr_page;
typedef enum { EXR_BOX_BLOCK = 1, EXR_BOX_IMAGE, EXR_BOX_CELL } exr_box_kind;
typedef struct {
  exr_box_kind kind;
  size_t node, page, resource, start, end;
  float x, y, width, height, border_width;
  uint32_t background, border_color; /* 0xRRGGBBAA */
  unsigned flags;                    /* Image bit 1: missing/unsupported image placeholder. */
} exr_box;
typedef enum { EXR_PAINT_GLYPH=1, EXR_PAINT_BOX=2 } exr_paint_kind;
typedef struct {
  exr_paint_kind kind;
  unsigned flags; /* Reserved; initialize to zero. */
  size_t index;   /* Index in the positioned glyph or box array. */
} exr_paint;
typedef struct {
  float width,height; /* Native coordinates: origin top left, y down. */
  exr_page content;
  size_t paint_start,paint_count;
} exr_positioned_page;
typedef struct {
  size_t struct_size; /* Set to sizeof(exr_positioned_input); zero-initialize all fields. */
  const exr_positioned_page *pages;
  size_t page_count;
  const exr_glyph *glyphs;
  size_t glyph_count;
  const exr_line *lines;
  size_t line_count;
  const exr_box *boxes;
  size_t box_count;
  const exr_paint *paints;
  size_t paint_count;
} exr_positioned_input;
typedef struct {
  float width, height, margin, font_size, line_height, paragraph_spacing;
} exr_layout_options;
typedef struct exr_bitmap exr_bitmap;
typedef exr_status (*exr_image_decode_fn)(void *context, const exr_resource *resource,
                                          const void *encoded, size_t size, exr_bitmap *rgba,
                                          exr_error *error);
typedef void (*exr_image_release_fn)(void *context, exr_bitmap *rgba);
typedef struct {
  exr_layout_options page;
  const char *user_css; /* Optional UTF-8 override stylesheet; borrowed for the create call. */
  int document_css;     /* Nonzero enables book stylesheets and inline styles. */
  exr_image_decode_fn decode_image;   /* Optional host decoder, returns RGBA. */
  exr_image_release_fn release_image; /* Required with decode_image; also called on failure. */
  void *image_context;
  exr_direction direction; /* Paragraph base direction; AUTO uses first strong scalar. */
  int embedded_fonts; /* Load used local @font-face resources; defaults to enabled. */
  exr_control control; /* Layout creation / pager work; context must outlive that work. */
} exr_layout_config;
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
typedef struct { double x,y; } exr_path_point;
typedef enum { EXR_PATH_MOVE,EXR_PATH_LINE,EXR_PATH_QUAD,EXR_PATH_CUBIC,EXR_PATH_CLOSE } exr_path_verb;
typedef struct { exr_path_verb verb; exr_path_point points[3]; } exr_path_segment;
typedef enum { EXR_FILL_NONZERO,EXR_FILL_EVENODD } exr_fill_rule;
typedef enum { EXR_CAP_BUTT,EXR_CAP_ROUND,EXR_CAP_SQUARE } exr_line_cap;
typedef enum { EXR_JOIN_MITER,EXR_JOIN_ROUND,EXR_JOIN_BEVEL } exr_line_join;
typedef struct { double width,miter_limit; exr_line_cap cap; exr_line_join join; } exr_path_stroke;
enum { EXR_MASK_GRAY=1,EXR_MASK_ALPHA=2 };
typedef struct exr_image_layer {
  exr_bitmap bitmap;
  struct exr_image_layer *mask;
  unsigned interpolate,mask_mode,has_matte; /* mask_mode: 1 gray*alpha, 2 alpha */
  double matte[3]; /* Optional normalized RGB preblend color to remove. */
} exr_image_layer;
enum { EXR_DRAW_FILL=1,EXR_DRAW_STROKE=2 };
typedef struct {
  uint32_t fill,stroke; /* 0xRRGGBBAA */
  unsigned flags;
  exr_fill_rule rule;
  exr_path_stroke line;
  const double *dashes; size_t dash_count; double dash_phase;
  /* Coordinates defining stroke widths/dashes. NULL uses the path matrix.
     Identity here gives a non-scaling stroke for a transformed path. */
  const double *stroke_matrix;
} exr_draw_style;
typedef struct exr_canvas exr_canvas;
typedef struct {
  uint32_t width,height,channels,background; /* channels 0 -> RGBA */
  size_t mask_budget; /* zero -> 64 MiB */
  exr_control control; /* Context must remain valid until canvas_free. */
} exr_canvas_config;
EXR_API exr_draw_style exr_draw_style_defaults(void);
/* Immediate drawing, independent of document format, fonts and UI. Path/image
   inputs are borrowed only for a call. A failed draw poisons the canvas; take
   then returns that failure instead of exposing partial output. */
EXR_API exr_status exr_canvas_create(const exr_canvas_config *config,exr_canvas **out,exr_error *error);
EXR_API void exr_canvas_free(exr_canvas *canvas);
EXR_API size_t exr_canvas_memory_size(const exr_canvas *canvas);
EXR_API const exr_bitmap *exr_canvas_bitmap(const exr_canvas *canvas);
EXR_API exr_status exr_canvas_take(exr_canvas *canvas,exr_bitmap *out,exr_error *error);
/* Save/restore the clipping region; paint styles are supplied per draw. */
EXR_API exr_status exr_canvas_save(exr_canvas *canvas,exr_error *error);
EXR_API exr_status exr_canvas_restore(exr_canvas *canvas,exr_error *error);
EXR_API exr_status exr_canvas_path(exr_canvas *canvas,const exr_path_segment *segments,size_t count,
                                    const double matrix[6],const exr_draw_style *style,exr_error *error);
EXR_API exr_status exr_canvas_clip(exr_canvas *canvas,const exr_path_segment *segments,size_t count,
                                    const double matrix[6],exr_fill_rule rule,exr_error *error);
EXR_API exr_status exr_canvas_image(exr_canvas *canvas,const exr_image_layer *image,const double matrix[6],
                                     double alpha,exr_error *error);
typedef enum { EXR_DRAW_SAVE,EXR_DRAW_RESTORE,EXR_DRAW_BEGIN_CLIP,EXR_DRAW_END_CLIP } exr_draw_state;
typedef exr_status (*exr_draw_path_fn)(void *context,const exr_path_segment *segments,size_t count,
                                        const double matrix[6],const exr_draw_style *style,exr_error *error);
typedef exr_status (*exr_draw_image_fn)(void *context,const exr_image_layer *image,const double matrix[6],
                                         double alpha,exr_error *error);
typedef exr_status (*exr_draw_clip_fn)(void *context,const exr_path_segment *segments,size_t count,
                                        const double matrix[6],exr_fill_rule rule,unsigned accumulate,exr_error *error);
typedef exr_status (*exr_draw_state_fn)(void *context,exr_draw_state state,exr_error *error);
/* A streaming drawing consumer. All callback inputs are borrowed for that
   callback. Absent callbacks are skipped for inspection-only consumers.
   Clip accumulate=0 intersects now; accumulate=1 adds to the union applied at
   END_CLIP. BEGIN_CLIP discards an unfinished union; an empty union is a no-op. */
typedef struct {
  exr_draw_path_fn path;
  exr_draw_image_fn image;
  exr_draw_clip_fn clip;
  exr_draw_state_fn state;
  void *context;
} exr_draw_sink;
/* The returned sink borrows the canvas until canvas_free. */
EXR_API exr_status exr_canvas_get_sink(exr_canvas *canvas,exr_draw_sink *out,exr_error *error);
typedef struct exr_fixed_document exr_fixed_document;
typedef struct exr_fixed_text exr_fixed_text;
enum { EXR_REGION_VERTICAL=1,EXR_REGION_INVISIBLE=2 };
typedef struct {
  size_t start,end; /* UTF-8 byte range; multiple regions may share a range. */
  double quad[8];  /* Four ordered corners in native page coordinates. */
  unsigned flags;
} exr_text_region;
/* Copies length-delimited UTF-8 and independent text quads, without imposing
   visual/reading order or one-glyph-per-character assumptions. */
EXR_API exr_status exr_fixed_text_create(const char *utf8,size_t size,const exr_text_region *regions,size_t count,
                                          const exr_control *control,exr_fixed_text **out,exr_error *error);
EXR_API void exr_fixed_text_free(exr_fixed_text *text);
EXR_API const char *exr_fixed_text_string(const exr_fixed_text *text,size_t *size);
EXR_API const exr_text_region *exr_fixed_text_regions(const exr_fixed_text *text,size_t *count);
EXR_API size_t exr_fixed_text_memory_size(const exr_fixed_text *text);
/* Exact, case-sensitive UTF-8 byte search, including embedded NUL. A miss sets
   start/end to SIZE_MAX. Queries are limited to 1 MiB; from rounds forward to UTF-8. */
EXR_API exr_status exr_fixed_text_find(const exr_fixed_text *text,const char *query,size_t query_size,size_t from,
                                        const exr_control *control,size_t *start,size_t *end,exr_error *error);
/* Copies whole overlapping regions in provider order; no ligature subdivision.
   UTF-8 range boundaries are required. Free returned regions with exr_free(). */
EXR_API exr_status exr_fixed_text_select(const exr_fixed_text *text,size_t start,size_t end,const exr_control *control,
                                          exr_text_region **regions,size_t *count,exr_error *error);
/* Nearest source-space quad within max_distance. Equal distances keep the first
   provider region. A miss returns SIZE_MAX; exclude_flags filters region flags. */
EXR_API exr_status exr_fixed_text_hit(const exr_fixed_text *text,double x,double y,double max_distance,unsigned exclude_flags,
                                       const exr_control *control,size_t *region,exr_error *error);

/* Owned from create, or explicit host inputs. Selector byte lengths preserve NUL;
   page_id is a nonempty UTF-8 string. Old offsets never override ambiguity. */
typedef struct {
  size_t start,end;
  char *page_id,*exact,*prefix,*suffix;
  size_t exact_size,prefix_size,suffix_size;
} exr_fixed_anchor;
EXR_API exr_status exr_fixed_anchor_create(const char *page_id,const exr_fixed_text *text,size_t start,size_t end,
                                            exr_fixed_anchor *out,exr_error *error);
EXR_API void exr_fixed_anchor_free(exr_fixed_anchor *anchor);
EXR_API exr_status exr_fixed_anchor_resolve(const char *page_id,const exr_fixed_text *text,const exr_fixed_anchor *anchor,
                                             const exr_control *control,exr_anchor_match *match,exr_error *error);

typedef struct {
  const char *id,*label;
  exr_page_geometry geometry;
} exr_fixed_page;
typedef exr_status (*exr_fixed_draw_fn)(void *context,size_t page,const double matrix[6],
                                         const exr_draw_sink *sink,const exr_control *control,exr_error *error);
typedef exr_status (*exr_fixed_text_fn)(void *context,size_t page,const exr_control *control,
                                         exr_fixed_text **out,exr_error *error);
typedef struct {
  size_t struct_size;
  const char *title;
  const exr_fixed_page *pages; size_t page_count;
  exr_fixed_draw_fn draw;
  void *context;
  exr_context_release_fn release;
  exr_fixed_text_fn text; /* Optional; appended after the original required prefix. */
} exr_fixed_input;
typedef struct {
  uint32_t channels,background; /* channels 0 -> RGBA */
  size_t mask_budget;
  exr_control control;
} exr_fixed_render_options;
/* Metadata is copied. Provider context ownership transfers only on success.
   Empty IDs become page-1, page-2, ...; effective IDs must be unique. */
EXR_API exr_status exr_fixed_create(const exr_fixed_input *input,exr_fixed_document **out,exr_error *error);
EXR_API void exr_fixed_free(exr_fixed_document *document);
EXR_API const char *exr_fixed_title(const exr_fixed_document *document);
EXR_API const exr_fixed_page *exr_fixed_pages(const exr_fixed_document *document,size_t *count);
/* Owned directory/metadata bytes, excluding the provider's own payload. */
EXR_API size_t exr_fixed_memory_size(const exr_fixed_document *document);
/* Loads an independent owned text snapshot only when requested. The same
   nonconcurrent/nonreentrant provider rule as draw applies. */
EXR_API exr_status exr_fixed_load_text(exr_fixed_document *document,size_t page,const exr_control *control,
                                        exr_fixed_text **out,exr_error *error);
/* Streams one page in source coordinates through matrix (NULL -> identity).
   No implicit clip/state changes. The provider must skip absent callbacks.
   One document cannot be drawn concurrently or reentered from a callback. */
EXR_API exr_status exr_fixed_draw(exr_fixed_document *document,size_t page,const double matrix[6],
                                   const exr_draw_sink *sink,const exr_control *control,exr_error *error);
/* Creates a natural-size viewport, clips to it, then paints just this page.
   NULL options default to white RGBA. Failure returns no partial bitmap. */
EXR_API exr_status exr_fixed_render(exr_fixed_document *document,size_t page,double scale,
                                     const exr_fixed_render_options *options,exr_bitmap *out,exr_error *error);
typedef struct {
  size_t struct_size;
  exr_font *fallback_font; /* Optional ordered font set, retained until fixed_free. */
  exr_control control; /* Used only while opening. */
} exr_fixed_open_options;
/* Built-in fixed-format readers (currently PDF). Memory input is copied;
   file input uses UTF-8 paths. No system font lookup or eager page painting. */
EXR_API exr_status exr_fixed_open_memory(exr_format format,const void *data,size_t size,
                                          const exr_fixed_open_options *options,
                                          exr_fixed_document **out,exr_error *error);
EXR_API exr_status exr_fixed_open(const char *path,const exr_fixed_open_options *options,
                                   exr_fixed_document **out,exr_error *error);
/* All input/output strings are UTF-8. Returned views belong to their owner. */
EXR_API const char *exr_version(void);
/* Unicode 17 extended grapheme boundaries plus documented line-break rules.
   Allocates size+1 bytes indexed by UTF-8 byte offset, freed with exr_free().
   Non-boundary/continuation bytes are zero; end is GRAPHEME|LINE|MANDATORY.
   Text must be valid UTF-8, at most 64 MiB. Embedded U+0000 is a control scalar. */
EXR_API exr_status exr_text_analyze(const char *text, size_t size, unsigned char **boundaries,
                                    exr_error *error);
/* Unicode 17 UAX #9 paragraph analysis, at most 4M scalars. Scalar views are borrowed.
   Reorder accepts scalar-index line slices and returns visual indices into this view,
   excluding X9 controls. Free the returned order with exr_free(). */
EXR_API exr_status exr_bidi_analyze(const char *text, size_t size, exr_direction direction,
                                    exr_bidi **out, exr_error *error);
EXR_API const exr_bidi_scalar *exr_bidi_scalars(const exr_bidi *bidi, size_t *count);
EXR_API exr_status exr_bidi_reorder(const exr_bidi *bidi, size_t first, size_t count,
                                    size_t **out_order, size_t *out_count, exr_error *error);
EXR_API void exr_bidi_free(exr_bidi *bidi);
/* Copies every input string/attribute/blob during this call. Failure leaves *out NULL. */
EXR_API exr_status exr_document_create(const exr_document_input *input, exr_document **out,
                                       exr_error *error);
EXR_API exr_status exr_document_open(const char *path, exr_document **out, exr_error *error);
EXR_API exr_status exr_document_open_memory(exr_format format, const void *data, size_t size,
                                            exr_document **out, exr_error *error);
EXR_API void exr_document_free(exr_document *doc);
/* Owned allocation payload, excluding shared source archives and allocator overhead. */
EXR_API size_t exr_document_memory_size(const exr_document *doc);
EXR_API const char *exr_document_text(const exr_document *doc, size_t *size);
EXR_API const char *exr_document_title(const exr_document *doc);
/* Borrowed effective font set used by this layout, valid until layout_free.
   Includes book fonts. Glyph font_index indexes this set; do not free this view. */
EXR_API exr_font *exr_layout_font(const exr_layout *layout);
/* Borrowed encoded font bytes for a host renderer; valid while font is alive. */
EXR_API exr_status exr_font_source(const exr_font *font, size_t index, exr_font_input *source,
                                   exr_error *error);
EXR_API const exr_block *exr_document_blocks(const exr_document *doc, size_t *count);
EXR_API const exr_node *exr_document_nodes(const exr_document *doc, size_t *count);
EXR_API const exr_chapter *exr_document_chapters(const exr_document *doc, size_t *count);
EXR_API const exr_resource *exr_document_resources(const exr_document *doc, size_t *count);
/* Owned navigation snapshot; valid after document_free. Release with navigation_free.
   Returns authored nav/NCX resources, or an empty array when none are present. */
EXR_API exr_status exr_document_navigation(const exr_document *doc, exr_navigation **entries,
                                            size_t *count, exr_error *error);
EXR_API void exr_navigation_free(exr_navigation *entries, size_t count);
/* Borrowed views last until document_free. Attribute names use URI|local for namespaces. */
EXR_API const char *exr_node_attribute(const exr_node *node, const char *name);
/* Copies an embedded resource; free the returned bytes with exr_free(). No network access. */
EXR_API exr_status exr_document_resource(const exr_document *doc, size_t resource, void **data,
                                         size_t *size, exr_error *error);
/* Resolve a local chapter-relative URI to a resource and, if parsed, a node.
   Missing targets return EXR_OK with SIZE_MAX; external/unsafe URIs return EXR_ARGUMENT. */
EXR_API exr_status exr_document_resolve(const exr_document *doc, size_t chapter, const char *uri,
                                        size_t *resource, size_t *node, exr_error *error);
EXR_API exr_format exr_document_format(const exr_document *doc);
EXR_API exr_status exr_document_find(const exr_document *doc, const char *query, size_t from,
                                     size_t *start, size_t *end, exr_error *error);
/* Capture up to 64 KiB of selected text and 32 Unicode scalars of context per side.
   Empty ranges capture point bookmarks. Output must be empty; failure clears it. */
EXR_API exr_status exr_anchor_create(const exr_document *doc, size_t start, size_t end,
                                     exr_anchor *out, exr_error *error);
EXR_API void exr_anchor_free(exr_anchor *anchor);
/* Read-only resolution; never falls back to the nearest old offset. EXR_OK may
   report MISSING/AMBIGUOUS/LEGACY; only FOUND supplies a usable range. */
EXR_API exr_status exr_anchor_resolve(const exr_document *doc, const exr_anchor *anchor,
                                      exr_anchor_match *match, exr_error *error);
/* DOM location for a chapter-local EPUB CFI path component. TEXT offsets count
   UTF-16 code units in raw, uncollapsed node text (including surrogate interiors).
   Element offset=SIZE_MAX denotes the element; other offsets are child-node
   boundaries. side: 0 unspecified, 1 before, 2 after. No normalized text offsets. */
typedef struct { size_t node,offset; unsigned side; } exr_cfi_point;
/* These APIs produce/consume the content-document component, e.g. /4/2[id]/1:3,
   not the package spine prefix or epubcfi(...) wrapper. chapter must have one
   XML document element. Owned path uses exr_free; failure clears output. */
EXR_API exr_status exr_document_cfi_path_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point,
                                                const exr_control *control,char **path,exr_error *error);
EXR_API exr_status exr_document_cfi_path_resolve(const exr_document *doc,size_t chapter,const char *path,
                                                 const exr_control *control,exr_cfi_point *point,exr_error *error);
/* Full point CFI through the original package spine. Requires a complete EPUB
   document retaining its archive; auxiliary non-spine chapters are rejected.
   Raw epubcfi(...) strings only; no URI percent decoding. Range input resolves
   to its start; use range_resolve to validate/obtain both ends. Failure clears output. */
EXR_API exr_status exr_document_cfi_create(const exr_document *doc,size_t chapter,const exr_cfi_point *point,
                                           const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_document_cfi_resolve(const exr_document *doc,const char *cfi,const exr_control *control,
                                            size_t *chapter,exr_cfi_point *point,exr_error *error);
/* EPUB CFI simple range across one or more spine chapters. Endpoint side bias
   must be unspecified; the standard implies after-start/before-end attachment. */
typedef struct { size_t start_chapter,end_chapter; exr_cfi_point start,end; } exr_cfi_range;
EXR_API exr_status exr_document_cfi_range_create(const exr_document *doc,const exr_cfi_range *range,
                                                 const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_document_cfi_range_resolve(const exr_document *doc,const char *cfi,const exr_control *control,
                                                  exr_cfi_range *range,exr_error *error);
/* Structure-preserving EPUB: serializes the tree and copies all declared resources.
   Chapter paths, attributes and resource bytes are retained. Missing resources,
   non-XML names and conflicting/reserved paths fail atomically. No network access.
   The legacy export() below remains a text-only conversion. */
EXR_API exr_status exr_document_export_epub(const exr_document *doc, const exr_control *control,
                                            void **data, size_t *size, exr_error *error);
/* Structure-preserving HTML directory in a ZIP, with a collision-free XHTML
   entrypoint/reading order. Retains chapter/asset paths, styles, fonts and links.
   Extract together before opening entry_path. Both allocations are owned;
   release data and entry_path with exr_free. Failure clears every output. */
EXR_API exr_status exr_document_export_html_bundle(const exr_document *doc,const exr_control *control,
                                                   void **data,size_t *size,char **entry_path,exr_error *error);
EXR_API exr_status exr_document_export(const exr_document *doc, exr_format format, void **data,
                                       size_t *size, exr_error *error);
/* Metadata is copied. On success, release (if provided) runs once after the last
   publication/session reference is freed. Without release, keep context alive.
   Callbacks must not destroy/reenter the active publication or session. */
EXR_API exr_status exr_publication_create(const exr_publication_input *input,
                                          exr_publication **out, exr_error *error);
/* Built-in indexed loading currently accepts EPUB. No XHTML is parsed at open. */
EXR_API exr_status exr_publication_open(const char *path, exr_publication **out,
                                        exr_error *error);
EXR_API exr_status exr_publication_open_source(const exr_source *source,
                                               exr_publication **out, exr_error *error);
EXR_API exr_status exr_publication_open_memory(exr_format format, const void *data, size_t size,
                                               exr_publication **out, exr_error *error);
EXR_API void exr_publication_free(exr_publication *publication);
EXR_API const char *exr_publication_title(const exr_publication *publication);
EXR_API const exr_part *exr_publication_parts(const exr_publication *publication, size_t *count);
/* Borrowed until publication_free; EPUB navigation is decoded on first request.
   Custom publications copy navigation through exr_publication_input. */
EXR_API exr_status exr_publication_navigation(exr_publication *publication,
                                               const exr_navigation **entries, size_t *count,
                                               exr_error *error);
/* Own the returned document with document_free(); offsets/indices are part-local. */
EXR_API exr_status exr_publication_load(exr_publication *publication, size_t part,
                                        exr_document **out, exr_error *error);
/* Full point CFI for the built-in indexed EPUB provider. Create accepts a
   single-chapter snapshot from this publication, with snapshot-local node IDs.
   Resolve parses only the addressed chapter and returns an independent owned
   document (document_free), plus a point local to it. Auxiliary parts fail. */
EXR_API exr_status exr_publication_cfi_create(exr_publication *publication,size_t part,const exr_document *document,
                                              const exr_cfi_point *point,const exr_control *control,char **cfi,exr_error *error);
EXR_API exr_status exr_publication_cfi_resolve(exr_publication *publication,const char *cfi,const exr_control *control,
                                               size_t *part,exr_document **document,exr_cfi_point *point,exr_error *error);
EXR_API exr_status exr_font_open(const char *path, exr_font **out, exr_error *error);
/* Immutable ordered fallback list, 1..32 scalable Unicode faces, at most 128 MiB
   of copied font bytes in total. Failure leaves *out NULL. No system font lookup. */
EXR_API exr_status exr_font_create(const exr_font_input *inputs, size_t count,
                                   exr_font **out, exr_error *error);
/* Also accepts scalable faces without Unicode charmaps, for direct glyph IDs.
   Such faces do not participate in Unicode character lookup. Inputs are copied. */
EXR_API exr_status exr_font_create_glyphs(const exr_font_input *inputs, size_t count,
                                          exr_font **out, exr_error *error);
EXR_API size_t exr_font_count(const exr_font *font);
/* Scalar cmap coverage, not a shaping/sequence support test; invalid input returns 0. */
EXR_API int exr_font_has_glyph(const exr_font *font, size_t font_index, uint32_t codepoint);
EXR_API void exr_font_free(exr_font *font);
/* Owned unhinted Bézier path in 1000-em units, origin on the baseline, y up.
   Direct glyph IDs also work without a Unicode cmap. Free segments with
   exr_free(); the path outlives its font. Same font concurrency rule as shape. */
EXR_API exr_status exr_font_glyph_outline(exr_font *font,size_t font_index,uint32_t glyph,
                                           exr_path_segment **out,size_t *count,
                                           const exr_control *control,exr_error *error);
EXR_API exr_shape_options exr_shape_defaults(void);
/* One font face, logical output order; caller splits directional/script/font runs.
   Own the returned glyph array with exr_free(). Failure clears output/count.
   The font must not be used concurrently with layout, shape or rendering calls. */
EXR_API exr_status exr_shape(exr_font *font, size_t font_index, const char *utf8, size_t size,
                             const exr_shape_options *options, exr_shaped_glyph **out,
                             size_t *out_count, exr_error *error);
EXR_API exr_layout_options exr_layout_defaults(void);
EXR_API exr_layout_config exr_layout_config_defaults(void);
EXR_API exr_status exr_layout_create(const exr_document *doc, exr_font *font,
                                     const exr_layout_options *options, exr_layout **out,
                                     exr_error *error);
EXR_API exr_status exr_layout_create_ex(const exr_document *doc, exr_font *font,
                                        const exr_layout_config *config, exr_layout **out,
                                        exr_error *error);
/* Copies pre-positioned arrays and fits each page inside the configured viewport.
   Glyph IDs/advances are supplied by the host; this path performs no shaping/reflow.
   Font may be NULL only for inputs with no glyphs. */
EXR_API exr_status exr_layout_create_positioned(const exr_document *doc, exr_font *font,
                                                const exr_positioned_input *input,
                                                const exr_layout_config *config,
                                                exr_layout **out, exr_error *error);
/* Resumable page layout. The document/font/callback context must outlive the pager.
   Config/CSS are copied. next() transfers one independent single-page layout,
   or returns EXR_OK with NULL at EOF. Pages share immutable images; serialize
   their lifetime changes with other pages from the same pager.
   After a next() error, recreate the pager. */
EXR_API exr_status exr_pager_create(const exr_document *doc, exr_font *font,
                                     const exr_layout_config *config, exr_pager **out,
                                     exr_error *error);
EXR_API exr_status exr_pager_next(exr_pager *pager, exr_layout **out, exr_error *error);
EXR_API exr_status exr_pager_set_control(exr_pager *pager, const exr_control *control,
                                         exr_error *error);
/* Alternative borrowed-page mode; cannot be mixed with next(). Cache defaults to
   one page/no byte limit. Evicted pages resume from a retained checkpoint when
   available, otherwise from the beginning.
   New oversize pages return EXR_LIMIT without evicting existing cached pages. */
EXR_API exr_status exr_pager_set_cache(exr_pager *pager, size_t capacity, size_t byte_budget,
                                       exr_error *error);
EXR_API exr_status exr_pager_get(exr_pager *pager, size_t page, const exr_layout **out,
                                 exr_error *error);
EXR_API size_t exr_pager_cached_count(const exr_pager *pager);
EXR_API size_t exr_pager_cached_bytes(const exr_pager *pager);
/* Bounded in-memory replay checkpoints, separate from the page payload cache.
   Defaults: 4 entries / 2 MiB / every 16 pages in get() mode. Capacity zero disables.
   Capacity <=64, nonzero budget/interval required when enabled; not serialized. */
EXR_API exr_status exr_pager_set_checkpoints(exr_pager *pager, size_t capacity,
                                             size_t byte_budget, size_t interval,
                                             exr_error *error);
typedef struct {
  size_t generated_pages, checkpoint_count, checkpoint_bytes, restored_checkpoints;
} exr_pager_stats;
EXR_API exr_pager_stats exr_pager_statistics(const exr_pager *pager);
/* Scanned UTF-8 source position, possibly ahead of the last page due to lookahead;
   this is progress information, not a serializable resume token. */
EXR_API size_t exr_pager_position(const exr_pager *pager);
EXR_API void exr_pager_free(exr_pager *pager);
/* Font and image callback context must outlive the session. Config/user CSS are
   copied; the publication is retained. Cache capacity is 1..64 resident parts. */
EXR_API exr_status exr_session_create(exr_publication *publication, exr_font *font,
                                      const exr_layout_config *config, size_t capacity,
                                      exr_session **out, exr_error *error);
/* Loads/layouts only this part. Borrowed views last until the next get/clear/free.
   Cache hits reuse layout; failure keeps existing cached entries. */
EXR_API exr_status exr_session_get(exr_session *session, size_t part,
                                   const exr_document **document, const exr_layout **layout,
                                   exr_error *error);
EXR_API size_t exr_session_cached(const exr_session *session);
/* Resident cache payload budget; zero is unlimited. Lowering evicts LRU entries.
   A new entry larger than the budget returns EXR_LIMIT and preserves the old cache.
   Shared sources, fonts, temporary loads and renderer bitmaps are outside this budget. */
EXR_API exr_status exr_session_set_budget(exr_session *session, size_t bytes, exr_error *error);
EXR_API size_t exr_session_cached_bytes(const exr_session *session);
EXR_API void exr_session_clear(exr_session *session);
EXR_API void exr_session_free(exr_session *session);
EXR_API void exr_layout_free(exr_layout *layout);
EXR_API size_t exr_layout_memory_size(const exr_layout *layout);
EXR_API const exr_page *exr_layout_pages(const exr_layout *layout, size_t *count);
EXR_API const exr_line *exr_layout_lines(const exr_layout *layout, size_t *count);
EXR_API const exr_glyph *exr_layout_glyphs(const exr_layout *layout, size_t *count);
EXR_API const exr_box *exr_layout_boxes(const exr_layout *layout, size_t *count);
/* Borrowed ordered paint commands for one positioned page; NULL for reflow layouts. */
EXR_API const exr_paint *exr_layout_paints(const exr_layout *layout, size_t page, size_t *count);
/* Borrowed decoded RGBA pixels, valid until layout_free; NULL for unavailable resources. */
EXR_API const exr_bitmap *exr_layout_image(const exr_layout *layout, size_t resource);
EXR_API size_t exr_layout_page_at(const exr_layout *layout, size_t utf8_offset);
EXR_API size_t exr_layout_hit_test(const exr_layout *layout, size_t page, float x, float y);
EXR_API exr_status exr_render_page(const exr_layout *layout, exr_font *font, size_t page,
                                   exr_bitmap *bitmap, exr_error *error);
/* Controlled rendering; channels must be 1 or 4. Cancellation clears bitmap. */
EXR_API exr_status exr_render_page_ex(const exr_layout *layout, exr_font *font, size_t page,
                                       unsigned channels, const exr_control *control,
                                       exr_bitmap *out, exr_error *error);
EXR_API exr_status exr_render_page_color(const exr_layout *layout, exr_font *font, size_t page,
                                         exr_bitmap *bitmap, exr_error *error);
/* Built-in PNG/JPEG decoder; owns its output pixels, freed with exr_bitmap_free(). */
EXR_API exr_status exr_image_decode(const void *data, size_t size, exr_bitmap *rgba,
                                    exr_error *error);
EXR_API exr_status exr_bitmap_write_png(const exr_bitmap *bitmap, const char *path,
                                        exr_error *error);
EXR_API void exr_bitmap_free(exr_bitmap *bitmap);
EXR_API exr_status exr_bitmap_write_bmp(const exr_bitmap *bitmap, const char *path,
                                        exr_error *error);
/* SQLite owns the original bytes and covers; there is no filesystem sidecar. */
typedef struct {
  int64_t id;
  exr_format format;
  char *title, *author, *tags;
  int favorite, status;
  size_t position;
} exr_book;
typedef struct {
  int64_t id, book_id;
  size_t start, end;
  char *text;
  exr_anchor anchor; /* Owned in query results; zero-initialize input notes. */
} exr_note;
typedef struct {
  int64_t id,book_id;
  size_t page,start,end; /* Zero-based page; UTF-8 range within that page. */
  char *text;
  exr_fixed_anchor anchor; /* Query output; writes capture the stored source. */
} exr_fixed_note;
/* Host-chosen audio_id keys are independent of source URIs and book row IDs. */
typedef struct { char *track_id; uint64_t offset_ms; double rate; } exr_audio_checkpoint;
typedef struct { int64_t id; char *label; exr_audio_checkpoint position; } exr_audio_bookmark;
EXR_API void exr_audio_checkpoint_free(exr_audio_checkpoint *position);
EXR_API exr_status exr_library_audio_resume(exr_library *library,const char *audio_id,const exr_audio_checkpoint *position,exr_error *error);
EXR_API exr_status exr_library_audio_resume_get(exr_library *library,const char *audio_id,exr_audio_checkpoint *position,int *found,exr_error *error);
EXR_API exr_status exr_library_audio_bookmark(exr_library *library,const char *audio_id,const exr_audio_bookmark *bookmark,int64_t *id,exr_error *error);
EXR_API exr_status exr_library_audio_bookmarks(exr_library *library,const char *audio_id,exr_audio_bookmark **bookmarks,size_t *count,exr_error *error);
EXR_API void exr_audio_bookmarks_free(exr_audio_bookmark *bookmarks,size_t count);
EXR_API exr_status exr_library_remove_audio_bookmark(exr_library *library,int64_t id,exr_error *error);
EXR_API exr_status exr_library_clear_audio(exr_library *library,const char *audio_id,exr_error *error);
EXR_API exr_status exr_library_open(const char *path, exr_library **out, exr_error *error);
EXR_API void exr_library_close(exr_library *library);
/* Imports original bytes (including PDF) and the first declared reflow cover-image up to 8 MiB.
   Larger covers remain in the original source; failed cover reads abort the insert. */
EXR_API exr_status exr_library_import(exr_library *library, exr_format format, const void *data,
                                      size_t size, const char *title, int64_t *id,
                                      exr_error *error);
/* Opt-in exact deduplication: same format and original bytes reuse the oldest ID.
   Existing metadata, progress, cover and notes stay untouched. created is 1 only
   for an inserted row. Lookup/insert commit atomically across library handles;
   failure clears id/created. Ordinary import still permits duplicate records. */
EXR_API exr_status exr_library_import_unique(exr_library *library,exr_format format,const void *data,
                                             size_t size,const char *title,int64_t *id,int *created,exr_error *error);
EXR_API exr_status exr_library_books(exr_library *library, const char *query, exr_book **books,
                                     size_t *count, exr_error *error);
EXR_API void exr_books_free(exr_book *books, size_t count);
EXR_API exr_status exr_library_update(exr_library *library, const exr_book *book, exr_error *error);
EXR_API exr_status exr_library_document(exr_library *library, int64_t id, exr_document **doc,
                                        exr_error *error);
/* PDF books keep page-count extent and zero-based page progress. */
EXR_API exr_status exr_library_fixed(exr_library *library,int64_t id,const exr_fixed_open_options *options,
                                      exr_fixed_document **out,exr_error *error);
EXR_API exr_status exr_library_fixed_note(exr_library *library,const exr_fixed_note *note,const exr_control *control,
                                           int64_t *id,exr_error *error);
EXR_API exr_status exr_library_fixed_notes(exr_library *library,int64_t book_id,exr_fixed_note **notes,
                                            size_t *count,exr_error *error);
EXR_API void exr_fixed_notes_free(exr_fixed_note *notes,size_t count);
EXR_API exr_status exr_library_remove_fixed_note(exr_library *library,int64_t id,exr_error *error);
EXR_API exr_status exr_library_cover(exr_library *library, int64_t id, const void *data,
                                     size_t size, exr_error *error);
/* New/reranged notes capture a selector from the stored book. Updating only text
   preserves the old selector (including legacy). A non-NULL anchor.exact explicitly
   supplies a replacement selector, whose start/end must equal the note range. */
EXR_API exr_status exr_library_note(exr_library *library, const exr_note *note, int64_t *id,
                                    exr_error *error);
EXR_API exr_status exr_library_notes(exr_library *library, int64_t book_id, exr_note **notes,
                                     size_t *count, exr_error *error);
EXR_API void exr_notes_free(exr_note *notes, size_t count);
EXR_API void exr_free(void *memory);
EXR_API exr_status exr_library_blob(exr_library *library, int64_t id, int cover, void **data,
                                    size_t *size, exr_error *error);
EXR_API exr_status exr_library_remove_note(exr_library *library, int64_t id, exr_error *error);
EXR_API exr_status exr_library_backup(exr_library *library, const char *path, exr_error *error);
EXR_API exr_status exr_library_delete(exr_library *library, int64_t id, exr_error *error);
#ifdef __cplusplus
}
#endif
#endif
