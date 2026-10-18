/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"

typedef struct {
  size_t node, row, column, colspan, rowspan;
  exr_layout *layout;
  float height,baseline,content_bottom;
} table_cell;
struct exr_table_cursor {
  size_t *rows, row_count, row_capacity;
  table_cell *cells;
  size_t cell_count, cell_capacity, columns;
  float *heights, *positions, *baselines;
  size_t row, first, last, end;
  size_t position;
  float x, width, min_height;
  float columns_at[65]; /* Logical inline edges, preserved by checkpoint clones. */
  int measured;
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
  for (i = 0; i < t->cell_count; i++)
    exr_layout_free(t->cells[i].layout);
  free(t->cells);
  free(t->rows);
  free(t->heights);
  free(t->positions);
  free(t->baselines);
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
    const table_cell *cell=&t->cells[i]; exr_style style; float width=0,minimum=0,maximum=0;
    if(cell->colspan!=n) continue;
    if(fixed && cell->row) continue;
    status=exr_control_cancel(&f->config->control,f->error); if(status!=EXR_OK) return status;
    style=exr_flow_style(&f->styles[cell->node],f->writing_mode);
    if(style.width.value>=0) width=length_value(style.width,t->width)+length_value(style.padding[1],t->width)+length_value(style.padding[3],t->width)+
      (style.border_style ? 2*style.border_width : 0);
    width=fminf(width,t->width*64);
    if(!fixed) {
      if(f->intrinsic!=2) { status=exr_flow_intrinsic(f,cell->node,t->width,1,&minimum); if(status!=EXR_OK) return status; }
      if(f->intrinsic!=1) { status=exr_flow_intrinsic(f,cell->node,t->width,2,&maximum); if(status!=EXR_OK) return status; }
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
      f->intrinsic_extent=fmax(f->intrinsic_extent,t->x+(f->intrinsic==1 ? min_total : max_total)+f->inline_end_inset);
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
size_t exr_table_memory_size(const exr_table_cursor *t) {
  size_t total, i;
  if (!t) return 0;
  total = sizeof(*t) + t->row_capacity*sizeof(*t->rows) + t->cell_capacity*sizeof(*t->cells);
  if (t->heights) total += (3*t->row_count + 1)*sizeof(float);
  for (i = 0; i < t->cell_count; i++) {
    size_t bytes = exr_layout_memory_size(t->cells[i].layout);
    if (bytes > SIZE_MAX - total) return SIZE_MAX;
    total += bytes;
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
    for (i = 0; i < copy->cell_count; i++) exr_layout_ref(copy->cells[i].layout);
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
  if (f->table_depth >= 8)
    return exr_fail(f->error, EXR_LIMIT, "Nested table limit exceeded");
  t = calloc(1, sizeof(*t));
  if (!t)
    return exr_fail(f->error, EXR_MEMORY, "Table cursor allocation failed");
  t->x = x;
  t->width = width;
  { exr_style style=exr_flow_style(&f->styles[node],f->writing_mode);
    t->min_height=length_value(style.height,exr_flow_room(f));
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
static exr_status measure(flow *f, exr_table_cursor *t) {
  size_t i, j;
  exr_status status;
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
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    status = exr_flow_unit(f, c->node, t->columns_at[c->column+c->colspan]-t->columns_at[c->column],
                           &c->layout, &c->height);
    if (status != EXR_OK)
      return status;
    {
      exr_style style=exr_flow_style(&f->styles[c->node],f->writing_mode);
      float width=t->columns_at[c->column+c->colspan]-t->columns_at[c->column];
      float border=style.border_style ? style.border_width : 0;
      float after=length_value(style.padding[2],width)+border;
      if(style.height.value>=0 && (!style.height.percent || t->min_height>0))
        c->height=fmaxf(c->height,length_value(style.height,t->min_height)+length_value(style.padding[0],width)+border+after);
      c->content_bottom=fmaxf(0,c->layout->flow_block-after);
      c->baseline=c->layout->has_baseline ? c->layout->first_baseline : c->content_bottom;
      if(style.vertical_align==EXR_CELL_BASELINE) t->baselines[c->row]=fmaxf(t->baselines[c->row],c->baseline);
    }
    if (f->doc->nodes[c->node].end != SIZE_MAX && f->doc->nodes[c->node].end > t->position)
      t->position = f->doc->nodes[c->node].end;
  }
  for(i=t->first;i<t->last;i++) {
    table_cell *c=&t->cells[i];
    float shift=f->styles[c->node].vertical_align==EXR_CELL_BASELINE ? fmaxf(0,t->baselines[c->row]-c->baseline) : 0;
    if(c->rowspan==1) t->heights[c->row]=fmaxf(t->heights[c->row],fmaxf(c->height,c->layout->flow_block+shift));
  }
  /* Keep the eager algorithm's pass order, including overlapping spanning cells. */
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    float total = 0;
    for (j = c->row; j < c->row + c->rowspan; j++)
      total += t->heights[j];
    { float shift=f->styles[c->node].vertical_align==EXR_CELL_BASELINE ? fmaxf(0,t->baselines[c->row]-c->baseline) : 0;
      float needed=fmaxf(c->height,c->layout->flow_block+shift);
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
void exr_table_geometry(const exr_table_cursor *t,float *x,float *width) { *x=t->x; *width=t->width; }
static float cell_inset(flow *f,const exr_table_cursor *t,const table_cell *c) {
  float allocated=t->positions[c->row+c->rowspan]-t->positions[c->row];
  float room=fmaxf(0,allocated-c->layout->flow_block);
  switch(f->styles[c->node].vertical_align) {
    case EXR_CELL_TOP: return 0;
    case EXR_CELL_MIDDLE: return room/2;
    case EXR_CELL_BOTTOM: return room;
    default: return fminf(room,fmaxf(0,t->baselines[c->row]-c->baseline));
  }
}
exr_status exr_table_step(flow *f, exr_table_cursor *t, int *done) {
  exr_status status;
  size_t i;
  float height;
  *done = 0;
  if (!t->columns || t->row == t->row_count) {
    *done = 1;
    return EXR_OK;
  }
  if (!t->measured) {
    status = measure(f, t);
    if (status != EXR_OK)
      return failed(f, status);
  }
  height = t->positions[t->end] - t->positions[t->row];
  status = exr_flow_page(f, height, f->doc->nodes[t->rows[t->row]].start);
  if (status == EXR_PAUSE)
    return status;
  if (status != EXR_OK)
    return failed(f, status);
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
  f->y += height;
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
