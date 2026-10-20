/* SPDX-License-Identifier: MIT */
#include "flow_internal.h"
#include "opentype_internal.h"

typedef struct {
  size_t node, row, column, colspan, rowspan;
  exr_layout *layout;
  exr_pager *cursor;
  float gap;
  int finished;
  float height,baseline,content_bottom,content_height;
  float border[4];
} table_cell;
typedef struct { float width; uint32_t color,rank; unsigned style; } table_edge;
struct exr_table_cursor {
  size_t *rows, row_count, row_capacity;
  table_cell *cells;
  size_t cell_count, cell_capacity, columns;
  float *heights, *positions, *baselines;
  size_t row, first, last, end;
  size_t header_rows, header_cells; /* Leading <thead> rows repeated per page. */
  size_t position;
  float x, width, min_height;
  float columns_at[65]; /* Logical inline edges, preserved by checkpoint clones. */
  int measured,fragmented;
  float consumed;
  size_t fragment_work;
  size_t node;
  table_edge *horizontal,*vertical;
  float border[4];
  int collapse;
};

static size_t span(const exr_node *node, const char *name, size_t limit) {
  const char *value = exr_node_attribute(node, name);
  char *end;
  unsigned long count;
  if (!value)
    return 1;
  count = strtoul(value, &end, 10);
  if (*end || end == value || !count)
    return 1;
  return count > limit ? limit : (size_t)count;
}
static int header_row(flow *f, size_t row) {
  size_t at = f->doc->nodes[row].parent;
  while (at != SIZE_MAX) {
    const char *name = exr_html_tag(f->doc, &f->doc->nodes[at]);
    if (!strcmp(name, "thead"))
      return 1;
    if (!strcmp(name, "table"))
      break;
    at = f->doc->nodes[at].parent;
  }
  return 0;
}
static int rows(flow *f, exr_table_cursor *t, size_t parent) {
  size_t child;
  for (child = f->doc->nodes[parent].first_child; child != SIZE_MAX;
       child = f->doc->nodes[child].next_sibling) {
    if (f->styles[child].display == EXR_CSS_NONE)
      continue;
    if (f->styles[child].display == EXR_CSS_ROW) {
      if (t->row_count >= 4096 ||
          !exr_grow((void **)&t->rows, &t->row_capacity, t->row_count + 1, sizeof(*t->rows)))
        return 0;
      t->rows[t->row_count++] = child;
    } else if (f->doc->nodes[child].kind != EXR_NODE_TABLE && !rows(f, t, child))
      return 0;
  }
  return 1;
}
void exr_table_free(exr_table_cursor *t) {
  size_t i;
  if (!t)
    return;
  for (i = 0; i < t->cell_count; i++) {
    exr_layout_free(t->cells[i].layout);
    exr_pager_free(t->cells[i].cursor);
  }
  free(t->cells);
  free(t->rows);
  free(t->heights);
  free(t->positions);
  free(t->baselines);
  free(t->horizontal);
  free(t->vertical);
  free(t);
}
static exr_status failed(flow *f, exr_status status) {
  if (!f->error || !f->error->message[0])
    return exr_fail(f->error, status, "Table layout limit exceeded");
  return status;
}
static float length_value(exr_length value,float width) {
  return value.value<0 ? 0 : value.percent ? value.value*width : value.value;
}
static int contains(const exr_document *doc,size_t ancestor,size_t node) {
  for(;node!=SIZE_MAX;node=doc->nodes[node].parent) if(node==ancestor) return 1;
  return 0;
}
static void edge_offer(table_edge *edge,const exr_style *s,int side,unsigned origin,
                       size_t row,size_t column,int horizontal,int rtl) {
  uint32_t order,rank; int style=s->border_style[side]; float width=s->border_width[side];
  if(!style) return;
  order=horizontal ? (uint32_t)((4096-row)*65+(rtl ? column : 64-column)) :
    (uint32_t)((rtl ? column : 64-column)*4097+4096-row);
  rank=style==2 ? UINT32_MAX : (origin<<20)+order;
  if(rank==UINT32_MAX || (edge->rank!=UINT32_MAX &&
      (width>edge->width || (width==edge->width && rank>edge->rank)))) {
    edge->width=style==2 ? 0 : width;
    edge->color=s->border_color[side]; edge->rank=rank; edge->style=(unsigned)style;
  }
}
static void perimeter(flow *f,exr_table_cursor *t,size_t node,unsigned origin,
                      size_t row,size_t column,size_t height,size_t width) {
  const exr_style *s=&f->styles[node]; size_t i; int rtl=f->styles[t->node].direction==EXR_DIRECTION_RTL;
  for(i=column;i<column+width;i++) {
    edge_offer(&t->horizontal[row*t->columns+i],s,0,origin,row,column,1,rtl);
    edge_offer(&t->horizontal[(row+height)*t->columns+i],s,2,origin,row,column,1,rtl);
  }
  for(i=row;i<row+height;i++) {
    edge_offer(&t->vertical[i*(t->columns+1)+column],s,3,origin,row,column,0,rtl);
    edge_offer(&t->vertical[i*(t->columns+1)+column+width],s,1,origin,row,column,0,rtl);
  }
}
static exr_status column_borders(flow *f,exr_table_cursor *t,size_t parent,size_t *column) {
  size_t child;
  for(child=f->doc->nodes[parent].first_child;child!=SIZE_MAX;child=f->doc->nodes[child].next_sibling) {
    const char *name=exr_html_tag(f->doc,&f->doc->nodes[child]); size_t before=*column,count;
    if(f->styles[child].display==EXR_CSS_NONE) continue;
    if(!strcmp(name,"colgroup")) {
      exr_status status=column_borders(f,t,child,column); if(status!=EXR_OK) return status;
      count=*column-before;
      if(!count) { count=span(&f->doc->nodes[child],"span",65); *column+=count; }
    } else if(!strcmp(name,"col")) { count=span(&f->doc->nodes[child],"span",65); *column+=count; }
    else continue;
    if(*column>t->columns) return exr_fail(f->error,EXR_LIMIT,"Invalid collapsed column range");
    if(!strcmp(name,"col")) { size_t i; for(i=0;i<count;i++) perimeter(f,t,child,3,0,before+i,t->row_count,1); }
    else perimeter(f,t,child,2,0,before,t->row_count,count);
  }
  return EXR_OK;
}
static exr_status collapsed_borders(flow *f,exr_table_cursor *t) {
  size_t i,j,k,column=0; exr_status status;
  t->horizontal=calloc((t->row_count+1)*t->columns,sizeof(*t->horizontal));
  t->vertical=calloc(t->row_count*(t->columns+1),sizeof(*t->vertical));
  if(!t->horizontal || !t->vertical) return EXR_MEMORY;
  perimeter(f,t,t->node,1,0,0,t->row_count,t->columns);
  status=column_borders(f,t,t->node,&column); if(status!=EXR_OK) return status;
  for(i=0;i<t->row_count;i++) {
    size_t ancestor;
    status=exr_control_cancel(&f->config->control,f->error); if(status!=EXR_OK) return status;
    perimeter(f,t,t->rows[i],5,i,0,1,t->columns);
    for(ancestor=f->doc->nodes[t->rows[i]].parent;ancestor!=t->node && ancestor!=SIZE_MAX;ancestor=f->doc->nodes[ancestor].parent) {
      const char *name=exr_html_tag(f->doc,&f->doc->nodes[ancestor]);
      if(strcmp(name,"thead") && strcmp(name,"tbody") && strcmp(name,"tfoot")) continue;
      if(i && contains(f->doc,ancestor,t->rows[i-1])) continue;
      for(j=i+1;j<t->row_count && contains(f->doc,ancestor,t->rows[j]);j++);
      perimeter(f,t,ancestor,4,i,0,j-i,t->columns);
    }
  }
  for(i=0;i<t->cell_count;i++) {
    const table_cell *c=&t->cells[i];
    perimeter(f,t,c->node,6,c->row,c->column,c->rowspan,c->colspan);
  }
  /* Spanning cells remove grid lines, including borders supplied by rows/columns. */
  for(i=0;i<t->cell_count;i++) {
    const table_cell *c=&t->cells[i];
    for(j=c->row+1;j<c->row+c->rowspan;j++) for(k=c->column;k<c->column+c->colspan;k++)
      t->horizontal[j*t->columns+k]=(table_edge){0,0,UINT32_MAX,0};
    for(j=c->row;j<c->row+c->rowspan;j++) for(k=c->column+1;k<c->column+c->colspan;k++)
      t->vertical[j*(t->columns+1)+k]=(table_edge){0,0,UINT32_MAX,0};
  }
  for(i=0;i<t->cell_count;i++) {
    table_cell *c=&t->cells[i];
    for(j=c->column;j<c->column+c->colspan;j++) {
      c->border[0]=fmaxf(c->border[0],t->horizontal[c->row*t->columns+j].width/2);
      c->border[2]=fmaxf(c->border[2],t->horizontal[(c->row+c->rowspan)*t->columns+j].width/2);
    }
    for(j=c->row;j<c->row+c->rowspan;j++) {
      c->border[3]=fmaxf(c->border[3],t->vertical[j*(t->columns+1)+c->column].width/2);
      c->border[1]=fmaxf(c->border[1],t->vertical[j*(t->columns+1)+c->column+c->colspan].width/2);
    }
  }
  for(i=0;i<t->columns;i++) {
    t->border[0]=fmaxf(t->border[0],t->horizontal[i].width/2);
    t->border[2]=fmaxf(t->border[2],t->horizontal[t->row_count*t->columns+i].width/2);
  }
  for(i=0;i<t->row_count;i++) {
    t->border[3]=fmaxf(t->border[3],t->vertical[i*(t->columns+1)].width/2);
    t->border[1]=fmaxf(t->border[1],t->vertical[i*(t->columns+1)+t->columns].width/2);
  }
  t->x+=t->border[3]; t->width-=t->border[3]+t->border[1];
  t->min_height=fmaxf(0,t->min_height-t->border[0]-t->border[2]);
  return EXR_OK;
}
static flow cell_flow(flow *f,const exr_table_cursor *t,const table_cell *c) {
  flow result=*f;
  if(t->collapse) {
    result.border_override=1; result.border_node=c->node;
    memcpy(result.border_insets,c->border,sizeof(c->border));
  }
  return result;
}
static void hint(float widths[64],unsigned kinds[64],size_t first,size_t count,float desired) {
  size_t i,free_columns=0; float total=0;
  for(i=first;i<first+count;i++) total+=widths[i];
  for(i=first;i<first+count;i++) if(kinds[i]<2) free_columns++;
  if(desired>total) for(i=first;i<first+count;i++) if(!free_columns || kinds[i]<2) {
    widths[i]+=(desired-total)/(float)(free_columns ? free_columns : count);
    if(kinds[i]<1) kinds[i]=1;
  }
}
static exr_status column_hints(flow *f,exr_table_cursor *t,size_t parent,exr_length inherited,float widths[64],size_t *column) {
  size_t child;
  for(child=f->doc->nodes[parent].first_child;child!=SIZE_MAX;child=f->doc->nodes[child].next_sibling) {
    const exr_node *n=&f->doc->nodes[child]; const char *name=exr_html_tag(f->doc,n);
    exr_style style=exr_flow_style(&f->styles[child],f->writing_mode); exr_length width=style.width.value<0 ? inherited : style.width;
    if(style.display==EXR_CSS_NONE) continue;
    if(!strcmp(name,"colgroup")) {
      size_t before=*column; exr_status status=column_hints(f,t,child,width,widths,column);
      if(status!=EXR_OK) return status;
      if(*column!=before) continue;
    } else if(strcmp(name,"col")) continue;
    {
      size_t count=span(n,"span",65),i;
      if(count>64-*column) return exr_fail(f->error,EXR_LIMIT,"Table column declarations exceed 64 columns");
      for(i=0;i<count;i++) widths[(*column)++]=length_value(width,t->width);
    }
  }
  return EXR_OK;
}
/* Exact min/max-content scan for a plain Latin cell without OpenType shaping.
   Rich trees/scripts keep the general two-pass algorithm below. The pair cache
   is bounded independently of the amount of text. */
