/* SPDX-License-Identifier: MIT */
#include "docx_edit_internal.h"

static const exr_edit_block *table_block(exr_edit_doc *d,exr_edit_id id,exr_status *s) {
  const exr_edit_block *b=NULL;
  *s=exr_edit_ready(d);
  if (!*s) {
    b=exr_edit_find_block(d,id);
    if (!b || b->kind!=EXR_EDIT_TABLE) *s=exr_edit_failure(d,EXR_ARGUMENT);
    else if (!b->table) *s=exr_edit_failure(d,EXR_UNSUPPORTED);
  }
  return *s ? NULL : b;
}
/* Vertical merge continuations must keep their preceding row. The decoder
   marks merge cells; use their original XML to distinguish horizontal merges. */
static int vertical(const exr_edit_row *r,int continuation) {
  size_t i;
  for (i=0;i<r->cell_count;i++) if (r->cells[i].unsupported&EXR_EDIT_CELL_MERGED) {
    const exr_edit_cell *c=r->cells+i;
    /* These flags are set by the namespace-aware decoder below. */
    if ((c->changed&(continuation ? CELL_VMERGE_CONTINUE : CELL_VMERGE_START|CELL_VMERGE_CONTINUE))) return 1;
  }
  return 0;
}
exr_status exr_edit_table_insert_row(exr_edit_doc *d,exr_edit_id id,size_t after) {
  exr_status s; const exr_edit_block *b=table_block(d,id,&s); exr_edit_block v,p={0};
  exr_edit_table t; exr_edit_row *rows; exr_edit_cell *cells; size_t at,i;
  if (!b) return s;
  t=*b->table; at=after==SIZE_MAX ? 0 : after+1;
  if (after!=SIZE_MAX && after>=t.row_count) return exr_edit_failure(d,EXR_ARGUMENT);
  if (at<t.row_count && vertical(t.rows+at,1)) return exr_edit_failure(d,EXR_UNSUPPORTED);
  if (t.row_count>=SIZE_MAX/sizeof(*rows)-1) return exr_edit_failure(d,EXR_LIMIT);
  rows=calloc(t.row_count+1,sizeof(*rows)); cells=calloc(t.column_count,sizeof(*cells));
  if (!rows || !cells) { free(rows); free(cells); return exr_edit_failure(d,EXR_MEMORY); }
  memcpy(rows,t.rows,at*sizeof(*rows)); memcpy(rows+at+1,t.rows+at,(t.row_count-at)*sizeof(*rows));
  /* Inherit paragraph formatting from the first simple source cell (or any paragraph cell). */
  for (i=0;i<t.rows[after==SIZE_MAX ? 0 : after].cell_count;i++) {
    const exr_edit_cell *c=t.rows[after==SIZE_MAX ? 0 : after].cells+i;
    if (!c->unsupported && c->block_count && c->blocks[0].kind==EXR_EDIT_PARAGRAPH) {
      p.props=c->blocks[0].props; p.opaque_xml=c->blocks[0].opaque_xml; p.opaque_size=c->blocks[0].opaque_size; break;
    }
  }
  if (!p.opaque_xml) for (i=0;i<t.rows[after==SIZE_MAX ? 0 : after].cell_count;i++) {
    const exr_edit_cell *c=t.rows[after==SIZE_MAX ? 0 : after].cells+i;
    if (c->block_count && c->blocks[0].kind==EXR_EDIT_PARAGRAPH) {
      p.props=c->blocks[0].props; p.opaque_xml=c->blocks[0].opaque_xml; p.opaque_size=c->blocks[0].opaque_size; break;
    }
  }
  for (i=0;i<t.column_count;i++) { cells[i].blocks=&p; cells[i].block_count=1; cells[i].changed=CELL_REPLACED; }
  rows[at].cells=cells; rows[at].cell_count=t.column_count; t.rows=rows; t.row_count++;
  v=*b; v.table=&t; s=exr_edit_replace(d,id,&v);
  free(cells); free(rows); return s;
}
exr_status exr_edit_table_delete_row(exr_edit_doc *d,exr_edit_id id,size_t at) {
  exr_status s; const exr_edit_block *b=table_block(d,id,&s); exr_edit_block v; exr_edit_table t; exr_edit_row *rows;
  if (!b) return s;
  t=*b->table;
  if (at>=t.row_count || t.row_count==1) return exr_edit_failure(d,EXR_ARGUMENT);
  if (vertical(t.rows+at,0) || (at+1<t.row_count && vertical(t.rows+at+1,1))) return exr_edit_failure(d,EXR_UNSUPPORTED);
  rows=malloc((t.row_count-1)*sizeof(*rows)); if (!rows) return exr_edit_failure(d,EXR_MEMORY);
  memcpy(rows,t.rows,at*sizeof(*rows)); memcpy(rows+at,t.rows+at+1,(t.row_count-at-1)*sizeof(*rows));
  t.rows=rows; t.row_count--; v=*b; v.table=&t;
  s=exr_edit_replace(d,id,&v); free(rows); return s;
}
exr_status exr_edit_table_set_cell_text(exr_edit_doc *d,exr_edit_id id,size_t row,size_t col,const exr_edit_run *runs,size_t count) {
  exr_status s; const exr_edit_block *b=table_block(d,id,&s); exr_edit_block v,p={0}; exr_edit_table t;
  exr_edit_row *rows; exr_edit_cell *cells; exr_edit_run *rs=NULL; size_t i;
  if (!b) return s;
  t=*b->table;
  if (row>=t.row_count || col>=t.rows[row].cell_count || (count && !runs) || count>SIZE_MAX/sizeof(*rs))
    return exr_edit_failure(d,EXR_ARGUMENT);
  if (t.rows[row].cells[col].unsupported) return exr_edit_failure(d,EXR_UNSUPPORTED);
  if (count) {
    rs=malloc(count*sizeof(*rs)); if (!rs) return exr_edit_failure(d,EXR_MEMORY);
    for (i=0;i<count;i++) {
      if (runs[i].kind!=EXR_EDIT_TEXT) { free(rs); return exr_edit_failure(d,EXR_ARGUMENT); }
      rs[i]=runs[i]; rs[i].id=0; rs[i].opaque_xml=NULL; rs[i].opaque_size=0;
    }
  }
  rows=malloc(t.row_count*sizeof(*rows)); cells=malloc(t.rows[row].cell_count*sizeof(*cells));
  if (!rows || !cells) { free(rows); free(cells); free(rs); return exr_edit_failure(d,EXR_MEMORY); }
  memcpy(rows,t.rows,t.row_count*sizeof(*rows)); memcpy(cells,t.rows[row].cells,t.rows[row].cell_count*sizeof(*cells));
  if (cells[col].block_count) p=cells[col].blocks[0];
  p.kind=EXR_EDIT_PARAGRAPH; p.runs=rs; p.run_count=count;
  cells[col].blocks=&p; cells[col].block_count=1; cells[col].changed=CELL_REPLACED;
  rows[row].cells=cells; t.rows=rows; v=*b; v.table=&t;
  s=exr_edit_replace(d,id,&v); free(rows); free(cells); free(rs); return s;
}
exr_status exr_edit_table_set_width(exr_edit_doc *d,exr_edit_id id,int32_t twips) {
  exr_status s; const exr_edit_block *b=table_block(d,id,&s); exr_edit_block v; exr_edit_table t;
  if (!b) return s;
  if (twips<=0) return exr_edit_failure(d,EXR_ARGUMENT);
  t=*b->table; t.width_twips=twips; t.changed|=1; v=*b; v.table=&t;
  return exr_edit_replace(d,id,&v);
}
static const exr_edit_cell *table_cell(const exr_edit_doc *d,exr_edit_id id,size_t row,size_t col) {
  const exr_edit_block *b=exr_edit_find_block(d,id);
  if (!b || !b->table || row>=b->table->row_count || col>=b->table->rows[row].cell_count) return NULL;
  return b->table->rows[row].cells+col;
}
size_t exr_edit_table_cell_block_count(const exr_edit_doc *d,exr_edit_id id,size_t row,size_t col) {
  const exr_edit_cell *cell=table_cell(d,id,row,col);
  return cell ? cell->block_count : 0;
}
const exr_edit_block *exr_edit_table_cell_block_at(
  const exr_edit_doc *d,exr_edit_id id,size_t row,size_t col,size_t index) {
  const exr_edit_cell *cell=table_cell(d,id,row,col);
  return cell && index<cell->block_count ? cell->blocks+index : NULL;
}
const exr_edit_block *exr_edit_table_cell_paragraph(
  const exr_edit_doc *d,exr_edit_id id,size_t row,size_t col,size_t index) {
  const exr_edit_cell *c=table_cell(d,id,row,col); size_t i;
  if (!c) return NULL;
  if (!exr_edit_cell_can_split(c)) return NULL;
  for (i=0;i<c->block_count;i++) if (c->blocks[i].kind==EXR_EDIT_PARAGRAPH) {
    if (!index) return c->blocks+i;
    index--;
  }
  return NULL;
}
exr_status exr_edit_table_set_column_width(
  exr_edit_doc *d,exr_edit_tx *tx,exr_edit_id id,size_t col,int32_t twips) {
  exr_status s=exr_edit_tx_ready(d,tx); const exr_edit_block *b;
  exr_edit_block v; exr_edit_table t; int32_t *widths; int64_t sum=0; size_t i;
  if (s) return s;
  b=table_block(d,id,&s); if (!b) return s;
  t=*b->table;
  if (col>=t.column_count || twips<=0) return exr_edit_failure(d,EXR_ARGUMENT);
  widths=malloc(t.column_count*sizeof(*widths));
  if (!widths) return exr_edit_failure(d,EXR_MEMORY);
  for (i=0;i<t.column_count;i++) {
    widths[i]=i==col ? twips : t.column_widths ? t.column_widths[i] : t.width_twips/(int32_t)t.column_count;
    sum+=widths[i];
  }
  if (sum>INT32_MAX) { free(widths); return exr_edit_failure(d,EXR_LIMIT); }
  t.column_widths=widths; t.width_twips=(int32_t)sum; t.changed|=5u; v=*b; v.table=&t;
  s=exr_edit_replace(d,id,&v); free(widths); return s;
}
exr_status exr_edit_table_set_borders(exr_edit_doc *d,exr_edit_id id,exr_edit_borders spec) {
  exr_status s; const exr_edit_block *b=table_block(d,id,&s); exr_edit_block v; exr_edit_table t;
  if (!b) return s;
  if (spec<EXR_EDIT_BORDER_NONE || spec>EXR_EDIT_BORDER_DOUBLE) return exr_edit_failure(d,EXR_ARGUMENT);
  t=*b->table; t.borders=spec; t.changed|=2; v=*b; v.table=&t;
  return exr_edit_replace(d,id,&v);
}
exr_status exr_edit_delete_table(exr_edit_doc *d,exr_edit_id id) {
  const exr_edit_block *b; exr_status s=exr_edit_ready(d);
  if (s) return s;
  b=exr_edit_find_block(d,id);
  return !b || b->kind!=EXR_EDIT_TABLE ? exr_edit_failure(d,EXR_ARGUMENT) : exr_edit_replace(d,id,NULL);
}

