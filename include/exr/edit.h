/* SPDX-License-Identifier: MIT */
#ifndef EXR_EDIT_H
#define EXR_EDIT_H
#include <exr/base.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct exr_edit_doc exr_edit_doc;
typedef struct exr_edit_tx exr_edit_tx;
typedef struct exr_edit_block exr_edit_block;
typedef struct exr_edit_table exr_edit_table;
typedef uint64_t exr_edit_id; /* Nonzero, document-wide, never reused (even after undo). */

enum {
  EXR_EDIT_FONT = 1u, EXR_EDIT_SIZE = 2u, EXR_EDIT_BOLD = 4u,
  EXR_EDIT_ITALIC = 8u, EXR_EDIT_COLOR = 16u
};
typedef struct {
  uint32_t present; /* Absent fields inherit. A present false bold/italic overrides inheritance. */
  char font[128]; /* UTF-8 w:rFonts/@w:ascii,hAnsi,eastAsia,cs; NUL terminated. */
  uint32_t size_half_points; /* w:sz, w:szCs */
  uint32_t color_rgb; /* w:color/@w:val, 0xRRGGBB */
  unsigned bold,italic; /* w:b, w:i: 0 or 1 */
} exr_edit_run_props;

typedef enum { EXR_EDIT_LEFT,EXR_EDIT_CENTER,EXR_EDIT_RIGHT,EXR_EDIT_JUSTIFY } exr_edit_alignment;
typedef enum { EXR_EDIT_LINE_AUTO,EXR_EDIT_LINE_EXACT,EXR_EDIT_LINE_AT_LEAST } exr_edit_line_rule;
enum {
  EXR_EDIT_ALIGN = 1u, EXR_EDIT_INDENT = 2u, EXR_EDIT_SPACING = 4u,
  EXR_EDIT_KEEP_NEXT = 8u, EXR_EDIT_KEEP_LINES = 16u, EXR_EDIT_PAGE_BEFORE = 32u,
  EXR_EDIT_NUMBERING = 64u
};
typedef struct {
  uint32_t present;
  exr_edit_alignment alignment; /* w:jc */
  int32_t indent_left,indent_right,indent_first_line; /* w:ind, twips; negative first = hanging */
  uint32_t space_before,space_after,line; /* w:spacing, twips; AUTO line uses 240ths */
  exr_edit_line_rule line_rule;
  unsigned keep_next,keep_lines,page_break_before; /* w:keepNext,keepLines,pageBreakBefore */
  uint32_t numbering_id,numbering_level; /* w:numPr/w:numId,ilvl; id 0 disables numbering */
} exr_edit_para_props;

typedef struct {
  exr_edit_id id;
  int32_t page_width,page_height; /* w:pgSz, positive twips */
  int32_t margin_top,margin_right,margin_bottom,margin_left; /* w:pgMar, twips */
  int32_t header_distance,footer_distance;
  unsigned landscape; /* w:pgSz/@w:orient */
  char header_refs[3][128],footer_refs[3][128]; /* relationship IDs: default, first, even */
} exr_edit_section;

typedef enum { EXR_EDIT_TEXT,EXR_EDIT_OPAQUE_RUN } exr_edit_run_kind;
typedef struct {
  exr_edit_id id;
  exr_edit_run_kind kind;
  const char *text; size_t text_size; /* UTF-8, byte length, owned copy is NUL terminated */
  exr_edit_run_props props;
  /* OPAQUE_RUN: complete unmodelled inline XML. TEXT: optional original run
     template, backed by the retained DOCX main part when using the IO bridge. */
  const void *opaque_xml; size_t opaque_size;
} exr_edit_run;
typedef enum { EXR_EDIT_PARAGRAPH,EXR_EDIT_TABLE,EXR_EDIT_PAGE_BREAK,
  EXR_EDIT_OPAQUE_BLOCK,EXR_EDIT_IMAGE } exr_edit_block_kind;
typedef enum { EXR_EDIT_BORDER_NONE,EXR_EDIT_BORDER_SINGLE,EXR_EDIT_BORDER_DOUBLE } exr_edit_borders;
enum { EXR_EDIT_CELL_MERGED=1u,EXR_EDIT_CELL_NESTED=2u,
  EXR_EDIT_CELL_SHADING=4u,EXR_EDIT_CELL_OPAQUE=8u };