static exr_status plain_widths(flow *f,const exr_table_cursor *t,const table_cell *cell,
                                float *minimum,float *maximum,int *handled) {
  const exr_node *node=&f->doc->nodes[cell->node],*text;
  const exr_style *style;
  struct { exr_face *face; uint32_t glyph; float advance; int ready; } metrics[128]={{0}};
  size_t child=node->first_child,at,order[32],ordered,i;
  float *kern=NULL,word=0,first_indent,left,right;
  unsigned char *known=NULL;unsigned previous=0,word_previous=0;int first=1;
  double total;exr_status status=EXR_OK;
  *handled=0;
  if(f->intrinsic || f->writing_mode!=EXR_WRITING_HORIZONTAL_TB || f->auto_bases || child==SIZE_MAX) return EXR_OK;
  text=&f->doc->nodes[child];style=&f->styles[child];
  if(text->kind!=EXR_NODE_TEXT || text->next_sibling!=SIZE_MAX || text->start==SIZE_MAX ||
     text->end<=text->start || style->display!=EXR_CSS_INLINE || style->float_side ||
     style->direction==EXR_DIRECTION_RTL || style->writing_mode!=EXR_WRITING_HORIZONTAL_TB ||
     (f->hyphenator && style->hyphens==EXR_HYPHENS_AUTO)) return EXR_OK;
  for(i=0;i<f->font->count;i++) if(exr_ot_present(&f->font->faces[i]) || f->font->faces[i].bitmap_only) return EXR_OK;
  for(at=text->start;at<text->end;at++) {
    unsigned char c=(unsigned char)f->doc->text[at];
    if((at&1023)==0 && exr_control_cancel(&f->config->control,f->error)!=EXR_OK) return EXR_CANCELLED;
    /* Whitespace trimming/collapsing belongs to the general line algorithm. */
    if(c==' ') {
      if(at==text->start || at+1==text->end || f->doc->text[at-1]==' ') return EXR_OK;
      continue;
    }
    if((c>='A' && c<='Z') || (c>='a' && c<='z') || (c>='0' && c<='9')) continue;
    if(!c || !strchr(".,!?:;",c) || (at+1<text->end && f->doc->text[at+1]!=' ')) return EXR_OK;
  }
  left=length_value(f->styles[cell->node].padding[3],t->width)+(t->collapse ? cell->border[3] : exr_border_extent(&f->styles[cell->node],3));
  right=length_value(f->styles[cell->node].padding[1],t->width)+(t->collapse ? cell->border[1] : exr_border_extent(&f->styles[cell->node],1));
  if(left+right+1>t->width) return EXR_OK;
  kern=calloc(128*128,sizeof(*kern));known=calloc(128*128,1);
  if(!kern || !known) { free(kern);free(known);return EXR_OK; }
  *handled=1;*minimum=left+right;
  first_indent=fmaxf(0,f->styles[cell->node].indent);total=first_indent;
  ordered=exr_font_order(f->font,style->family,style->flags,text->chapter,order);
  for(at=text->start;at<text->end;at++) {
    unsigned c=(unsigned char)f->doc->text[at];float spacing=0,word_spacing=0;
    if(++f->assets->work_glyphs>EXR_MAX_ITEMS) { status=exr_fail(f->error,EXR_LIMIT,"Text work limit exceeded");break; }
    if(!(f->assets->work_glyphs&255)) {
      status=exr_control_poll(&f->config->control,EXR_STAGE_LAYOUT,at,f->doc->size,f->error);
      if(status!=EXR_OK) break;
    }
    if(!metrics[c].ready) {
      size_t face=0;
      for(i=0;i<ordered;i++) if(exr_font_has_glyph(f->font,order[i],c)) { face=order[i];break; }
      metrics[c].face=&f->font->faces[face];metrics[c].glyph=FT_Get_Char_Index(metrics[c].face->face,c);
      if(exr_font_size(metrics[c].face,style->font_size) ||
         exr_measure(metrics[c].face,metrics[c].glyph,style->flags&~metrics[c].face->style_flags,&metrics[c].advance)) {
        status=exr_fail(f->error,EXR_FONT,"Cannot measure intrinsic cell font");break;
      }
      metrics[c].ready=1;
    }
    if(previous && metrics[previous].face==metrics[c].face) {
      size_t pair=previous*128+c;
      if(!known[pair]) { kern[pair]=exr_kern(metrics[c].face,metrics[previous].glyph,metrics[c].glyph);known[pair]=1; }
      spacing=kern[pair];
    }
    total+=metrics[c].advance+spacing;
    if(c==' ') {
      *minimum=fmaxf(*minimum,left+word+(first ? first_indent : 0)+right);
      if(word_previous) first=0;
      word=0;word_previous=0;
    } else {
      if(word_previous && metrics[word_previous].face==metrics[c].face) word_spacing=kern[word_previous*128+c];
      word+=metrics[c].advance+word_spacing;word_previous=c;
    }
    previous=c;
  }
  if(status==EXR_OK) {
    *minimum=fmaxf(*minimum,left+word+(first ? first_indent : 0)+right);
    *maximum=(float)(left+total+right);
    if(!isfinite(*maximum) || *maximum>1e9) status=exr_fail(f->error,EXR_LIMIT,"Intrinsic table width exceeds coordinate budget");
  }
  free(kern);free(known);return status;
}
static exr_status column_widths(flow *f,exr_table_cursor *t,size_t node) {
  float widths[64]={0},preferred[64]={0},total=0,available=t->width; unsigned kinds[64]={0},lowest=2;
  size_t column=0,i,n,automatic=0; exr_status status;
  exr_style table=exr_flow_style(&f->styles[node],f->writing_mode);
  int fixed=table.table_fixed && table.width.value>=0 && (!f->intrinsic || !table.width.percent);
  exr_length empty={-1,0};
  status=column_hints(f,t,node,empty,widths,&column); if(status!=EXR_OK) return status;
  if(column>t->columns && t->row_count) t->columns=column;
  if(!t->columns) return EXR_OK;
  if(t->width<(float)t->columns) return exr_fail(f->error,EXR_LIMIT,"Table has less than one pixel per column");
  for(i=0;i<t->columns;i++) { if(widths[i]>0) kinds[i]=2; preferred[i]=widths[i]; }
  for(n=1;n<=t->columns;n++) for(i=0;i<t->cell_count;i++) {
    const table_cell *cell=&t->cells[i]; exr_style style; float width=0,minimum=0,maximum=0; flow local=cell_flow(f,t,cell);
    if(cell->colspan!=n) continue;
    if(fixed && cell->row) continue;
    status=exr_control_cancel(&f->config->control,f->error); if(status!=EXR_OK) return status;
    style=exr_flow_style(&f->styles[cell->node],f->writing_mode);
    if(style.width.value>=0) width=length_value(style.width,t->width)+length_value(style.padding[1],t->width)+length_value(style.padding[3],t->width)+
      (t->collapse ? cell->border[1]+cell->border[3] : exr_border_extent(&style,1)+exr_border_extent(&style,3));
    width=fminf(width,t->width*64);
    if(!fixed) {
      int handled=0;
      status=plain_widths(&local,t,cell,&minimum,&maximum,&handled);if(status!=EXR_OK) return status;
      if(!handled) {
        if(f->intrinsic!=2) { status=exr_flow_intrinsic(&local,cell->node,t->width,1,&minimum); if(status!=EXR_OK) return status; }
        if(f->intrinsic!=1) { status=exr_flow_intrinsic(&local,cell->node,t->width,2,&maximum); if(status!=EXR_OK) return status; }
      }
    }
    if(!fixed) {
      /* The cell cursor needs one content pixel in addition to its insets,
         including an otherwise empty collapsed-border column. */
      float insets=length_value(style.padding[1],t->width)+length_value(style.padding[3],t->width)+
        (t->collapse ? cell->border[1]+cell->border[3] : exr_border_extent(&style,1)+exr_border_extent(&style,3));
      minimum=fmaxf(minimum,insets+1);
    }
    minimum=fmaxf(minimum,width); maximum=fmaxf(fmaxf(minimum,maximum),width);
    if(n==1) {
      widths[cell->column]=fmaxf(widths[cell->column],minimum);
      preferred[cell->column]=fmaxf(preferred[cell->column],maximum);
      if(width>0) kinds[cell->column]=2;
    } else {
      hint(widths,kinds,cell->column,cell->colspan,minimum);
      for(column=0;column<t->columns;column++) preferred[column]=fmaxf(preferred[column],widths[column]);
      hint(preferred,kinds,cell->column,cell->colspan,maximum);
    }
  }
  {
    double min_total=0,max_total=0;
    for(i=0;i<t->columns;i++) {
      widths[i]=fmaxf(1,widths[i]); preferred[i]=fmaxf(widths[i],preferred[i]);
      min_total+=widths[i]; max_total+=preferred[i];
    }
    if(f->intrinsic) {
      /* Nested tables expose their measured width directly. They do not lay
         out all cells a third time just to obtain the same intrinsic result. */
      f->intrinsic_extent=fmax(f->intrinsic_extent,t->x+(f->intrinsic==1 ? min_total : max_total)+t->border[1]+f->inline_end_inset);
      t->row=t->row_count; return EXR_OK;
    }
    if(!fixed && table.width.value<0) {
      float shrink=(float)fmin(t->width,max_total);
      if(table.margin[3].value<0) t->x+=(t->width-shrink)/(table.margin[1].value<0 ? 2 : 1);
      t->width=available=shrink;
    }
    if(!fixed && min_total<available && max_total>min_total) {
      double fraction=fmin(1,(available-min_total)/(max_total-min_total));
      for(i=0;i<t->columns;i++) widths[i]+=(float)((preferred[i]-widths[i])*fraction);
    }
  }
  for(i=0;i<t->columns;i++) { total+=widths[i]; if(kinds[i]<lowest) lowest=kinds[i]; }
  for(i=0;i<t->columns;i++) if(kinds[i]==lowest) automatic++;
  if(lowest<2 && total<available) {
    double weights=0;
    for(i=0;i<t->columns;i++) if(kinds[i]==lowest) weights+=fixed ? 1 : preferred[i];
    for(i=0;i<t->columns;i++) if(kinds[i]==lowest)
      widths[i]+=(float)((available-total)*(weights ? (fixed ? 1 : preferred[i])/weights : 1.0/automatic));
  }
  /* Fit overconstrained hints while keeping every column at least one pixel.
     Lock tiny columns before redistributing, at most one pass per column. */
  {
    unsigned locked[64]={0}; size_t count=t->columns;
    for(;;) {
      int changed=0; float scale; total=0;
      for(i=0;i<t->columns;i++) if(!locked[i]) total+=widths[i];
      scale=total ? available/total : available/(float)count;
      for(i=0;i<t->columns;i++) if(!locked[i] && (total ? widths[i]*scale : scale)<1) {
        locked[i]=1; widths[i]=1; available-=1; count--; changed=1;
      }
      if(!changed || !count) {
        if(count) for(i=0;i<t->columns;i++) if(!locked[i]) widths[i]=total ? widths[i]*available/total : available/(float)count;
        break;
      }
    }
  }
  for(i=0;i<t->columns;i++) t->columns_at[i+1]=fmaxf(t->columns_at[i]+1,
    fminf(t->width-(float)(t->columns-i-1),t->columns_at[i]+widths[i]));
  t->columns_at[t->columns]=t->width;
  /* Across float exponent boundaries, rounded (left + 1) can leave a delta
     just below one pixel. Anchor the final edge and enforce the floor backwards. */
  for(i=t->columns;i>1;i--) t->columns_at[i-1]=fminf(t->columns_at[i-1],t->columns_at[i]-1);
  return EXR_OK;
}
size_t exr_table_float_cursors(const exr_table_cursor *t) {
  size_t i,count=0;if(!t) return 0;
  for(i=0;i<t->cell_count && count<=EXR_MAX_FLOATS;i++) count+=exr_flow_cursor_floats(t->cells[i].cursor);
  return count;
}
size_t exr_table_memory_size(const exr_table_cursor *t) {
  size_t total, i;
  if (!t) return 0;
  total = sizeof(*t) + t->row_capacity*sizeof(*t->rows) + t->cell_capacity*sizeof(*t->cells);
  if (t->heights) total += (3*t->row_count + 1)*sizeof(float);
  if(t->horizontal) total+=((t->row_count+1)*t->columns+t->row_count*(t->columns+1))*sizeof(table_edge);
  for (i = 0; i < t->cell_count; i++) {
    size_t bytes = exr_layout_memory_size(t->cells[i].layout);
    if (bytes > SIZE_MAX - total) return SIZE_MAX;
    total += bytes;
    bytes=exr_flow_cursor_size(t->cells[i].cursor);
    if(bytes>SIZE_MAX-total) return SIZE_MAX;
    total+=bytes;
  }
  return total;
}
exr_table_cursor *exr_table_clone(const exr_table_cursor *t) {
  exr_table_cursor *copy;
  size_t i;
  if (!t) return NULL;
  copy = malloc(sizeof(*copy));
  if (!copy) return NULL;
  *copy = *t;
  copy->rows = NULL; copy->cells = NULL; copy->heights = copy->positions = copy->baselines = NULL;
  copy->horizontal=copy->vertical=NULL;
  copy->cell_count = 0;
  if (t->row_count) {
    copy->rows = malloc(t->row_count*sizeof(*t->rows));
    if (!copy->rows) goto bad;
    memcpy(copy->rows, t->rows, t->row_count*sizeof(*t->rows));
  }
  if (t->cell_count) {
    copy->cells = malloc(t->cell_count*sizeof(*t->cells));
    if (!copy->cells) goto bad;
    memcpy(copy->cells, t->cells, t->cell_count*sizeof(*t->cells));
    copy->cell_count = t->cell_count;
    for (i = 0; i < copy->cell_count; i++) { exr_layout_ref(copy->cells[i].layout);copy->cells[i].cursor=NULL; }
    for (i = 0; i < copy->cell_count; i++) if(t->cells[i].cursor) {
      copy->cells[i].cursor=exr_flow_cursor_clone(t->cells[i].cursor);
      if(!copy->cells[i].cursor) goto bad;
    }
  }
  if (t->heights) {
    copy->heights = malloc(t->row_count*sizeof(*t->heights));
    copy->positions = malloc((t->row_count + 1)*sizeof(*t->positions));
    copy->baselines = malloc(t->row_count*sizeof(*t->baselines));
    if (!copy->heights || !copy->positions || !copy->baselines) goto bad;
    memcpy(copy->heights, t->heights, t->row_count*sizeof(*t->heights));
    memcpy(copy->positions, t->positions, (t->row_count + 1)*sizeof(*t->positions));
    memcpy(copy->baselines, t->baselines, t->row_count*sizeof(*t->baselines));
  }
  if(t->horizontal) {
    size_t h=(t->row_count+1)*t->columns*sizeof(table_edge),v=t->row_count*(t->columns+1)*sizeof(table_edge);
    copy->horizontal=malloc(h); copy->vertical=malloc(v);
    if(!copy->horizontal || !copy->vertical) goto bad;
    memcpy(copy->horizontal,t->horizontal,h); memcpy(copy->vertical,t->vertical,v);
  }
  copy->row_capacity = copy->row_count; copy->cell_capacity = copy->cell_count;
  return copy;
bad:
  exr_table_free(copy); return NULL;
}
exr_status exr_table_create(flow *f, size_t node, float x, float width,
                            exr_table_cursor **out) {
  exr_table_cursor *t;
  size_t occupied[64] = {0}, i;
  exr_status status = EXR_OK;
  *out = NULL;
  if (f->unit_depth >= 8)
    return exr_fail(f->error, EXR_LIMIT, "Nested flow unit limit exceeded");
  t = calloc(1, sizeof(*t));
  if (!t)
    return exr_fail(f->error, EXR_MEMORY, "Table cursor allocation failed");
  t->x = x;
  t->width = width;
  t->node=node; t->collapse=f->styles[node].border_collapse;
  { exr_style style=exr_flow_style(&f->styles[node],f->writing_mode);
    t->min_height=length_value(style.height,f->unit_assigned && node==f->unit_node ? f->unit_block_reference : exr_flow_room(f));
  }
  if (!rows(f, t, node)) {
    status = EXR_LIMIT;
    goto bad;
  }
  for (i = 0; i < t->row_count; i++) {
    size_t child, column = 0;
    for (child = f->doc->nodes[t->rows[i]].first_child; child != SIZE_MAX;
         child = f->doc->nodes[child].next_sibling) {
      table_cell *c;
      size_t colspan, rowspan, k;
      if (f->styles[child].display != EXR_CSS_CELL)
        continue;
      colspan = span(&f->doc->nodes[child], "colspan", 65);
      rowspan = span(&f->doc->nodes[child], "rowspan", t->row_count - i);
      for (;;) {
        while (column < 64 && occupied[column] > i)
          column++;
        if (colspan > 64 - column) {
          status = EXR_LIMIT;
          goto bad;
        }
        for (k = 0; k < colspan && occupied[column + k] <= i; k++) {
        }
        if (k == colspan)
          break;
        column += k + 1;
      }
      if (t->cell_count >= 4096 ||
          !exr_grow((void **)&t->cells, &t->cell_capacity, t->cell_count + 1,
                    sizeof(*t->cells))) {
        status = EXR_LIMIT;
        goto bad;
      }
      c = &t->cells[t->cell_count++];
      *c = (table_cell){0};
      c->node = child;
      c->row = i;
      c->column = column;
      c->colspan = colspan;
      c->rowspan = rowspan;
      for (k = 0; k < colspan; k++)
        occupied[column + k] = i + rowspan;
      column += colspan;
      if (column > t->columns)
        t->columns = column;
    }
  }
  if(t->collapse && t->row_count) {
    float hints[64]={0}; size_t count=0; exr_length empty={-1,0};
    status=column_hints(f,t,node,empty,hints,&count); if(status!=EXR_OK) goto bad;
    if(count>t->columns) t->columns=count;
    if(t->columns) { status=collapsed_borders(f,t); if(status!=EXR_OK) goto bad; }
  }
  while (t->header_rows < t->row_count && header_row(f, t->rows[t->header_rows]))
    t->header_rows++;
  while (t->header_cells < t->cell_count &&
         t->cells[t->header_cells].row + t->cells[t->header_cells].rowspan <= t->header_rows)
    t->header_cells++;
  status=column_widths(f,t,node); if(status!=EXR_OK) goto bad;
  if (t->columns && t->row_count) {
    t->heights = calloc(t->row_count, sizeof(*t->heights));
    t->positions = calloc(t->row_count + 1, sizeof(*t->positions));
    t->baselines = calloc(t->row_count, sizeof(*t->baselines));
    if (!t->heights || !t->positions || !t->baselines) {
      status = EXR_MEMORY;
      goto bad;
    }
  }
  *out = t;
  return EXR_OK;
bad:
  exr_table_free(t);
  return failed(f, status);
}
static int repeats_header(const flow *f, const exr_table_cursor *t) {
  return f->paginate && t->header_rows > 0 && t->row > 0 && t->row >= t->header_rows;
}
static float header_height(const exr_table_cursor *t) {
  return t->header_rows ? t->positions[t->header_rows] - t->positions[0] : 0;
}
static float boundary(const exr_table_cursor *t,size_t row);
static exr_status measure(flow *f, exr_table_cursor *t) {
  size_t i, j,retained=t->first;
  exr_status status;
  int probe=f->paginate,exact=0,tall=0;
  float full_room=fmaxf(exr_flow_room(f),f->unit_assigned ? f->unit_block_reference : 0);
  /* A repeated header occupies the top of every continuation page, so the
     probed row group must fit in what is left. */
  if (repeats_header(f, t))
    full_room = fmaxf(1, full_room - header_height(t) - boundary(t,0) -
                         boundary(t,t->header_rows));
  t->end = t->row + 1;
  t->last = t->first;
  /* Cells are in row order. Extending the end discovers the entire rowspan group. */
  while (t->last < t->cell_count && t->cells[t->last].row < t->end) {
    table_cell *c = &t->cells[t->last++];
    if (c->row + c->rowspan > t->end)
      t->end = c->row + c->rowspan;
  }
  for(i=t->row;i<t->end;i++) {
    exr_style style=exr_flow_style(&f->styles[t->rows[i]],f->writing_mode);
    float minimum=style.height.percent && !t->min_height ? 0 : length_value(style.height,t->min_height);
    t->heights[i]=fmaxf(t->heights[i],fmaxf(minimum,t->min_height/(float)t->row_count));
  }
  /* Probe short cells once. Only unfinished aligned groups need exact full
     heights; those measurements retain geometry rather than full glyph arrays. */
  for(i=t->first;i<t->last;i++) if(f->styles[t->cells[i].node].vertical_align==EXR_CELL_MIDDLE ||
      f->styles[t->cells[i].node].vertical_align==EXR_CELL_BOTTOM) exact=1;
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    flow local=cell_flow(f,t,c);
    if(probe && !(exact && tall)) {
      exr_pager *cursor=NULL;
      status=exr_flow_fragment(&local,NULL,c->node,t->columns_at[c->column+c->colspan]-t->columns_at[c->column],full_room,0,0,&cursor,&c->layout);
      if(status==EXR_OK) {
        int finished=exr_flow_cursor_finished(cursor);
        c->height=c->layout ? c->layout->flow_block : 0;
        if(!finished) {
          if(f->defer_tall_rows) status=EXR_FRAGMENT_SMALL;
          else if(exact) {
            exr_layout_free(c->layout);c->layout=NULL;local.measure_height=1;
            status=exr_flow_unit(&local,c->node,t->columns_at[c->column+c->colspan]-t->columns_at[c->column],&c->layout,&c->height);
            tall=1;
          } else c->height=fmaxf(c->height,full_room+1);
        }
      }
      exr_pager_free(cursor);
      if(status==EXR_FRAGMENT_SMALL && !f->fragment_probe) status=exr_fail(f->error,EXR_LIMIT,"Table cell contains an item larger than a page");
    } else {
      if(probe && exact && tall) local.measure_height=1;
      status = exr_flow_unit(&local, c->node, t->columns_at[c->column+c->colspan]-t->columns_at[c->column],
                           &c->layout, &c->height);
    }
    if (status != EXR_OK) return status;
    if(!c->layout) {
      c->layout=calloc(1,sizeof(*c->layout));if(!c->layout) return exr_fail(f->error,EXR_MEMORY,"Empty table cell allocation failed");
      c->layout->writing_mode=f->writing_mode;
    }
    {
      exr_style style=exr_flow_style(&f->styles[c->node],f->writing_mode);
      float width=t->columns_at[c->column+c->colspan]-t->columns_at[c->column];
      float before=length_value(style.padding[0],width)+(t->collapse ? c->border[0] : exr_border_extent(&style,0));
      float after=length_value(style.padding[2],width)+(t->collapse ? c->border[2] : exr_border_extent(&style,2));
      if(style.height.value>=0 && (!style.height.percent || t->min_height>0))
        c->height=fmaxf(c->height,length_value(style.height,t->min_height)+before+after);
      c->content_height=c->layout->flow_block;
      c->content_bottom=fmaxf(0,c->content_height-after);
      c->baseline=c->layout->has_baseline ? c->layout->first_baseline : c->content_bottom;
      if(style.vertical_align==EXR_CELL_BASELINE) t->baselines[c->row]=fmaxf(t->baselines[c->row],c->baseline);
    }
    if(probe && exact) {
      float minimum=0;
      if(c->rowspan==1) t->heights[c->row]=fmaxf(t->heights[c->row],c->height);
      for(j=t->row;j<t->end;j++) minimum+=t->heights[j];
      if(c->height>full_room+.01f || minimum>full_room+.01f) tall=1;
      if(tall) for(;retained<=i;retained++) { exr_layout_free(t->cells[retained].layout);t->cells[retained].layout=NULL; }
    }
    if (f->doc->nodes[c->node].end != SIZE_MAX && f->doc->nodes[c->node].end > t->position)
      t->position = f->doc->nodes[c->node].end;
  }
  for(i=t->first;i<t->last;i++) {
    table_cell *c=&t->cells[i];
    float shift=f->styles[c->node].vertical_align==EXR_CELL_BASELINE ? fmaxf(0,t->baselines[c->row]-c->baseline) : 0;
    if(c->rowspan==1) t->heights[c->row]=fmaxf(t->heights[c->row],fmaxf(c->height,c->content_height+shift));
  }
  /* Keep the eager algorithm's pass order, including overlapping spanning cells. */
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    float total = 0;
    for (j = c->row; j < c->row + c->rowspan; j++)
      total += t->heights[j];
    { float shift=f->styles[c->node].vertical_align==EXR_CELL_BASELINE ? fmaxf(0,t->baselines[c->row]-c->baseline) : 0;
      float needed=fmaxf(c->height,c->content_height+shift);
      if(total<needed) t->heights[c->row+c->rowspan-1]+=needed-total;
    }
  }
  /* Accumulate positions globally to preserve the eager float arithmetic. */
  for (i = t->row; i < t->end; i++)
    t->positions[i + 1] = t->positions[i] + t->heights[i];
  t->measured = 1;
  return EXR_OK;
}
size_t exr_table_position(const exr_table_cursor *t) { return t ? t->position : 0; }
void exr_table_geometry(const exr_table_cursor *t,float *x,float *width) { *x=t->x-t->border[3]; *width=t->width+t->border[3]+t->border[1]; }
static float cell_inset(flow *f,const exr_table_cursor *t,const table_cell *c) {
  float allocated=t->positions[c->row+c->rowspan]-t->positions[c->row];
  float room=fmaxf(0,allocated-c->content_height);
  switch(f->styles[c->node].vertical_align) {
    case EXR_CELL_TOP: return 0;
    case EXR_CELL_MIDDLE: return room/2;
    case EXR_CELL_BOTTOM: return room;
    default: return fminf(room,fmaxf(0,t->baselines[c->row]-c->baseline));
  }
}
static float boundary(const exr_table_cursor *t,size_t row) {
  size_t i; float half=0;
  if(t->collapse) for(i=0;i<t->columns;i++) half=fmaxf(half,t->horizontal[row*t->columns+i].width/2);
  return half;
}
static exr_status paint_edge(flow *f,const exr_table_cursor *t,const table_edge *edge,float x,float y,float w,float h) {
  return exr_flow_edge(f,t->node,edge->style,edge->width,edge->color,x,y,w,h);
}
static exr_status paint_cell_sides(flow *f,const exr_table_cursor *t,const table_cell *cell,
                                   float y,float height) {
  exr_style style=exr_flow_style(&f->styles[cell->node],f->writing_mode);
  float x=t->x+t->columns_at[cell->column];
  float w=t->columns_at[cell->column+cell->colspan]-t->columns_at[cell->column];
  float top=exr_border_extent(&style,0),right=exr_border_extent(&style,1);
  float bottom=exr_border_extent(&style,2),left=exr_border_extent(&style,3);
  float inner=fmaxf(0,height-top-bottom);
  exr_status status;
  if(top>0) { status=exr_flow_edge(f,cell->node,style.border_style[0],top,style.border_color[0],x,y,w,top); if(status!=EXR_OK) return status; }
  if(bottom>0) { status=exr_flow_edge(f,cell->node,style.border_style[2],bottom,style.border_color[2],x,y+height-bottom,w,bottom); if(status!=EXR_OK) return status; }
  if(left>0) { status=exr_flow_edge(f,cell->node,style.border_style[3],left,style.border_color[3],x,y+top,left,inner); if(status!=EXR_OK) return status; }
  if(right>0) { status=exr_flow_edge(f,cell->node,style.border_style[1],right,style.border_color[1],x+w-right,y+top,right,inner); if(status!=EXR_OK) return status; }
  return EXR_OK;
}
static exr_status paint_borders(flow *f,const exr_table_cursor *t,int top) {
  size_t r,c; exr_status status;
  if(!t->collapse) {
    size_t i;
    for(i=t->first;i<t->last;i++) {
      const table_cell *cell=&t->cells[i];
      if(exr_border_uniform(&f->styles[cell->node])) continue;
      status=paint_cell_sides(f,t,cell,f->y+t->positions[cell->row]-t->positions[t->row],
        t->positions[cell->row+cell->rowspan]-t->positions[cell->row]);
      if(status!=EXR_OK) return status;
    }
    return EXR_OK;
  }
  for(r=t->row+!top;r<=t->end;r++) for(c=0;c<t->columns;c++) {
    const table_edge *edge=&t->horizontal[r*t->columns+c];
    float left=0,right=0;
    if(r) {
      left=t->vertical[(r-1)*(t->columns+1)+c].width/2;
      right=t->vertical[(r-1)*(t->columns+1)+c+1].width/2;
    }
    if(r<t->row_count) {
      left=fmaxf(left,t->vertical[r*(t->columns+1)+c].width/2);
      right=fmaxf(right,t->vertical[r*(t->columns+1)+c+1].width/2);
    }
    status=paint_edge(f,t,edge,t->x+t->columns_at[c]-left,
      f->y+t->positions[r]-t->positions[t->row]-edge->width/2,
      t->columns_at[c+1]-t->columns_at[c]+left+right,edge->width);
    if(status!=EXR_OK) return status;
  }
  for(r=t->row;r<t->end;r++) for(c=0;c<=t->columns;c++) {
    const table_edge *edge=&t->vertical[r*(t->columns+1)+c];
    status=paint_edge(f,t,edge,t->x+t->columns_at[c]-edge->width/2,
      f->y+t->positions[r]-t->positions[t->row],edge->width,t->heights[r]);
    if(status!=EXR_OK) return status;
  }
  return EXR_OK;
}
/* Re-lay the <thead> rows at the top of a continuation page. Cell layouts are
   released after each page fragment, so the header is measured again here. */