void exr_edit_table_decode_free(exr_edit_table *t) {
  size_t i,j,k,l;
  if (!t) return;
  for (i=0;i<t->row_count;i++) {
    const exr_edit_row *r=t->rows+i;
    for (j=0;j<r->cell_count;j++) {
      const exr_edit_cell *c=r->cells+j;
      for (k=0;k<c->block_count;k++) {
        for (l=0;l<c->blocks[k].run_count;l++) free((void *)c->blocks[k].runs[l].text);
        free((void *)c->blocks[k].runs);
      }
      free((void *)c->blocks);
    }
    free((void *)r->cells);
  }
  free((void *)t->column_widths); free((void *)t->rows); free(t);
}
static void template(const source_xml *x,size_t n,const void **xml,size_t *size) {
  *xml=x->bytes+x->spans[n].start; *size=x->spans[n].end-x->spans[n].start;
}
exr_status exr_edit_table_decode(const source_xml *x,size_t n,exr_edit_table **out) {
  exr_edit_table *t=calloc(1,sizeof(*t)); exr_edit_row *rows=NULL;
  size_t i,j,k,l,rc=0,cc=0,bc=0,pr,grid; int32_t value; exr_status status=EXR_MEMORY;
  *out=NULL; if (!t) return status;
  pr=exr_edit_xml_child(x,n,"tblPr"); grid=exr_edit_xml_child(x,n,"tblGrid");
  i=exr_edit_xml_child(x,pr,"tblW");
  if (i!=NONE && exr_edit_xml_integer(exr_edit_xml_wa(x->tree->nodes+i,"w"),&value) && value>=0) {
    const char *type=exr_edit_xml_wa(x->tree->nodes+i,"type");
    if (type && !strcmp(type,"dxa")) t->width_twips=value;
  }
  i=exr_edit_xml_child(x,exr_edit_xml_child(x,pr,"tblBorders"),"top");
  if (i!=NONE) {
    const char *val=exr_edit_xml_wa(x->tree->nodes+i,"val");
    t->borders=val && !strcmp(val,"double") ? EXR_EDIT_BORDER_DOUBLE : val && !strcmp(val,"single") ? EXR_EDIT_BORDER_SINGLE : EXR_EDIT_BORDER_NONE;
  }
  if (grid!=NONE) for (i=x->tree->nodes[grid].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling)
    if (exr_edit_xml_word(x->tree->nodes+i,"gridCol")) t->column_count++;
  for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (exr_edit_xml_word(x->tree->nodes+i,"tr")) {
    exr_edit_row *row; exr_edit_cell *cells=NULL; size_t columns=0;
    if (!exr_grow((void **)&rows,&rc,t->row_count+1,sizeof(*rows))) goto done;
    t->rows=rows; row=rows+t->row_count++; memset(row,0,sizeof(*row)); cc=0;
    row->source_index=i+1;
    template(x,i,&row->opaque_xml,&row->opaque_size);
    for (j=x->tree->nodes[i].first_child;j!=NONE;j=x->tree->nodes[j].next_sibling) if (exr_edit_xml_word(x->tree->nodes+j,"tc")) {
      exr_edit_cell *cell; exr_edit_block *blocks=NULL; size_t span=1;
      if (!exr_grow((void **)&cells,&cc,row->cell_count+1,sizeof(*cells))) goto done;
      row->cells=cells; cell=cells+row->cell_count++; memset(cell,0,sizeof(*cell)); bc=0;
      template(x,j,&cell->opaque_xml,&cell->opaque_size); pr=exr_edit_xml_child(x,j,"tcPr");
      k=exr_edit_xml_child(x,pr,"gridSpan");
      if (k!=NONE && exr_edit_xml_integer(exr_edit_xml_wa(x->tree->nodes+k,"val"),&value) && value>0) {
        span=(size_t)value; if (span>1) cell->unsupported|=EXR_EDIT_CELL_MERGED;
      }
      columns+=span;
      k=exr_edit_xml_child(x,pr,"vMerge");
      if (k!=NONE) {
        const char *val=exr_edit_xml_wa(x->tree->nodes+k,"val");
        cell->unsupported|=EXR_EDIT_CELL_MERGED;
        cell->changed|=val && !strcmp(val,"restart") ? CELL_VMERGE_START : CELL_VMERGE_CONTINUE;
      }
      if (exr_edit_xml_child(x,pr,"hMerge")!=NONE) cell->unsupported|=EXR_EDIT_CELL_MERGED;
      if (exr_edit_xml_child(x,pr,"shd")!=NONE) cell->unsupported|=EXR_EDIT_CELL_SHADING;
      for (k=x->tree->nodes[j].first_child;k!=NONE;k=x->tree->nodes[k].next_sibling) {
        exr_edit_block *p;
        if (!x->tree->nodes[k].name || k==pr) continue;
        if (!exr_grow((void **)&blocks,&bc,cell->block_count+1,sizeof(*blocks))) goto done;
        cell->blocks=blocks; p=blocks+cell->block_count++; memset(p,0,sizeof(*p));
        template(x,k,&p->opaque_xml,&p->opaque_size);
        if (exr_edit_xml_word(x->tree->nodes+k,"p")) {
          exr_edit_run *runs; size_t nr;
          exr_edit_xml_para_props(x,exr_edit_xml_child(x,k,"pPr"),&p->props);
          status=exr_edit_xml_decode_runs(x,k,&runs,&nr); if (status) goto done;
          p->runs=runs; p->run_count=nr; status=EXR_MEMORY;
          for (l=0;l<nr;l++) if (runs[l].kind==EXR_EDIT_OPAQUE_RUN && memchr(runs[l].opaque_xml,'<',runs[l].opaque_size)) cell->unsupported|=EXR_EDIT_CELL_OPAQUE;
        } else {
          p->kind=EXR_EDIT_OPAQUE_BLOCK; cell->unsupported|=EXR_EDIT_CELL_OPAQUE;
          if (exr_edit_xml_word(x->tree->nodes+k,"tbl")) cell->unsupported|=EXR_EDIT_CELL_NESTED;
        }
      }
      if (cell->block_count>1) cell->unsupported|=EXR_EDIT_CELL_OPAQUE;
    }
    if (!row->cell_count) { status=EXR_OK; goto done; }
    if (columns>t->column_count) t->column_count=columns;
  }
  if (!t->row_count || t->column_count>16384) { status=EXR_OK; goto done; }
  if (grid!=NONE) {
    int32_t *widths=calloc(t->column_count,sizeof(*widths)); size_t col=0;
    if (!widths) goto done;
    t->column_widths=widths;
    for (i=0;i<t->column_count;i++) widths[i]=t->width_twips/(int32_t)t->column_count;
    if (grid!=NONE) for (i=x->tree->nodes[grid].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling)
      if (exr_edit_xml_word(x->tree->nodes+i,"gridCol")) {
        if (exr_edit_xml_integer(exr_edit_xml_wa(x->tree->nodes+i,"w"),&value) && value>=0) widths[col]=value;
        col++;
      }
  }
  *out=t; return EXR_OK;
done:
  exr_edit_table_decode_free(t); return status;
}