typedef struct {
  exr_edit_id id;
  const exr_edit_block *blocks; size_t block_count; /* Paragraphs reuse the block/run model. */
  unsigned unsupported; /* Protected cells are retained as original XML. */
  const void *opaque_xml; size_t opaque_size;
  unsigned changed; /* Writer bookkeeping: replacement=1, vertical merge=2/4, patch=8. */
} exr_edit_cell;
typedef struct {
  exr_edit_id id;
  const exr_edit_cell *cells; size_t cell_count;
  const void *opaque_xml; size_t opaque_size;
  size_t source_index; /* Writer bookkeeping; 0 for newly seeded rows. */
} exr_edit_row;
struct exr_edit_table {
  const exr_edit_row *rows; size_t row_count,column_count;
  int32_t width_twips;
  exr_edit_borders borders;
  unsigned changed; /* Writer bookkeeping: width=1, borders=2, grid=4. */
  const int32_t *column_widths; /* column_count twip widths; NULL uses width/column_count. */
};
typedef enum { EXR_EDIT_IMAGE_PNG=1,EXR_EDIT_IMAGE_JPEG,EXR_EDIT_IMAGE_GIF,EXR_EDIT_IMAGE_BMP } exr_edit_image_format;
typedef struct {
  const void *data; size_t size; /* Original payload, never re-encoded; borrowed read-only. */
  int64_t width_emu,height_emu; /* 12700 EMU = 1 point. */
  unsigned jpeg; /* Compatibility flag; use format for new code. */
  unsigned format; /* exr_edit_image_format; 0 in legacy seeds uses jpeg. */
  exr_edit_id anchor_run_id; /* Imported inline image: owning run; 0 = standalone block. */
  size_t anchor_offset; /* Original byte offset in run XML; position() tracks later edits. */
} exr_edit_image;
struct exr_edit_block {
  exr_edit_id id,section_id;
  exr_edit_block_kind kind;
  exr_edit_para_props props;
  const exr_edit_run *runs; size_t run_count;
  /* Original paragraph/table/unknown XML. The DOCX bridge patches modelled
     properties in paragraph templates and retains all other source bytes. */
  const void *opaque_xml; size_t opaque_size;
  const exr_edit_table *table; /* TABLE: NULL keeps an opaque legacy seed. */
  const exr_edit_image *image; /* IMAGE: payload and exact EMU dimensions (635 EMU = 1 twip).
    Imported images follow their owning paragraph/table as anchor views. The
    original run XML remains the lossless writer template, emitted only once. */
};
typedef struct {
  exr_edit_id id;
  const char *name; /* OPC part path, e.g. word/media/image1.png or word/_rels/document.xml.rels */
  const void *data; size_t size;
} exr_edit_part;
typedef struct { size_t undo_depth; } exr_edit_options;
EXR_API exr_edit_options exr_edit_defaults(void); /* 100; explicit depth 0 disables history */
/* Seed an independent model from a decoder. This API does not parse/write DOCX.
   All data are deep copied. Supply every OPC part, opaque table/drawing and
   unmodelled property needed by a future writer to preserve source content.
   Nonzero seed IDs are retained and must be globally unique; zero IDs are assigned.
   section_id 0 selects the first section; NULL/0 sections creates a Letter section.
   Blocks must reference a supplied section. out is cleared on failure. */
EXR_API exr_status exr_edit_doc_create(const exr_edit_section *sections,size_t section_count,
  const exr_edit_block *blocks,size_t block_count,const exr_edit_part *parts,size_t part_count,
  const exr_edit_options *options,exr_edit_doc **out);
EXR_API void exr_edit_doc_free(exr_edit_doc *doc);
/* Lossless OPC-backed DOCX IO. Unknown XML and package parts are retained.
   UTF-8/US-ASCII XML only. Outputs are cleared on failure; release successful
   write output with exr_free(). Edits invalidate retained digital signatures. */
EXR_API exr_status exr_edit_docx_read(const void *data,size_t size,
  const exr_edit_options *options,exr_edit_doc **out,exr_error *error);