static exr_status repeat_header(flow *f, exr_table_cursor *t) {
  size_t i;
  float height=header_height(t),top=boundary(t,0),bottom=boundary(t,t->header_rows);
  exr_status status=EXR_OK;
  exr_table_cursor view;
  if(!t->header_rows || !t->header_cells) return EXR_OK;
  view=*t;
  view.row=0; view.end=t->header_rows; view.fragmented=0; view.consumed=0;
  f->y+=top;
  for(i=0;i<t->header_cells;i++) {
    table_cell *c=&t->cells[i];
    exr_layout *layout=NULL; float measured=0;
    flow local=cell_flow(f,t,c);
    status=exr_flow_unit(&local,c->node,
      t->columns_at[c->column+c->colspan]-t->columns_at[c->column],&layout,&measured);
    if(status!=EXR_OK) { exr_layout_free(layout); return status; }
    if(layout) {
      status=exr_flow_copy(f,layout,c->node,t->x+t->columns_at[c->column],
                           f->y+t->positions[c->row]-t->positions[0],
                           t->positions[c->row+c->rowspan]-t->positions[c->row],
                           cell_inset(f,t,c));
      exr_layout_free(layout);
      if(status!=EXR_OK) return status;
    }
  }
  if(t->collapse) status=paint_borders(f,&view,1);
  else for(i=0;i<t->header_cells;i++) {
    const table_cell *c=&t->cells[i];
    if(exr_border_uniform(&f->styles[c->node])) continue;
    status=paint_cell_sides(f,&view,c,f->y+t->positions[c->row]-t->positions[0],
                            t->positions[c->row+c->rowspan]-t->positions[c->row]);
    if(status!=EXR_OK) return status;
  }
  if(status!=EXR_OK) return status;
  f->y+=height+bottom;
  return EXR_OK;
}
/* A tall row advances each column independently, using the same speculative
   BFC cursors as floats. No line/image is cropped at a shared canvas cut. */