static int cell_block_write(exr_buffer *b,const source_xml *x,const exr_edit_block *p) {
  return p->kind==EXR_EDIT_PARAGRAPH ? exr_edit_xml_paragraph(b,x,p,NONE,NULL) :
    exr_append(b,p->opaque_xml,p->opaque_size);
}
static int cell_footnotes(const source_xml *x,const exr_edit_cell *c) {
  size_t i,j;
  if (!x->footnotes_changed) return 0;
  for (i=0;i<c->block_count;i++) for (j=0;j<c->blocks[i].run_count;j++)
    if (c->blocks[i].runs[j].kind==EXR_EDIT_FOOTNOTE) return 1;
  return 0;
}
static int cell_write(exr_buffer *b,const source_xml *x,const exr_edit_cell *c,size_t n) {
  size_t pr=exr_edit_xml_child(x,n,"tcPr"),i,at=x->spans[n].open,j=0;
  if (!exr_edit_xml_start(b,x,n,"tc")) return 0;
  if ((c->changed&CELL_PATCHED) || (!(c->changed&CELL_REPLACED) && cell_footnotes(x,c))) {
    /* Text edits and drawing deletion patch paragraphs in place, including protected
       cells. Nested tables, shading, comments and whitespace retain their bytes. */
    for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
      if (!exr_append(b,x->bytes+at,x->spans[i].start-at)) return 0;
      if (i==pr) { if (!exr_edit_xml_raw(b,x,i)) return 0; }
      else if (j>=c->block_count || !cell_block_write(b,x,c->blocks+j++)) return 0;
      at=x->spans[i].end;
    }
    if (j!=c->block_count || !exr_append(b,x->bytes+at,x->spans[n].close-at)) return 0;
  } else {
    if (!exr_edit_xml_raw(b,x,pr)) return 0;
    for (i=0;i<c->block_count;i++) if (!cell_block_write(b,x,c->blocks+i)) return 0;
  }
  return exr_edit_xml_end(b,x,n,"tc");
}
static size_t row_node(const source_xml *x,const exr_edit_row *r,size_t parent) {
  size_t n=r->source_index-1;
  if (x->tree && r->source_index && n<x->tree->node_count && x->tree->nodes[n].parent==parent &&
      exr_edit_xml_word(x->tree->nodes+n,"tr") && x->spans[n].end-x->spans[n].start==r->opaque_size &&
      !memcmp(x->bytes+x->spans[n].start,r->opaque_xml,r->opaque_size)) return n;
  return exr_edit_xml_locate(x,r->opaque_xml,r->opaque_size,"tr",parent);
}
static int row_write(exr_buffer *b,const source_xml *x,const exr_edit_row *r,size_t parent) {
  size_t i,j,n=row_node(x,r,parent),at,ci=0;
  int changed=n==NONE;
  for (i=0;i<r->cell_count;i++) if ((r->cells[i].changed&(CELL_REPLACED|CELL_PATCHED)) || cell_footnotes(x,r->cells+i)) changed=1;
  if (!changed) return exr_edit_xml_raw(b,x,n);
  if (!exr_edit_xml_start(b,x,n,"tr")) return 0;
  at=n==NONE ? 0 : x->spans[n].open;
  for (i=n==NONE ? NONE : x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
    if (!exr_append(b,x->bytes+at,x->spans[i].start-at)) return 0;
    if (exr_edit_xml_word(x->tree->nodes+i,"tc")) {
      const exr_edit_cell *c=r->cells+ci++;
      if (!(c->changed&(CELL_REPLACED|CELL_PATCHED)) && !cell_footnotes(x,c)) { if (!exr_edit_xml_raw(b,x,i)) return 0; }
      else if (!cell_write(b,x,c,i)) return 0;
    } else if (!exr_edit_xml_raw(b,x,i)) return 0;
    at=x->spans[i].end;
  }
  if (n!=NONE && !exr_append(b,x->bytes+at,x->spans[n].close-at)) return 0;
  if (n==NONE) for (i=0;i<r->cell_count;i++) {
    if (!exr_edit_xml_start(b,x,NONE,"tc")) return 0;
    for (j=0;j<r->cells[i].block_count;j++) if (!exr_edit_xml_paragraph(b,x,r->cells[i].blocks+j,NONE,NULL)) return 0;
    if (!r->cells[i].block_count && !exr_edit_xml_paragraph(b,x,&(exr_edit_block){0},NONE,NULL)) return 0;
    if (!exr_edit_xml_end(b,x,NONE,"tc")) return 0;
  }
  return exr_edit_xml_end(b,x,n,"tr");
}
static int table_prop(exr_buffer *b,const source_xml *x,const exr_edit_table *t,size_t n,int borders) {
  char num[32]; size_t i; static const char *edges[]={"top","left","bottom","right","insideH","insideV"};
  if (!borders) {
    attr_edit a[]={{"w",num},{"type",t->width_twips ? "dxa" : "auto"}}; snprintf(num,sizeof(num),"%d",t->width_twips);
    return exr_edit_xml_attrs(b,x,n,"tblW",a,2);
  }
  if (!exr_edit_xml_start(b,x,n,"tblBorders")) return 0;
  for (i=0;i<6;i++) {
    attr_edit a[]={{"val",t->borders==EXR_EDIT_BORDER_DOUBLE ? "double" : t->borders==EXR_EDIT_BORDER_SINGLE ? "single" : "nil"},{"sz","8"},{"color","auto"}};
    if (!exr_edit_xml_attrs(b,x,exr_edit_xml_child(x,n,edges[i]),edges[i],a,3)) return 0;
  }
  return exr_edit_xml_end(b,x,n,"tblBorders");
}
static int table_rank(const exr_node *n) {
  static const char *tags[]={"tblStyle","tblpPr","tblOverlap","bidiVisual","tblStyleRowBandSize",
    "tblStyleColBandSize","tblW","jc","tblCellSpacing","tblInd","tblBorders","shd",
    "tblLayout","tblCellMar","tblLook","tblCaption","tblDescription","tblPrChange"};
  size_t i;
  for (i=0;i<sizeof(tags)/sizeof(tags[0]);i++) if (exr_edit_xml_word(n,tags[i])) return (int)i;
  return -1;
}
static int table_pr(exr_buffer *b,const source_xml *x,const exr_edit_table *t,size_t n) {
  size_t i,at=n==NONE ? 0 : x->spans[n].open; unsigned seen=0,wanted=n==NONE ? 3u : t->changed;
  int missing_w=exr_edit_xml_child(x,n,"tblW")==NONE,missing_b=exr_edit_xml_child(x,n,"tblBorders")==NONE;
  if (n!=NONE && !t->changed) return exr_edit_xml_raw(b,x,n);
  if (!exr_edit_xml_start(b,x,n,"tblPr")) return 0;
  for (i=n==NONE ? NONE : x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
    unsigned bit=exr_edit_xml_word(x->tree->nodes+i,"tblW") ? 1u : exr_edit_xml_word(x->tree->nodes+i,"tblBorders") ? 2u : 0u;
    if (!exr_append(b,x->bytes+at,x->spans[i].start-at)) return 0;
    if ((wanted&1) && !(seen&1) && missing_w && table_rank(x->tree->nodes+i)>6) {
      if (!table_prop(b,x,t,NONE,0)) return 0;
      seen|=1;
    }
    if ((wanted&2) && !(seen&2) && missing_b && table_rank(x->tree->nodes+i)>10) {
      if (!table_prop(b,x,t,NONE,1)) return 0;
      seen|=2;
    }
    if (bit && (t->changed&bit)) { if (!table_prop(b,x,t,i,bit==2)) return 0; }
    else if (!exr_edit_xml_raw(b,x,i)) return 0;
    seen|=bit; at=x->spans[i].end;
  }
  if (!(seen&1) && (wanted&1) && !table_prop(b,x,t,NONE,0)) return 0;
  if (!(seen&2) && (wanted&2) && !table_prop(b,x,t,NONE,1)) return 0;
  return (n==NONE || exr_append(b,x->bytes+at,x->spans[n].close-at)) && exr_edit_xml_end(b,x,n,"tblPr");
}
static int grid_column(exr_buffer *b,const source_xml *x,const exr_edit_table *t,size_t n,size_t col) {
  char value[32]; attr_edit a={"w",value};
  snprintf(value,sizeof(value),"%d",t->column_widths ? t->column_widths[col] : t->width_twips/(int32_t)t->column_count);
  return exr_edit_xml_attrs(b,x,n,"gridCol",&a,1);
}
static int table_grid(exr_buffer *b,const source_xml *x,const exr_edit_table *t,size_t n) {
  size_t i,col=0,at=n==NONE ? 0 : x->spans[n].open;
  if (n!=NONE && !(t->changed&4u)) return exr_edit_xml_raw(b,x,n);
  if (!exr_edit_xml_start(b,x,n,"tblGrid")) return 0;
  for (i=n==NONE ? NONE : x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
    if (!exr_append(b,x->bytes+at,x->spans[i].start-at)) return 0;
    if (exr_edit_xml_word(x->tree->nodes+i,"gridCol")) {
      if (!grid_column(b,x,t,i,col++)) return 0;
    } else {
      if (!exr_edit_xml_raw(b,x,i)) return 0;
    }
    at=x->spans[i].end;
  }
  while (col<t->column_count) if (!grid_column(b,x,t,NONE,col++)) return 0;
  return (n==NONE || exr_append(b,x->bytes+at,x->spans[n].close-at)) && exr_edit_xml_end(b,x,n,"tblGrid");
}
int exr_edit_table_write(exr_buffer *b,const source_xml *x,const exr_edit_block *block) {
  const exr_edit_table *t=block->table; size_t n,i,at,ri=0,pr,grid;
  if (!t) return exr_append(b,block->opaque_xml,block->opaque_size);
  n=exr_edit_xml_locate(x,block->opaque_xml,block->opaque_size,"tbl",NONE);
  if (n!=NONE && !t->changed) {
    size_t count=0,j; int same=1;
    for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (exr_edit_xml_word(x->tree->nodes+i,"tr")) {
      if (count>=t->row_count || row_node(x,t->rows+count,n)!=i) { same=0; break; }
      for (j=0;j<t->rows[count].cell_count;j++) if ((t->rows[count].cells[j].changed&(CELL_REPLACED|CELL_PATCHED)) || cell_footnotes(x,t->rows[count].cells+j)) same=0;
      count++;
    }
    if (same && count==t->row_count) return exr_edit_xml_raw(b,x,n);
  }
  pr=exr_edit_xml_child(x,n,"tblPr"); grid=exr_edit_xml_child(x,n,"tblGrid");
  if (!exr_edit_xml_start(b,x,n,"tbl") || !table_pr(b,x,t,pr)) return 0;
  if (!table_grid(b,x,t,grid)) return 0;
  at=n==NONE ? 0 : x->spans[n].open;
  for (i=n==NONE ? NONE : x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
    if (!exr_append(b,x->bytes+at,x->spans[i].start-at)) return 0;
    if (exr_edit_xml_word(x->tree->nodes+i,"tr")) {
      /* Retain siblings (bookmarks, permission ranges, extensions) at their
         original row boundary. source_index distinguishes byte-identical rows. */
      while (ri<t->row_count && row_node(x,t->rows+ri,n)==NONE)
        if (!row_write(b,x,t->rows+ri++,n)) return 0;
      if (ri<t->row_count && row_node(x,t->rows+ri,n)==i) {
        if (!row_write(b,x,t->rows+ri++,n)) return 0;
        while (ri<t->row_count && row_node(x,t->rows+ri,n)==NONE)
          if (!row_write(b,x,t->rows+ri++,n)) return 0;
      }
    } else if (i!=pr && i!=grid && !exr_edit_xml_raw(b,x,i)) return 0;
    at=x->spans[i].end;
  }
  for (;ri<t->row_count;ri++) if (!row_write(b,x,t->rows+ri,n)) return 0;
  return (n==NONE || exr_append(b,x->bytes+at,x->spans[n].close-at)) && exr_edit_xml_end(b,x,n,"tbl");
}