EXR_API exr_status exr_edit_docx_open(const char *path,const exr_edit_options *options,
  exr_edit_doc **out,exr_error *error);
EXR_API exr_status exr_edit_docx_write(const exr_edit_doc *doc,void **data,
  size_t *size,exr_error *error);

/* Borrowed read-only views. Block/run views expire when that block changes or
   leaves the model; IDs remain stable. Sections and parts live until doc_free.
   block_count/at enumerate top-level blocks; find_block also resolves cell blocks.
   Cell views expire on any change to their owning table.
   Objects are single-threaded; callers serialize access. */
EXR_API size_t exr_edit_block_count(const exr_edit_doc *doc);
EXR_API const exr_edit_block *exr_edit_block_at(const exr_edit_doc *doc,size_t index);
EXR_API const exr_edit_block *exr_edit_find_block(const exr_edit_doc *doc,exr_edit_id id);
EXR_API const exr_edit_section *exr_edit_sections(const exr_edit_doc *doc,size_t *count);
EXR_API const exr_edit_part *exr_edit_parts(const exr_edit_doc *doc,size_t *count);
/* Retained allocation bytes, including history/capacity (excludes allocator overhead). */
EXR_API size_t exr_edit_memory_bytes(const exr_edit_doc *doc);

/* after_id 0 prepends. A cell paragraph anchor inserts into that same cell.
   Runs receive fresh IDs; section inherits from anchor
   (first section at start). NULL props uses an empty/inheriting property set.
   Input buffers may alias borrowed views. Output ID is cleared on failure. */
EXR_API exr_status exr_edit_insert_paragraph(exr_edit_doc *doc,exr_edit_id after_id,
  const exr_edit_run *runs,size_t count,const exr_edit_para_props *props,exr_edit_id *new_id);
/* UTF-8 scalar boundary, not a character index. (run_count,0) splits at end.
   Left block retains its ID; the next block gets a fresh ID. Whole moved runs
   retain IDs; only the right fragment of a divided run gets a fresh ID.
   Opaque runs can only be split before them (offset 0). Paragraph props copy.
   Editable cell paragraphs split within their owning cell. */
EXR_API exr_status exr_edit_split_paragraph(exr_edit_doc *doc,exr_edit_id block_id,
  size_t run_index,size_t byte_offset);
EXR_API exr_status exr_edit_set_paragraph_props(exr_edit_doc *doc,exr_edit_id block_id,
  const exr_edit_para_props *props);
EXR_API exr_status exr_edit_set_run_props(exr_edit_doc *doc,exr_edit_id block_id,
  size_t run_index,const exr_edit_run_props *props);
/* Replace one TEXT run with valid UTF-8/XML text (byte length, not characters).
   IDs, direct properties, original XML template and neighbouring opaque runs
   are retained. Buffers may alias borrowed text; NULL/0 clears the run.
   Editable cell paragraphs are updated without replacing sibling paragraphs.
   Protected cells and opaque runs return EXR_UNSUPPORTED.
   Participates in transactions/undo/redo. */
EXR_API exr_status exr_edit_set_run_text(exr_edit_doc *doc,exr_edit_id block_id,
  size_t run_index,const char *text,size_t text_size);
/* Insert a fresh TEXT run before run_index (run_count appends, including 0 on
   an empty paragraph). Text must be non-NULL and nonempty. Requires the
   document's active transaction. Preserves
   paragraph templates, existing runs and sibling cell paragraphs. */
EXR_API exr_status exr_edit_insert_run(exr_edit_doc *doc,exr_edit_tx *tx,
  exr_edit_id paragraph,size_t run_index,const char *text,size_t text_size,
  const exr_edit_run_props *props);
EXR_API exr_status exr_edit_delete_block(exr_edit_doc *doc,exr_edit_id block_id);

/* Zero-based physical row/cell indices. SIZE_MAX inserts before the first row.
   Protected cells (merges, nested tables, shading or opaque content) cannot be
   replaced. Other cells/rows in the same table remain editable. Vertical merge
   chains cannot be split by inserting/deleting a row. Each command participates
   in the same transaction/undo history as paragraph edits. */
