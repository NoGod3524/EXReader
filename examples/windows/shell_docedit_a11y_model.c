/* SPDX-License-Identifier: MIT */
/* Cell text/format edits use the engine's normal validation/copy/undo path. */
#include "../../src/docx_edit_model_internal.h"
#include <stdlib.h>
#include <string.h>

exr_status l07_edit_cell_paragraph(exr_edit_doc *doc,exr_edit_id table_id,
  size_t row,size_t col,const exr_edit_block *paragraph) {
  const exr_edit_block *b=exr_edit_find_block(doc,table_id);
  if(!b || !b->table || row>=b->table->row_count || col>=b->table->rows[row].cell_count)
    return EXR_ARGUMENT;
  const exr_edit_cell *cell=&b->table->rows[row].cells[col];
  if(!exr_edit_cell_can_split(cell))return EXR_UNSUPPORTED;
  size_t index=0;
  if(!paragraph || paragraph->kind!=EXR_EDIT_PARAGRAPH)return EXR_ARGUMENT;
  while(index<cell->block_count && cell->blocks[index].id!=paragraph->id)index++;
  if(index==cell->block_count || cell->blocks[index].kind!=EXR_EDIT_PARAGRAPH)return EXR_ARGUMENT;
  exr_edit_row *rows=malloc(b->table->row_count*sizeof(*rows));
  exr_edit_cell *cells=malloc(b->table->rows[row].cell_count*sizeof(*cells));
  exr_edit_block *blocks=malloc(cell->block_count*sizeof(*blocks));
  if(!rows || !cells || !blocks) {free(rows);free(cells);free(blocks);return EXR_MEMORY;}
  memcpy(rows,b->table->rows,b->table->row_count*sizeof(*rows));
  memcpy(cells,rows[row].cells,rows[row].cell_count*sizeof(*cells));
  memcpy(blocks,cell->blocks,cell->block_count*sizeof(*blocks));
  blocks[index]=*paragraph;
  cells[col].blocks=blocks;
  if(!(cells[col].changed&CELL_REPLACED))cells[col].changed|=CELL_PATCHED;
  rows[row].cells=cells;
  exr_edit_table table=*b->table;table.rows=rows;
  exr_edit_block replacement=*b;replacement.table=&table;
  exr_status status=exr_edit_replace(doc,table_id,&replacement);
  free(blocks);free(cells);free(rows);return status;
}
