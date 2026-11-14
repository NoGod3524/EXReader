/* SPDX-License-Identifier: MIT */
/* Logical grid shared by painting and hit testing. Include after edit.h and
   Expat declarations. Entries index physical cells, owners index this array. */
#ifndef EXR_SHELL_DOCEDIT_MERGED_CELLS_H
#define EXR_SHELL_DOCEDIT_MERGED_CELLS_H
typedef struct {
  size_t row,cell,column,columns,rows,owner;
  unsigned vertical,horizontal;
} de_merged_cell;

/* Read-only physical cell query for display, including protected content.
   A returned view does not grant paragraph editing permission. */
static const exr_edit_cell *de_merge_cell_view(const exr_edit_table *table,size_t row,size_t cell) {
  if(!table || row>=table->row_count || cell>=table->rows[row].cell_count)return NULL;
  return table->rows[row].cells+cell;
}
typedef struct { int depth,properties; size_t span; unsigned vertical,horizontal; } de_merge_parse;
static const char *de_merge_local(const char *name) {
  const char *colon=strrchr(name,':');return colon ? colon+1:name;
}
static void de_merge_start(void *context,const char *name,const char **attrs) {
  de_merge_parse *p=context;const char *value="";p->depth++;
  name=de_merge_local(name);
  if(p->depth==2 && !strcmp(name,"tcPr"))p->properties=1;
  if(!p->properties || p->depth!=3)return;
  for(size_t i=0;attrs[i];i+=2)
    if(!strcmp(de_merge_local(attrs[i]),"val"))value=attrs[i+1];
  if(!strcmp(name,"gridSpan")) {
    char *end;unsigned long span=strtoul(value,&end,10);
    if(*value && !*end && span>0 && span<=16384)p->span=span;
  } else if(!strcmp(name,"vMerge"))p->vertical=!strcmp(value,"restart") ? 1:2;
  else if(!strcmp(name,"hMerge"))p->horizontal=!strcmp(value,"restart") ? 1:2;
}
static void de_merge_end(void *context,const char *name) {
  de_merge_parse *p=context;(void)name;
  if(p->depth==2)p->properties=0;
  p->depth--;
}
static int de_merge_properties(const exr_edit_cell *cell,de_merge_parse *p) {
  memset(p,0,sizeof(*p));p->span=1;
  if(!cell->opaque_size)return 1;
  if(!cell->opaque_xml || cell->opaque_size>INT_MAX)return 0;
  void *parser=XML_ParserCreate(NULL);if(!parser)return 0;
  XML_SetUserData(parser,p);XML_SetElementHandler(parser,de_merge_start,de_merge_end);
  int ok=XML_Parse(parser,cell->opaque_xml,(int)cell->opaque_size,1)==1;
  XML_ParserFree(parser);return ok;
}
static int de_merge_grid(const exr_edit_table *table,de_merged_cell **out,size_t *count) {
  size_t total=0,at=0;*out=NULL;*count=0;
  if(!table)return 0;
  for(size_t r=0;r<table->row_count;r++) {
    if(table->rows[r].cell_count>SIZE_MAX-total)return 0;
    total+=table->rows[r].cell_count;
  }
  if(total>SIZE_MAX/sizeof(de_merged_cell))return 0;
  de_merged_cell *grid=calloc(total ? total:1,sizeof(*grid));if(!grid)return 0;
  for(size_t r=0;r<table->row_count;r++) {
    size_t column=0,start=at;
    for(size_t c=0;c<table->rows[r].cell_count;c++,at++) {
      de_merge_parse p;
      if(!de_merge_properties(table->rows[r].cells+c,&p) ||
         column>table->column_count || p.span>table->column_count-column)goto fail;
      de_merged_cell *cell=grid+at;
      cell->row=r;cell->cell=c;cell->column=column;cell->columns=p.span;
      cell->rows=1;cell->owner=at;cell->vertical=p.vertical;cell->horizontal=p.horizontal;
      column+=p.span;
      if(p.horizontal==2 && at>start) {
        de_merged_cell *left=grid+grid[at-1].owner;
        if(left->horizontal && left->row==r) {
          cell->owner=grid[at-1].owner;left->columns+=p.span;
        }
      }
    }
    /* Resolve vertical continuations after horizontal widths are complete. */
    for(size_t i=start;i<at;i++)if(grid[i].owner==i && grid[i].vertical==2) {
      for(size_t j=start;j>0;) {
        de_merged_cell *above=grid+--j;
        if(above->row+1<r)break;
        if(above->row+1==r && above->vertical && above->column==grid[i].column &&
           above->columns==grid[i].columns) {
          size_t owner=above->owner;
          grid[i].owner=owner;grid[owner].rows=r-grid[owner].row+1;break;
        }
      }
    }
    /* Horizontal continuation targets can themselves be vertical continuations. */
    for(size_t i=start;i<at;i++)grid[i].owner=grid[grid[i].owner].owner;
  }
  *out=grid;*count=total;return 1;
fail:
  free(grid);return 0;
}
static const de_merged_cell *de_merge_at(const de_merged_cell *grid,size_t count,size_t row,size_t column) {
  for(size_t i=0;i<count;i++)if(grid[i].row==row && column>=grid[i].column &&
    column-grid[i].column<grid[i].columns)return grid+grid[i].owner;
  return NULL;
}
/* Panel coordinates are physical row/cell indices; grid coordinates are not. */
static int de_merge_resolve(const exr_edit_table *t,size_t *row,size_t *cell,int direction,int *merged) {
  de_merged_cell *grid=NULL;size_t count=0,at=SIZE_MAX;
  if(!de_merge_grid(t,&grid,&count))return 0;
  for(size_t i=0;i<count;i++)if(grid[i].row==*row && grid[i].cell==*cell) {at=grid[i].owner;break;}
  if(at==SIZE_MAX) {free(grid);return 0;}
  if(direction>0) {
    for(size_t i=at+1;i<count;i++)if(grid[i].owner==i) {at=i;break;}
  } else if(direction<0) {
    for(size_t i=at;i>0;) {i--;if(grid[i].owner==i) {at=i;break;}}
  }
  *row=grid[at].row;*cell=grid[at].cell;
  if(merged)*merged=grid[at].columns>1 || grid[at].rows>1 || grid[at].vertical || grid[at].horizontal;
  free(grid);return 1;
}
#define DE_MERGE_STRUCTURE_MESSAGE L"合并单元格只读；不能修改文字、增删行或调整列宽。"
#endif
