/* SPDX-License-Identifier: GPL-3.0-only */
#include "bidi_internal.h"
#include "bidi_data.h"

struct exr_bidi {
  exr_bidi_scalar *scalars;
  unsigned char *types, *bases;
  size_t count;
};
typedef struct {
  unsigned char level, override, isolate;
} status_entry;
typedef struct {
  size_t *match, *next, *sequence;
  unsigned char *types, *levels, *heads;
} work;

static unsigned char classify(uint32_t cp) {
  size_t low = 0, high = sizeof(bidi_ranges) / sizeof(*bidi_ranges);
  while (low < high) {
    size_t middle = low + (high - low) / 2;
    if (cp < bidi_ranges[middle].first)
      high = middle;
    else if (cp > bidi_ranges[middle].last)
      low = middle + 1;
    else
      return bidi_ranges[middle].type;
  }
  return bidi_L;
}
static const bidi_bracket *bracket(uint32_t cp) {
  size_t low = 0, high = sizeof(bidi_brackets) / sizeof(*bidi_brackets);
  while (low < high) {
    size_t middle = low + (high - low) / 2;
    if (cp < bidi_brackets[middle].codepoint)
      high = middle;
    else if (cp > bidi_brackets[middle].codepoint)
      low = middle + 1;
    else
      return &bidi_brackets[middle];
  }
  return NULL;
}
uint32_t exr_bidi_mirror(uint32_t cp) {
  size_t low = 0, high = sizeof(bidi_mirrors) / sizeof(*bidi_mirrors);
  while (low < high) {
    size_t middle = low + (high - low) / 2;
    if (cp < bidi_mirrors[middle].codepoint)
      high = middle;
    else if (cp > bidi_mirrors[middle].codepoint)
      low = middle + 1;
    else
      return bidi_mirrors[middle].mirror;
  }
  return cp;
}
static int isolate(unsigned char type) {
  return type == bidi_LRI || type == bidi_RLI || type == bidi_FSI;
}
static int removed(unsigned char type) {
  return type == bidi_BN || type == bidi_LRE || type == bidi_RLE ||
         type == bidi_LRO || type == bidi_RLO || type == bidi_PDF;
}
static int whitespace(unsigned char type) {
  return type == bidi_WS || isolate(type) || type == bidi_PDI || removed(type);
}
int exr_bidi_complex(uint32_t cp) {
  if (cp < 0x80) return 0;
  unsigned char type = classify(cp);
  return type == bidi_R || type == bidi_AL || type == bidi_AN ||
         (removed(type) && type != bidi_BN) || isolate(type) || type == bidi_PDI;
}
int exr_bidi_ltr_letter(uint32_t cp) { return classify(cp)==bidi_L; }
unsigned exr_bidi_strong_type(uint32_t cp) {
  unsigned char type=classify(cp);
  return type==bidi_L ? 1u : type==bidi_R ? 2u : type==bidi_AL ? 3u : 0u;
}
int exr_bidi_window_safe(uint32_t cp) {
  unsigned char type=classify(cp);
  return !bracket(cp) && !(removed(type) && type!=bidi_BN) && !isolate(type) &&
    type!=bidi_PDI && type!=bidi_B && type!=bidi_S;
}
static unsigned char direction(unsigned level) { return level & 1 ? bidi_R : bidi_L; }
static unsigned char strong(unsigned char type) {
  return type == bidi_EN || type == bidi_AN || type == bidi_AL ? bidi_R : type;
}
static int neutral(unsigned char type) {
  return type == bidi_B || type == bidi_S || type == bidi_WS || type == bidi_ON ||
         isolate(type) || type == bidi_PDI;
}
/* P2/P3 and X5c skip whole nested isolates, including unmatched initiators. */
static unsigned first_strong(const unsigned char *types, const size_t *match,
                               size_t first, size_t end) {
  size_t i;
  for (i = first; i < end; i++) {
    if (types[i] == bidi_L)
      return 0;
    if (types[i] == bidi_R || types[i] == bidi_AL)
      return 1;
    if (isolate(types[i])) {
      if (match[i] == SIZE_MAX || match[i] >= end)
        break;
      i = match[i];
    }
  }
  return 0;
}
/* X1-X8. Levels of X9 controls remain internal until the live runs are built. */
static void explicit_levels(exr_bidi_scalar *scalars, const unsigned char *original,
                              size_t count, unsigned base, work *w) {
  status_entry stack[126] = {{0, 0, 0}};
  size_t depth = 1, overflow_isolate = 0, overflow_embedding = 0, valid_isolate = 0, i;
  stack[0].level = (unsigned char)base;
  stack[0].override = bidi_ON;
  for (i = 0; i < count; i++) {
    unsigned char type = original[i];
    status_entry top = stack[depth - 1];
    unsigned level = top.level;
    w->types[i] = type;
    if (type == bidi_LRE || type == bidi_RLE || type == bidi_LRO || type == bidi_RLO) {
      unsigned next = type == bidi_RLE || type == bidi_RLO ? (level + 1) | 1 : (level + 2) & ~1u;
      if (next <= 125 && !overflow_isolate && !overflow_embedding) {
        stack[depth++] = (status_entry){(unsigned char)next,
            type == bidi_LRO ? bidi_L : type == bidi_RLO ? bidi_R : bidi_ON, 0};
      } else if (!overflow_isolate)
        overflow_embedding++;
    } else if (isolate(type)) {
      unsigned rtl = type == bidi_RLI ||
          (type == bidi_FSI && first_strong(original, w->match, i + 1,
                                             w->match[i] == SIZE_MAX ? count : w->match[i]));
      unsigned next = rtl ? (level + 1) | 1 : (level + 2) & ~1u;
      if (top.override != bidi_ON)
        w->types[i] = top.override;
      if (next <= 125 && !overflow_isolate && !overflow_embedding) {
        valid_isolate++;
        stack[depth++] = (status_entry){(unsigned char)next, bidi_ON, 1};
      } else
        overflow_isolate++;
    } else if (type == bidi_PDI) {
      if (overflow_isolate)
        overflow_isolate--;
      else if (valid_isolate) {
        overflow_embedding = 0;
        while (!stack[depth - 1].isolate)
          depth--;
        depth--;
        valid_isolate--;
      }
      top = stack[depth - 1];
      level = top.level;
      if (top.override != bidi_ON)
        w->types[i] = top.override;
    } else if (type == bidi_PDF) {
      if (!overflow_isolate) {
        if (overflow_embedding)
          overflow_embedding--;
        else if (depth > 1 && !top.isolate)
          depth--;
      }
    } else if (type == bidi_B)
      level = base;
    else if (type != bidi_BN && top.override != bidi_ON)
      w->types[i] = top.override;
    w->levels[i] = (unsigned char)level;
    scalars[i].level = removed(type) ? UINT_MAX : level;
  }
}
static uint32_t canonical_bracket(uint32_t cp) {
  return cp == 0x2329 ? 0x3008 : cp == 0x232a ? 0x3009 : cp;
}
/* BD16/N0: at most 63 nested openings; pair[] reuses the isolate match workspace. */
static void brackets(exr_bidi_scalar *scalars, const unsigned char *original,
                        work *w, size_t count, unsigned char embedding, unsigned char sos) {
  size_t openings[63], depth = 0, i, j, context_at = 0;
  unsigned char context = sos;
  for (i = 0; i < count; i++)
    w->match[i] = SIZE_MAX;
  for (i = 0; i < count; i++) {
    const bidi_bracket *b;
    size_t index = w->sequence[i];
    if (w->types[index] != bidi_ON || !(b = bracket(scalars[index].codepoint)))
      continue;
    if (b->kind == 1) {
      if (depth == 63)
        return; /* BD16 requires discarding every pair on stack overflow. */
      openings[depth++] = i;
    } else {
      for (j = depth; j > 0; j--) {
        const bidi_bracket *open = bracket(scalars[w->sequence[openings[j - 1]]].codepoint);
        if (canonical_bracket(open->pair) == canonical_bracket(b->codepoint)) {
          w->match[openings[j - 1]] = i;
          depth = j - 1;
          break;
        }
      }
    }
  }
  for (i = 0; i < count; i++) {
    unsigned char found = bidi_ON, resolved;
    size_t end = w->match[i];
    if (end == SIZE_MAX)
      continue;
    while (context_at < i) {
      unsigned char t = strong(w->types[w->sequence[context_at++]]);
      if (t == bidi_L || t == bidi_R)
        context = t;
    }
    for (j = i + 1; j < end; j++) {
      unsigned char t = strong(w->types[w->sequence[j]]);
      if (t == embedding) {
        found = embedding;
        break;
      }
      if (t == bidi_L || t == bidi_R)
        found = t;
    }
    if (found == bidi_ON)
      continue;
    resolved = found == embedding ? embedding : context;
    w->types[w->sequence[i]] = w->types[w->sequence[end]] = resolved;
    for (j = i + 1; j < count && original[w->sequence[j]] == bidi_NSM; j++)
      w->types[w->sequence[j]] = resolved;
    for (j = end + 1; j < count && original[w->sequence[j]] == bidi_NSM; j++)
      w->types[w->sequence[j]] = resolved;
  }
}
/* One isolating run sequence: W1-W7, N0-N2 and I1/I2. */
static void resolve_sequence(exr_bidi_scalar *scalars, const unsigned char *original,
                                work *w, size_t count, unsigned char sos, unsigned char eos) {
  size_t i, j;
  unsigned char previous = sos, last_strong = sos;
  unsigned char embedding = direction(w->levels[w->sequence[0]]);
  for (i = 0; i < count; i++) {
    unsigned char *t = &w->types[w->sequence[i]];
    if (*t == bidi_NSM)
      *t = isolate(previous) || previous == bidi_PDI ? bidi_ON : previous;
    previous = *t;
  }
  for (i = 0; i < count; i++) {
    unsigned char *t = &w->types[w->sequence[i]];
    if (*t == bidi_EN && last_strong == bidi_AL)
      *t = bidi_AN;
    if (*t == bidi_L || *t == bidi_R || *t == bidi_AL)
      last_strong = *t;
  }
  for (i = 0; i < count; i++)
    if (w->types[w->sequence[i]] == bidi_AL)
      w->types[w->sequence[i]] = bidi_R;
  for (i = 1; i + 1 < count; i++) {
    unsigned char *t = &w->types[w->sequence[i]];
    unsigned char before = w->types[w->sequence[i - 1]], after = w->types[w->sequence[i + 1]];
    if ((*t == bidi_ES && before == bidi_EN && after == bidi_EN) ||
        (*t == bidi_CS && before == after && (before == bidi_EN || before == bidi_AN)))
      *t = before;
  }
  for (i = 0; i < count;) {
    if (w->types[w->sequence[i]] != bidi_ET) {
      i++;
      continue;
    }
    j = i + 1;
    while (j < count && w->types[w->sequence[j]] == bidi_ET)
      j++;
    if ((i && w->types[w->sequence[i - 1]] == bidi_EN) ||
        (j < count && w->types[w->sequence[j]] == bidi_EN))
      while (i < j)
        w->types[w->sequence[i++]] = bidi_EN;
    i = j;
  }
  for (i = 0; i < count; i++) {
    unsigned char *t = &w->types[w->sequence[i]];
    if (*t == bidi_ES || *t == bidi_ET || *t == bidi_CS)
      *t = bidi_ON;
  }
  last_strong = sos;
  for (i = 0; i < count; i++) {
    unsigned char *t = &w->types[w->sequence[i]];
    if (*t == bidi_EN && last_strong == bidi_L)
      *t = bidi_L;
    if (*t == bidi_L || *t == bidi_R)
      last_strong = *t;
  }
  brackets(scalars, original, w, count, embedding, sos);
  previous = sos;
  for (i = 0; i < count;) {
    unsigned char t = w->types[w->sequence[i]], after, resolved;
    if (!neutral(t)) {
      previous = strong(t);
      i++;
      continue;
    }
    j = i + 1;
    while (j < count && neutral(w->types[w->sequence[j]]))
      j++;
    after = j == count ? eos : strong(w->types[w->sequence[j]]);
    resolved = previous == after ? previous : embedding;
    while (i < j)
      w->types[w->sequence[i++]] = resolved;
    previous = resolved;
  }
  for (i = 0; i < count; i++) {
    size_t index = w->sequence[i];
    unsigned char t = w->types[index];
    unsigned level = w->levels[index];
    if (!(level & 1))
      level += t == bidi_R ? 1 : t == bidi_AN || t == bidi_EN ? 2 : 0;
    else
      level += t == bidi_L || t == bidi_EN || t == bidi_AN ? 1 : 0;
    scalars[index].level = level;
  }
}
static void free_work(work *w) {
  free(w->match);
  free(w->next);
  free(w->sequence);
  free(w->types);
  free(w->levels);
  free(w->heads);
}
static exr_status paragraph(exr_bidi_scalar *scalars, const unsigned char *original,
                              unsigned char *bases, size_t count, exr_direction requested,
                              exr_error *e) {
  work w = {0};
  size_t i, previous = SIZE_MAX, depth = 0;
  unsigned base;
  w.match = malloc(count * sizeof(*w.match));
  w.next = malloc(count * sizeof(*w.next));
  w.sequence = malloc(count * sizeof(*w.sequence));
  w.types = malloc(count);
  w.levels = malloc(count);
  w.heads = calloc(count, 1);
  if (!w.match || !w.next || !w.sequence || !w.types || !w.levels || !w.heads) {
    free_work(&w);
    return exr_fail(e, EXR_MEMORY, "Bidi paragraph workspace allocation failed");
  }
  for (i = 0; i < count; i++) {
    w.match[i] = SIZE_MAX;
    if (isolate(original[i]))
      w.sequence[depth++] = i;
    else if (original[i] == bidi_PDI && depth) {
      size_t opening = w.sequence[--depth];
      w.match[opening] = i;
    }
  }
  base = requested == EXR_DIRECTION_AUTO ? first_strong(original, w.match, 0, count) :
         requested == EXR_DIRECTION_RTL;
  memset(bases, (int)base, count);
  explicit_levels(scalars, original, count, base, &w);
  /* Build level runs as linked lists, then join the runs linked by isolates.
     No backward search or repeated paragraph scan is needed to form an IRS. */
  for (i = 0; i < count; i++) {
    w.next[i] = SIZE_MAX;
    if (removed(original[i]))
      continue;
    if (previous == SIZE_MAX || w.levels[previous] != w.levels[i])
      w.heads[i] = 1;
    else
      w.next[previous] = i;
    previous = i;
  }
  for (i = 0; i < count; i++)
    if (isolate(original[i]) && w.next[i] == SIZE_MAX && w.match[i] != SIZE_MAX &&
        w.levels[i] == w.levels[w.match[i]]) {
      w.next[i] = w.match[i];
      w.heads[w.match[i]] = 0;
    }
  for (i = 0; i < count; i++) {
    size_t current, n = 0, before, after, last;
    unsigned sos_level, eos_level;
    if (!w.heads[i])
      continue;
    for (current = i; current != SIZE_MAX; current = w.next[current])
      w.sequence[n++] = current;
    last = w.sequence[n - 1];
    before = i;
    while (before && removed(original[before - 1]))
      before--;
    sos_level = before ? w.levels[before - 1] : base;
    if (w.levels[i] > sos_level)
      sos_level = w.levels[i];
    after = last + 1;
    while (after < count && removed(original[after]))
      after++;
    eos_level = after == count || isolate(original[last]) ? base : w.levels[after];
    if (w.levels[last] > eos_level)
      eos_level = w.levels[last];
    resolve_sequence(scalars, original, &w, n, direction(sos_level), direction(eos_level));
  }
  free_work(&w);
  return EXR_OK;
}
/* L1 uses original types, including X9 controls while scanning whitespace. */
static void reset_level(const exr_bidi *bidi, size_t first, size_t index, unsigned *levels) {
  if (levels)
    levels[index] = bidi->bases[first + index];
  else
    bidi->scalars[first + index].level = bidi->bases[first + index];
}
static void line_levels(const exr_bidi *bidi, size_t first, size_t count, unsigned *levels) {
  size_t i, j;
  if (levels)
    for (i = 0; i < count; i++)
      levels[i] = bidi->scalars[first + i].level;
  for (i = 0; i < count; i++)
    if (bidi->types[first + i] == bidi_B || bidi->types[first + i] == bidi_S) {
      reset_level(bidi, first, i, levels);
      for (j = i; j && whitespace(bidi->types[first + j - 1]);) {
        j--;
        if (!removed(bidi->types[first + j]))
          reset_level(bidi, first, j, levels);
      }
    }
  for (j = count; j && whitespace(bidi->types[first + j - 1]);) {
    j--;
    if (!removed(bidi->types[first + j]))
      reset_level(bidi, first, j, levels);
  }
}
exr_status exr_bidi_line_levels(const exr_bidi *bidi, size_t first, size_t count, unsigned *out) {
  if (!bidi || first > bidi->count || count > bidi->count - first || (count && !out))
    return EXR_ARGUMENT;
  if (count)
    line_levels(bidi, first, count, out);
  return EXR_OK;
}
void exr_bidi_override_free(exr_bidi_override *item) {
  while(item && !--item->refs) { exr_bidi_override *previous=item->previous;free(item);item=previous; }
}
exr_direction exr_bidi_override_at(const exr_bidi_override *item,size_t source) {
  for(;item;item=item->previous) if(source>=item->start && source<item->end) return item->direction;
  return EXR_DIRECTION_AUTO;
}
int exr_bidi_paragraph_end(uint32_t cp) { return classify(cp)==bidi_B; }
unsigned exr_bidi_p2(uint32_t cp,size_t *depth) {
  unsigned char type=classify(cp);
  if(isolate(type)) { (*depth)++;return 0; }
  if(type==bidi_PDI) { if(*depth) (*depth)--;return 0; }
  if(*depth) return 0;
  return type==bidi_L ? 1 : type==bidi_R || type==bidi_AL ? 2 : 0;
}
exr_status exr_bidi_analyze_mapped(const char *text,size_t size,exr_direction requested,
  const size_t *sources,const exr_bidi_override *overrides,exr_bidi **out,exr_error *e) {
  exr_bidi *bidi;
  size_t at = 0, count = 0, i, first;
  uint32_t cp;
  exr_status status;
  if (!out)
    return exr_fail(e, EXR_ARGUMENT, "Missing bidi analysis output");
  *out = NULL;
  if (!text || requested < EXR_DIRECTION_AUTO || requested > EXR_DIRECTION_RTL)
    return exr_fail(e, EXR_ARGUMENT, "Invalid bidi analysis arguments");
  if (size > EXR_MAX_TEXT)
    return exr_fail(e, EXR_LIMIT, "Bidi input exceeds 64 MiB");
  while (at < size) {
    if (!exr_next(text, size, &at, &cp))
      return exr_fail(e, EXR_ENCODING, "Invalid UTF-8 in bidi text");
    if (++count > EXR_MAX_ITEMS)
      return exr_fail(e, EXR_LIMIT, "Bidi input exceeds scalar limit");
  }
  bidi = calloc(1, sizeof(*bidi));
  if (!bidi)
    return exr_fail(e, EXR_MEMORY, "Bidi result allocation failed");
  bidi->count = count;
  if (count) {
    bidi->scalars = calloc(count, sizeof(*bidi->scalars));
    bidi->types = malloc(count);
    bidi->bases = malloc(count);
    if (!bidi->scalars || !bidi->types || !bidi->bases) {
      exr_bidi_free(bidi);
      return exr_fail(e, EXR_MEMORY, "Bidi scalar allocation failed");
    }
  }
  at = 0;
  for (i = 0; i < count; i++) {
    bidi->scalars[i].start = at;
    exr_next(text, size, &at, &cp);
    bidi->scalars[i].end = at;
    bidi->scalars[i].codepoint = cp;
    bidi->types[i] = classify(cp);
  }
  for (first = 0; first < count; first = i) {
    i = first;
    do {
      i++;
    } while (i < count && bidi->types[i - 1] != bidi_B);
    status = paragraph(bidi->scalars + first, bidi->types + first, bidi->bases + first,
                         i - first, requested==EXR_DIRECTION_AUTO && sources && overrides ?
                         exr_bidi_override_at(overrides,sources[first]) : requested, e);
    if (status != EXR_OK) {
      exr_bidi_free(bidi);
      return status;
    }
  }
  line_levels(bidi, 0, count, NULL);
  *out = bidi;
  return exr_fail(e, EXR_OK, "");
}
exr_status exr_bidi_analyze(const char *text,size_t size,exr_direction requested,exr_bidi **out,exr_error *e) {
  return exr_bidi_analyze_mapped(text,size,requested,NULL,NULL,out,e);
}
const exr_bidi_scalar *exr_bidi_scalars(const exr_bidi *bidi, size_t *count) {
  if (count)
    *count = bidi ? bidi->count : 0;
  return bidi ? bidi->scalars : NULL;
}
unsigned exr_bidi_base_level(const exr_bidi *bidi, size_t index) {
  return bidi && index < bidi->count ? bidi->bases[index] : UINT_MAX;
}
/* L2 for one paragraph fragment. The order array contains absolute scalar indices. */
static void reverse_levels(size_t *order, size_t count, const unsigned *levels, size_t first) {
  unsigned highest = 0, lowest_odd = UINT_MAX, level;
  size_t i, j, k;
  for (i = 0; i < count; i++) {
    level = levels[order[i] - first];
    if (level > highest)
      highest = level;
    if ((level & 1) && level < lowest_odd)
      lowest_odd = level;
  }
  if (lowest_odd == UINT_MAX)
    return;
  for (level = highest;; level--) {
    for (i = 0; i < count;) {
      if (levels[order[i] - first] < level) {
        i++;
        continue;
      }
      j = i + 1;
      while (j < count && levels[order[j] - first] >= level)
        j++;
      for (k = j; i < --k; i++) {
        size_t swap = order[i];
        order[i] = order[k];
        order[k] = swap;
      }
      i = j;
    }
    if (level == lowest_odd)
      break;
  }
}
exr_status exr_bidi_reorder(const exr_bidi *bidi, size_t first, size_t count,
                             size_t **out, size_t *out_count, exr_error *e) {
  unsigned *levels;
  size_t *order, n = 0, paragraph_start = 0, i;
  if (out)
    *out = NULL;
  if (out_count)
    *out_count = 0;
  if (!out || !out_count || !bidi || first > bidi->count || count > bidi->count - first)
    return exr_fail(e, EXR_ARGUMENT, "Invalid bidi line slice or output");
  if (!count)
    return exr_fail(e, EXR_OK, "");
  levels = malloc(count * sizeof(*levels));
  order = malloc(count * sizeof(*order));
  if (!levels || !order) {
    free(levels);
    free(order);
    return exr_fail(e, EXR_MEMORY, "Bidi line allocation failed");
  }
  line_levels(bidi, first, count, levels);
  for (i = 0; i < count; i++) {
    if (levels[i] != UINT_MAX)
      order[n++] = first + i;
    if (bidi->types[first + i] == bidi_B || i + 1 == count) {
      reverse_levels(order + paragraph_start, n - paragraph_start, levels, first);
      paragraph_start = n;
    }
  }
  free(levels);
  if (!n) {
    free(order);
    order = NULL;
  }
  *out = order;
  *out_count = n;
  return exr_fail(e, EXR_OK, "");
}
void exr_bidi_free(exr_bidi *bidi) {
  if (bidi) {
    free(bidi->scalars);
    free(bidi->types);
    free(bidi->bases);
    free(bidi);
  }
}
