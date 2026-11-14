/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <exr/edit.h>
extern void *XML_ParserCreate(const char *);
extern void XML_ParserFree(void *);
extern void XML_SetUserData(void *,void *);
extern void XML_SetElementHandler(void *,void (*)(void *,const char *,const char **),void (*)(void *,const char *));
extern int XML_Parse(void *,const char *,int,int);
#include "shell_docedit_merged_cells.h"
static exr_edit_cell cell(const char *xml) {
  exr_edit_cell c={0};c.opaque_xml=xml;c.opaque_size=strlen(xml);return c;
}
int main(void) {
  exr_edit_cell cells[6]={0};exr_edit_row rows[3]={0};exr_edit_table table={0};
  de_merged_cell *grid=NULL;size_t count=0;
  cells[0]=cell("<q:tc><q:tcPr><q:gridSpan q:val='2'/><q:vMerge q:val='restart'/></q:tcPr><q:p/></q:tc>");
  cells[1]=cell("<w:tc><w:p/></w:tc>");
  cells[2]=cell("<w:tc><w:tcPr><w:gridSpan w:val='2'/><w:vMerge/></w:tcPr><w:p/></w:tc>");
  cells[3]=cells[1];cells[4]=cells[2];cells[5]=cells[1];
  for(size_t r=0;r<3;r++) {rows[r].cells=cells+2*r;rows[r].cell_count=2;}
  table.rows=rows;table.row_count=3;table.column_count=3;
  assert(de_merge_grid(&table,&grid,&count) && count==6);
  assert(grid[0].columns==2 && grid[0].rows==3);
  for(size_t r=0;r<3;r++)for(size_t c=0;c<2;c++)assert(de_merge_at(grid,count,r,c)==grid);
  assert(de_merge_at(grid,count,2,2)==grid+5 && !de_merge_at(grid,count,3,0));
  size_t row=2,col=0;int merged=0;
  assert(de_merge_resolve(&table,&row,&col,0,&merged) && !row && !col && merged);
  assert(de_merge_resolve(&table,&row,&col,1,&merged) && !row && col==1 && !merged);
  assert(de_merge_resolve(&table,&row,&col,-1,&merged) && !row && !col && merged);
  free(grid);puts("PASS gridSpan + vMerge: 2 columns x 3 rows, all covered positions resolve to one owner");
  cells[0]=cell("<w:tc><w:tcPr><w:hMerge w:val='restart'/></w:tcPr></w:tc>");
  cells[1]=cell("<w:tc><w:tcPr><w:hMerge/></w:tcPr></w:tc>");
  table.row_count=1;table.column_count=2;
  assert(de_merge_grid(&table,&grid,&count));
  assert(grid[0].columns==2 && grid[1].owner==0 && de_merge_at(grid,count,0,1)==grid);
  free(grid);puts("PASS legacy hMerge continuation resolves to horizontal owner");
  cells[0]=cell("<w:tc><w:tcPr/><w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val='9'/></w:tcPr></w:tc></w:tr></w:tbl></w:tc>");
  cells[1]=cell("<w:tc><w:tcPr><w:vMerge/></w:tcPr></w:tc>");
  assert(de_merge_grid(&table,&grid,&count));
  assert(grid[0].columns==1 && grid[1].owner==1);free(grid);
  puts("PASS nested table properties ignored; orphan continuation remains its own cell");
  cells[0]=cell("<w:tc><w:tcPr><w:gridSpan w:val='3'/></w:tcPr></w:tc>");
  assert(!de_merge_grid(&table,&grid,&count) && !grid && !count);
  cells[0]=cell("<w:tc>");assert(!de_merge_grid(&table,&grid,&count));
  puts("PASS overflowing spans and malformed XML rejected");return 0;
}
