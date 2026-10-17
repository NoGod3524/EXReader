/* SPDX-License-Identifier: GPL-3.0-only */
#include "flow_internal.h"

typedef struct {
  size_t node, row, column, colspan, rowspan;
  exr_layout *layout;
  float height;
} table_cell;
struct exr_table_cursor {
  size_t *rows, row_count, row_capacity;
  table_cell *cells;
  size_t cell_count, cell_capacity, columns;
  float *heights, *positions;
  size_t row, first, last, end;
  size_t position;
  float x, width;
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
  free(t);
}
static exr_status failed(flow *f, exr_status status) {
  if (!f->error || !f->error->message[0])
    return exr_fail(f->error, status, "Table layout limit exceeded");
  return status;
}
size_t exr_table_memory_size(const exr_table_cursor *t) {
  size_t total, i;
  if (!t) return 0;
  total = sizeof(*t) + t->row_count*sizeof(*t->rows) + t->cell_count*sizeof(*t->cells);
  if (t->heights) total += (2*t->row_count + 1)*sizeof(float);
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
  copy->rows = NULL; copy->cells = NULL; copy->heights = copy->positions = NULL;
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
    if (!copy->heights || !copy->positions) goto bad;
    memcpy(copy->heights, t->heights, t->row_count*sizeof(*t->heights));
    memcpy(copy->positions, t->positions, (t->row_count + 1)*sizeof(*t->positions));
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
  if (t->columns) {
    t->heights = calloc(t->row_count, sizeof(*t->heights));
    t->positions = calloc(t->row_count + 1, sizeof(*t->positions));
    if (!t->heights || !t->positions) {
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
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    status = exr_flow_unit(f, c->node, t->width * (float)c->colspan / (float)t->columns,
                           &c->layout, &c->height);
    if (status != EXR_OK)
      return status;
    if (f->doc->nodes[c->node].end != SIZE_MAX && f->doc->nodes[c->node].end > t->position)
      t->position = f->doc->nodes[c->node].end;
    if (c->rowspan == 1)
      t->heights[c->row] = fmaxf(t->heights[c->row], c->height);
  }
  /* Keep the eager algorithm's pass order, including overlapping spanning cells. */
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    float total = 0;
    for (j = c->row; j < c->row + c->rowspan; j++)
      total += t->heights[j];
    if (total < c->height)
      t->heights[c->row + c->rowspan - 1] += c->height - total;
  }
  /* Accumulate positions globally to preserve the eager float arithmetic. */
  for (i = t->row; i < t->end; i++)
    t->positions[i + 1] = t->positions[i] + t->heights[i];
  t->measured = 1;
  return EXR_OK;
}
size_t exr_table_position(const exr_table_cursor *t) { return t ? t->position : 0; }
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
  for (i = t->first; i < t->last; i++) {
    table_cell *c = &t->cells[i];
    status = exr_flow_copy(f, c->layout, c->node,
                           t->x + t->width * (float)c->column / (float)t->columns,
                           f->y + t->positions[c->row] - t->positions[t->row],
                           t->positions[c->row + c->rowspan] - t->positions[c->row]);
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