EXR_API exr_status exr_edit_table_insert_row(exr_edit_doc *doc,exr_edit_id table_id,size_t after_row_index);
EXR_API exr_status exr_edit_table_delete_row(exr_edit_doc *doc,exr_edit_id table_id,size_t row_index);
EXR_API exr_status exr_edit_table_set_cell_text(exr_edit_doc *doc,exr_edit_id table_id,
  size_t row,size_t col,const exr_edit_run *runs,size_t count);
EXR_API exr_status exr_edit_table_set_width(exr_edit_doc *doc,exr_edit_id table_id,int32_t twips);
/* All modelled cell blocks in document order, including protected/opaque blocks.
   Invalid cells return 0/NULL; at also returns NULL for an out-of-range index.
   Borrowed views; querying neither edits nor latches transaction failures. */
EXR_API size_t exr_edit_table_cell_block_count(
  const exr_edit_doc *doc,exr_edit_id table,size_t row,size_t column);
EXR_API const exr_edit_block *exr_edit_table_cell_block_at(
  const exr_edit_doc *doc,exr_edit_id table,size_t row,size_t column,size_t index);
/* Editable paragraphs in document order; NULL for invalid indices/protected cells.
   Empty cells return their existing placeholder paragraph, if any. Borrowed view. */
EXR_API const exr_edit_block *exr_edit_table_cell_paragraph(
  const exr_edit_doc *doc,exr_edit_id table,size_t row,size_t column,size_t index);
/* Requires doc's active transaction. Positive twips; sets grid[column] and
   table width to the sum of all columns. Undo/redo restores both. */
EXR_API exr_status exr_edit_table_set_column_width(
  exr_edit_doc *doc,exr_edit_tx *tx,exr_edit_id table,size_t column,int32_t width_twips);
EXR_API exr_status exr_edit_table_set_borders(exr_edit_doc *doc,exr_edit_id table_id,exr_edit_borders spec);
EXR_API exr_status exr_edit_delete_table(exr_edit_doc *doc,exr_edit_id table_id);
/* Payload length is required for a C byte buffer. Dimensions are points, finite
   and positive. The existing decoder accepts PNG/JPEG/BMP/GIF. GIF uses frame 0
   for display; the complete original GIF payload is retained. after_id 0 prepends.
   Delete accepts a new image block ID, an imported drawing run ID (including
   table-cell runs), or a paragraph ID to remove its drawings while keeping text.
   Export prunes removed image relationships and media unused by any OPC part. */
EXR_API exr_status exr_edit_insert_image(exr_edit_doc *doc,exr_edit_id after_id,
  const void *bytes,size_t size,double width_pt,double height_pt,exr_edit_id *new_id);
EXR_API exr_status exr_edit_delete_image(exr_edit_doc *doc,exr_edit_id image_id);
/* Locate an imported image in its current paragraph (including table cells).
   run_index and byte_offset identify the drawing/pict within the run's XML.
   Standalone images return paragraph_id=0, run_index=byte_offset=0.
   Read-only, borrowed block must be a current view from doc. Outputs required
   and cleared on failure; same single-thread/lifetime rules as block_at. */
EXR_API exr_status exr_edit_image_position(const exr_edit_doc *doc,const exr_edit_block *block,
  exr_edit_id *paragraph_id,size_t *run_index,size_t *byte_offset);

/* No nested transactions. NULL means invalid document, active tx or allocation
   failure. Outside a tx each successful command is one undo entry.
   A failed command latches its status: further commands fail until rollback.
   commit of a failed tx rolls the entire tx back and returns that status.
   commit/rollback consume the handle. doc_free also rolls back an active tx.
   Empty commits preserve redo. A successful new edit clears redo at commit.
   Undo/redo while a tx is open, or with an empty stack, returns EXR_ARGUMENT. */
EXR_API exr_edit_tx *exr_edit_begin(exr_edit_doc *doc);
EXR_API exr_status exr_edit_commit(exr_edit_tx *tx);
EXR_API exr_status exr_edit_rollback(exr_edit_tx *tx);
EXR_API exr_status exr_edit_undo(exr_edit_doc *doc);
EXR_API exr_status exr_edit_redo(exr_edit_doc *doc);
#ifdef __cplusplus
}
#endif
#endif