static void remove_cell_box(exr_layout *l,size_t node) {
  size_t i,n=0;
  for(i=0;i<l->box_count;i++) if(l->boxes[i].node!=node || l->boxes[i].kind!=EXR_BOX_CELL) l->boxes[n++]=l->boxes[i];
  l->box_count=n;if(l->page_count) l->pages[0].box_count=n;
}
static exr_status split_borders(flow *f,const exr_table_cursor *t,float offset,float height,int top) {
  size_t r,c;exr_status status;
  if(t->collapse) {
    for(r=t->row;r<=t->end;r++) {
      float y=t->positions[r]-t->positions[t->row]-offset;
      if(y<-.001f || y>height+.001f || (r==t->row && !offset && !top)) continue;
      for(c=0;c<t->columns;c++) {
        const table_edge *edge=t->horizontal+r*t->columns+c;float left=0,right=0;
        if(r) { left=t->vertical[(r-1)*(t->columns+1)+c].width/2;right=t->vertical[(r-1)*(t->columns+1)+c+1].width/2; }
        if(r<t->row_count) { left=fmaxf(left,t->vertical[r*(t->columns+1)+c].width/2);right=fmaxf(right,t->vertical[r*(t->columns+1)+c+1].width/2); }
        status=paint_edge(f,t,edge,t->x+t->columns_at[c]-left,f->y+y-edge->width/2,t->columns_at[c+1]-t->columns_at[c]+left+right,edge->width);
        if(status!=EXR_OK) return status;
      }
    }
    for(r=t->row;r<t->end;r++) {
      float begin=fmaxf(0,t->positions[r]-t->positions[t->row]-offset),end=fminf(height,t->positions[r+1]-t->positions[t->row]-offset);
      if(end<=begin) continue;
      for(c=0;c<=t->columns;c++) {
        const table_edge *edge=t->vertical+r*(t->columns+1)+c;
        status=paint_edge(f,t,edge,t->x+t->columns_at[c]-edge->width/2,f->y+begin,edge->width,end-begin);if(status!=EXR_OK) return status;
      }
    }
  } else for(c=t->first;c<t->last;c++) {
    const table_cell *cell=t->cells+c;
    exr_style style=exr_flow_style(&f->styles[cell->node],f->writing_mode);
    float begin=t->positions[cell->row]-t->positions[t->row]-offset,end=t->positions[cell->row+cell->rowspan]-t->positions[t->row]-offset;
    float lo=fmaxf(0,begin),hi=fminf(height,end);
    float x=t->x+t->columns_at[cell->column],w=t->columns_at[cell->column+cell->colspan]-t->columns_at[cell->column];
    float top_edge=exr_border_extent(&style,0),bottom=exr_border_extent(&style,2);
    float left=exr_border_extent(&style,3),right=exr_border_extent(&style,1);
    if(hi<=lo) continue;
    if(begin>=-.001f && top_edge>0) { status=exr_flow_edge(f,cell->node,style.border_style[0],top_edge,style.border_color[0],x,f->y+lo,w,fminf(top_edge,hi-lo));if(status!=EXR_OK) return status; }
    if(end<=height+.001f && bottom>0) { status=exr_flow_edge(f,cell->node,style.border_style[2],bottom,style.border_color[2],x,f->y+fmaxf(lo,hi-bottom),w,fminf(bottom,hi-lo));if(status!=EXR_OK) return status; }
    if(left>0) { status=exr_flow_edge(f,cell->node,style.border_style[3],left,style.border_color[3],x,f->y+lo,left,hi-lo);if(status!=EXR_OK) return status; }
    if(right>0) { status=exr_flow_edge(f,cell->node,style.border_style[1],right,style.border_color[1],x+w-right,f->y+lo,right,hi-lo);if(status!=EXR_OK) return status; }
  }
  return EXR_OK;
}
static float fragment_border(const exr_table_cursor *t,float offset,int maximum) {
  size_t row;float result=0;
  if(!t->collapse) return 0;
  for(row=t->row;row<=t->end;row++) if(maximum || fabsf(t->positions[row]-t->positions[t->row]-offset)<.001f)
    result=fmaxf(result,boundary(t,row));
  return result;
}
static exr_status split_row(flow *f,exr_table_cursor *t,int *done) {
  typedef struct { exr_pager *cursor;exr_layout *layout;float gap;size_t position;int finished; } trial;
  size_t i,n=t->last-t->first,operations=n+(t->end-t->row+1)*(t->columns+1);exr_status status;trial *parts=NULL;exr_table_cursor view=*t;
  int paint_top=!t->consumed && (!t->row || f->y==exr_flow_top(f)),last,repeat;
  float top=t->consumed ? fragment_border(t,t->consumed,0) : paint_top ? boundary(t,t->row) : 0;
  float bottom=fragment_border(t,0,1),budget,height,header=0;
  view.heights=NULL;view.positions=NULL;
  status=exr_flow_page(f,1,f->doc->nodes[t->rows[t->row]].start);if(status!=EXR_OK) return status;
  repeat=repeats_header(f,t) && f->y<=exr_flow_top(f)+.001f;
  if(repeat) header=header_height(t)+boundary(t,0)+boundary(t,t->header_rows);
  budget=exr_flow_bottom(f)-f->y-top-bottom-header;
  if(budget<1) return f->y>exr_flow_top(f)+.01f ? EXR_PAUSE : exr_fail(f->error,f->fragment_probe ? EXR_FRAGMENT_SMALL : EXR_LIMIT,"Table borders leave no row fragment extent");
  if(operations>64u*1024u*1024u-t->fragment_work) return exr_fail(f->error,EXR_LIMIT,"Table fragment work budget exceeded");
  parts=calloc(n ? n : 1,sizeof(*parts));view.heights=malloc(t->row_count*sizeof(*view.heights));view.positions=malloc((t->row_count+1)*sizeof(*view.positions));
  if(!parts || !view.heights || !view.positions) { status=exr_fail(f->error,EXR_MEMORY,"Table fragment trial allocation failed");goto bad; }
  memcpy(view.heights,t->heights,t->row_count*sizeof(*view.heights));memcpy(view.positions,t->positions,(t->row_count+1)*sizeof(*view.positions));
  /* Cells are visited in row order. Extending a cell's ending row only moves
     later, not-yet-started cells; completed pages retain their coordinates. */
  for(i=0;i<n;i++) {
    table_cell *c=t->cells+t->first+i;trial *part=parts+i;flow local=cell_flow(f,t,c);
    float begin=view.positions[c->row]-view.positions[t->row],needed;
    status=exr_control_cancel(&f->config->control,f->error);if(status!=EXR_OK) goto bad;
    part->finished=c->finished;
    if(c->finished || begin>=t->consumed+budget-.001f) continue;
    part->gap=c->cursor ? 0 : fminf(budget,fmaxf(0,begin+c->gap-t->consumed));
    if(part->gap+.01f<budget) {
      status=exr_flow_fragment(&local,c->cursor,c->node,t->columns_at[c->column+c->colspan]-t->columns_at[c->column],
                               budget-part->gap,0,0,&part->cursor,&part->layout);
      if(status==EXR_FRAGMENT_SMALL && (part->gap>0 || f->y>exr_flow_top(f)+.01f)) { part->gap=budget;status=EXR_OK; }
      else if(status==EXR_FRAGMENT_SMALL) status=exr_fail(f->error,f->fragment_probe ? EXR_FRAGMENT_SMALL : EXR_LIMIT,"Table cell contains an item larger than a page");
      if(status!=EXR_OK) goto bad;
      if(part->cursor) {
        part->finished=exr_flow_cursor_finished(part->cursor);part->position=exr_flow_cursor_position(part->cursor);
        if(part->finished) { exr_pager_free(part->cursor);part->cursor=NULL; }
      }
    }
    needed=t->consumed+part->gap+(part->layout ? part->layout->flow_block : 0);
    if(!part->finished) needed=fmaxf(needed,t->consumed+budget+1);
    if(needed>view.positions[c->row+c->rowspan]-view.positions[t->row]) {
      size_t row=c->row+c->rowspan-1,j;
      if(view.end-row>64u*1024u*1024u-t->fragment_work-operations) { status=exr_fail(f->error,EXR_LIMIT,"Table fragment work budget exceeded");goto bad; }
      operations+=view.end-row;
      view.heights[row]+=needed-(view.positions[row+1]-view.positions[t->row]);
      for(j=row;j<view.end;j++) view.positions[j+1]=view.positions[j]+view.heights[j];
    }
  }
  { size_t count=0;
    for(i=0;i<n && count<=EXR_MAX_FLOATS;i++) if(!parts[i].finished) count+=exr_flow_cursor_floats(parts[i].cursor ? parts[i].cursor : t->cells[t->first+i].cursor);
    if(count>EXR_MAX_FLOATS) { status=exr_fail(f->error,EXR_LIMIT,"More than 128 floating cursors in table cells");goto bad; }
  }
  height=fminf(budget,fmaxf(0,view.positions[view.end]-view.positions[view.row]-t->consumed));
  last=1;for(i=0;i<n;i++) if(!parts[i].finished) last=0;
  if(t->consumed+height+.01f<view.positions[view.end]-view.positions[view.row]) last=0;
  if(height<.001f && !last) { status=exr_fail(f->error,EXR_LIMIT,"Table row fragment made no progress");goto bad; }
  if(repeat) { status=repeat_header(f,t); if(status!=EXR_OK) goto bad; }
  f->y+=top;
  for(i=0;i<n;i++) {
    table_cell *c=t->cells+t->first+i;trial *part=parts+i;
    float x=t->x+t->columns_at[c->column],w=t->columns_at[c->column+c->colspan]-t->columns_at[c->column];
    float begin=fmaxf(0,view.positions[c->row]-view.positions[view.row]-t->consumed);
    float end=fminf(height,view.positions[c->row+c->rowspan]-view.positions[view.row]-t->consumed);exr_box *box;
    if(end<=begin) continue;
    box=exr_flow_box(f,c->node,f->layout->page_count-1,x,f->y+begin,w,end-begin,EXR_BOX_CELL);
    if(!box) { status=EXR_MEMORY;goto bad; }box->border_width=0;
    if(part->layout) {
      remove_cell_box(part->layout,c->node);
      status=exr_flow_copy(f,part->layout,c->node,x,f->y+part->gap,part->layout->flow_block,0);if(status!=EXR_OK) goto bad;
    }
  }
  status=split_borders(f,&view,t->consumed,height,paint_top);if(status!=EXR_OK) goto bad;
  /* Commit only after every cell and the complete shared grid are valid. */
  for(i=0;i<n;i++) {
    table_cell *c=t->cells+t->first+i;trial *part=parts+i;c->finished=part->finished;
    if(part->position>t->position) t->position=part->position;
    if(part->cursor || part->finished) { exr_pager_free(c->cursor);c->cursor=part->cursor;part->cursor=NULL; }
    exr_layout_free(part->layout);part->layout=NULL;
  }
  memcpy(t->heights,view.heights,t->row_count*sizeof(*view.heights));memcpy(t->positions,view.positions,(t->row_count+1)*sizeof(*view.positions));
  free(parts);free(view.heights);free(view.positions);t->fragment_work+=operations;
  t->consumed+=height;f->y+=height;
  if(!last) return EXR_PAUSE;
  if(t->end==t->row_count) f->y+=boundary(t,t->end);
  for(i=t->first;i<t->last;i++) { exr_pager_free(t->cells[i].cursor);t->cells[i].cursor=NULL;if(f->doc->nodes[t->cells[i].node].end>t->position) t->position=f->doc->nodes[t->cells[i].node].end; }
  t->row=t->end;t->first=t->last;t->measured=t->fragmented=0;t->consumed=0;*done=t->row==t->row_count;
  return EXR_OK;
bad:
  if(parts) for(i=0;i<n;i++) { exr_pager_free(parts[i].cursor);exr_layout_free(parts[i].layout); }
  free(parts);free(view.heights);free(view.positions);return status;
}
exr_status exr_table_step(flow *f, exr_table_cursor *t, int *done) {
  exr_status status;
  size_t i;
  float height,top,bottom,header=0; int paint_top;
  *done = 0;
  if (!t->columns || t->row == t->row_count) {
    *done = 1;
    return EXR_OK;
  }
  if(t->fragmented) return split_row(f,t,done);
  if (!t->measured) {
    size_t previous=t->position;
    status = measure(f, t);
    if (status != EXR_OK)
      return failed(f, status);
    float room=fmaxf(exr_flow_room(f),f->unit_assigned ? f->unit_block_reference : 0);
    if(repeats_header(f,t))
      room=fmaxf(1,room-header_height(t)-boundary(t,0)-boundary(t,t->header_rows));
    if(f->paginate && !f->defer_tall_rows && t->positions[t->end]-t->positions[t->row]+boundary(t,t->row)+boundary(t,t->end)>room+.01f) {
      t->fragmented=1;t->consumed=0;t->position=previous;
      for(i=t->first;i<t->last;i++) {
        t->cells[i].gap=cell_inset(f,t,t->cells+i);
        t->cells[i].finished=t->cells[i].content_height<.001f;
        exr_layout_free(t->cells[i].layout);t->cells[i].layout=NULL;
      }
      return split_row(f,t,done);
    }
  }
  height = t->positions[t->end] - t->positions[t->row];
  {
    int eligible = repeats_header(f, t);
    header = eligible ? header_height(t)+boundary(t,0)+boundary(t,t->header_rows) : 0;
  }
  paint_top=!t->row || f->y==exr_flow_top(f);
  top=paint_top ? boundary(t,t->row) : 0; bottom=boundary(t,t->end);
  /* Keep the outside half of the boundary inside the page, including a
     continuation fragment. Continuous groups share the same grid coordinate. */
  { size_t pages=f->layout->page_count;
    status = exr_flow_page(f, height+top+bottom+header, f->doc->nodes[t->rows[t->row]].start);
    if(status==EXR_OK && f->layout->page_count!=pages) {
      paint_top=1; top=boundary(t,t->row);
      status=exr_flow_page(f,height+top+bottom+header,f->doc->nodes[t->rows[t->row]].start);
    }
  }
  if (status == EXR_PAUSE)
    return status;
  if (status != EXR_OK)
    return failed(f, status);
  if(header>0 && f->y<=exr_flow_top(f)+.001f) {
    status=repeat_header(f,t); if(status!=EXR_OK) return failed(f,status);
  }
  f->y+=top;
  if(!f->layout->has_baseline) {
    float baseline=t->baselines[t->row]; int aligned=0;
    for(i=t->first;i<t->last && t->cells[i].row==t->row;i++) if(f->styles[t->cells[i].node].vertical_align==EXR_CELL_BASELINE) aligned=1;
    if(!aligned) for(i=t->first;i<t->last && t->cells[i].row==t->row;i++)
      baseline=fmaxf(baseline,t->cells[i].content_bottom+cell_inset(f,t,&t->cells[i]));
    f->layout->first_baseline=f->y+baseline; f->layout->has_baseline=1;
  }
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    status = exr_flow_copy(f, c->layout, c->node,
                           t->x + t->columns_at[c->column],
                           f->y + t->positions[c->row] - t->positions[t->row],
                           t->positions[c->row + c->rowspan] - t->positions[c->row],cell_inset(f,t,c));
    if (status != EXR_OK)
      return failed(f, status);
  }
  status=paint_borders(f,t,paint_top); if(status!=EXR_OK) return failed(f,status);
  f->y += height;
  if(t->end==t->row_count) f->y+=bottom;
  for (i = t->first; i < t->last; i++) {
    exr_layout_free(t->cells[i].layout);
    t->cells[i].layout = NULL;
  }
  t->row = t->end;
  t->first = t->last;
  t->measured = 0;
  *done = t->row == t->row_count;
  return EXR_OK;
}
