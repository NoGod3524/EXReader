/* SPDX-License-Identifier: MIT */
#ifndef EXR_EDIT_H
#define EXR_EDIT_H
#include <exr/base.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct exr_edit_doc exr_edit_doc;
typedef struct exr_edit_tx exr_edit_tx;
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
  const void *opaque_xml; size_t opaque_size; /* Uninterpreted drawing/unknown inline XML */
} exr_edit_run;
typedef enum { EXR_EDIT_PARAGRAPH,EXR_EDIT_TABLE,EXR_EDIT_PAGE_BREAK,
  EXR_EDIT_OPAQUE_BLOCK } exr_edit_block_kind;
typedef struct {
  exr_edit_id id,section_id;
  exr_edit_block_kind kind;
  exr_edit_para_props props;
  const exr_edit_run *runs; size_t run_count;
  /* Original paragraph/table/unknown XML. The DOCX bridge patches modelled
     properties in paragraph templates and retains all other source bytes. */
  const void *opaque_xml; size_t opaque_size;
} exr_edit_block;
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
/* Borrowed read-only views. Block/run views expire when that block changes or
   leaves the model; IDs remain stable. Sections and parts live until doc_free.
   Objects are single-threaded; callers serialize access. */
EXR_API size_t exr_edit_block_count(const exr_edit_doc *doc);
EXR_API const exr_edit_block *exr_edit_block_at(const exr_edit_doc *doc,size_t index);
EXR_API const exr_edit_block *exr_edit_find_block(const exr_edit_doc *doc,exr_edit_id id);
EXR_API const exr_edit_section *exr_edit_sections(const exr_edit_doc *doc,size_t *count);
EXR_API const exr_edit_part *exr_edit_parts(const exr_edit_doc *doc,size_t *count);
/* Retained allocation bytes, including history/capacity (excludes allocator overhead). */
EXR_API size_t exr_edit_memory_bytes(const exr_edit_doc *doc);

/* after_id 0 prepends. Runs receive fresh IDs; section inherits from anchor
   (first section at start). NULL props uses an empty/inheriting property set.
   Input buffers may alias borrowed views. Output ID is cleared on failure. */
EXR_API exr_status exr_edit_insert_paragraph(exr_edit_doc *doc,exr_edit_id after_id,
  const exr_edit_run *runs,size_t count,const exr_edit_para_props *props,exr_edit_id *new_id);
/* UTF-8 scalar boundary, not a character index. (run_count,0) splits at end.
   Left block retains its ID; the next block gets a fresh ID. Whole moved runs
   retain IDs; only the right fragment of a divided run gets a fresh ID.
   Opaque runs can only be split before them (offset 0). Paragraph props copy. */
EXR_API exr_status exr_edit_split_paragraph(exr_edit_doc *doc,exr_edit_id block_id,
  size_t run_index,size_t byte_offset);
EXR_API exr_status exr_edit_set_paragraph_props(exr_edit_doc *doc,exr_edit_id block_id,
  const exr_edit_para_props *props);
EXR_API exr_status exr_edit_set_run_props(exr_edit_doc *doc,exr_edit_id block_id,
  size_t run_index,const exr_edit_run_props *props);
/* Tables are retained but cannot be deleted/edited in this version. */
EXR_API exr_status exr_edit_delete_block(exr_edit_doc *doc,exr_edit_id block_id);

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
