/* SPDX-License-Identifier: MIT */
#include "internal.h"
#include <ctype.h>

enum {
  FONT_SIZE,
  WEIGHT,
  ITALIC,
  COLOR,
  LEADING,
  ALIGN,
  INDENT,
  DISPLAY,
  WIDTH,
  HEIGHT,
  MAX_WIDTH,
  MT,
  MR,
  MB,
  ML,
  PT,
  PR,
  PB,
  PL,
  BACKGROUND,
  BORDER_WIDTH,
  BORDER_COLOR,
  BORDER_STYLE,
  BEFORE,
  AFTER,
  DIRECTION,
  FAMILY,
  DECORATION,
  WRITING_MODE,
  ORIENTATION,
  MAX_HEIGHT,
  RUBY_POSITION,
  RUBY_ALIGN,
  TABLE_LAYOUT,
  VERTICAL_ALIGN,
  BORDER_COLLAPSE,
  FLOAT_SIDE,
  CLEAR_SIDE,
  HYPHENS,
  /* Per-side borders, in CSS physical order (top, right, bottom, left) per
     sub-property. The blocks must stay consecutive: a `border` shorthand
     expands to all twelve in one run. */
  BORDER_TOP_WIDTH,
  BORDER_RIGHT_WIDTH,
  BORDER_BOTTOM_WIDTH,
  BORDER_LEFT_WIDTH,
  BORDER_TOP_COLOR,
  BORDER_RIGHT_COLOR,
  BORDER_BOTTOM_COLOR,
  BORDER_LEFT_COLOR,
  BORDER_TOP_STYLE,
  BORDER_RIGHT_STYLE,
  BORDER_BOTTOM_STYLE,
  BORDER_LEFT_STYLE,
  PROPERTIES
};
typedef struct {
  int property, important;
  char value[128];
} declaration;
typedef struct {
  char *selector;
  declaration *declarations;
  size_t count, chapter;
  int user;
} rule;
typedef struct {
  rule *rules;
  size_t count, capacity, bytes, declarations, work;
  exr_status failed;
  exr_font_rule *fonts;
  size_t font_count, font_capacity;
} css;
typedef struct {
  const char *value;
  uint64_t rank;
} winner;
static int ws(char c) { return c == ' ' || c == '\n' || c == '\r' || c == '\t' || c == '\f'; }
static const char *tag(const exr_node *n) {
  const char *p;
  if (!n->name)
    return "";
  p = strrchr(n->name, '|');
  return p ? p + 1 : n->name;
}
static int equal(const char *s, size_t n, const char *word) {
  size_t i;
  if (strlen(word) != n)
    return 0;
  for (i = 0; i < n; i++)
    if (tolower((unsigned char)s[i]) != word[i])
      return 0;
  return 1;
}
static int identifier(unsigned char c) { return isalnum(c) || c == '-' || c == '_' || c >= 128; }
static int word_in(const char *s, const char *word, size_t length) {
  while (s && *s) {
    const char *a;
    while (ws(*s))
      s++;
    a = s;
    while (*s && !ws(*s))
      s++;
    if ((size_t)(s - a) == length && !memcmp(a, word, length))
      return 1;
  }
  return 0;
}
typedef struct {
  const char *text;
  size_t size;
  int child;
} selector_part;
static int selector_parse(const char *s, size_t n, selector_part parts[16], unsigned *specificity) {
  size_t i = 0;
  int count = 0, child = 0;
  unsigned ids = 0, classes = 0, tags = 0;
  while (i < n && ws(s[i]))
    i++;
  while (i < n) {
    size_t start = i;
    if (count == 16)
      return 0;
    if (s[i] == '*')
      i++;
    else if (identifier((unsigned char)s[i])) {
      tags++;
      while (i < n && identifier((unsigned char)s[i]))
        i++;
    }
    while (i < n && (s[i] == '.' || s[i] == '#')) {
      char type = s[i++];
      size_t a = i;
      while (i < n && identifier((unsigned char)s[i]))
        i++;
      if (a == i)
        return 0;
      if (type == '#')
        ids++;
      else
        classes++;
    }
    if (start == i || (i < n && !ws(s[i]) && s[i] != '>'))
      return 0;
    parts[count].text = s + start;
    parts[count].size = i - start;
    parts[count++].child = child;
    while (i < n && ws(s[i]))
      i++;
    child = i < n && s[i] == '>';
    if (child) {
      i++;
      while (i < n && ws(s[i]))
        i++;
      if (i == n)
        return 0;
    }
  }
  if (ids > 255 || classes > 255 || tags > 255)
    return 0;
  *specificity = (ids << 16) | (classes << 8) | tags;
  return count;
}
static int part_matches(const exr_node *node, selector_part part) {
  size_t i = 0, start;
  const char *s = part.text, *value;
  if (node->kind == EXR_NODE_TEXT ||
      (!node->name && (node->kind == EXR_NODE_DOCUMENT || node->kind == EXR_NODE_CHAPTER)))
    return 0;
  if (s[0] == '*')
    i++;
  else if (identifier((unsigned char)s[0])) {
    while (i < part.size && identifier((unsigned char)s[i]))
      i++;
    value = tag(node);
    if (strlen(value) != i || memcmp(value, s, i))
      return 0;
  }
  while (i < part.size) {
    char type = s[i++];
    start = i;
    while (i < part.size && identifier((unsigned char)s[i]))
      i++;
    value = exr_node_attribute(node, type == '#' ? "id" : "class");
    if (type == '#') {
      if (!value || strlen(value) != i - start || memcmp(value, s + start, i - start))
        return 0;
    } else if (!word_in(value, s + start, i - start))
      return 0;
  }
  return 1;
}
static int selector_match(css *c, const exr_document *d, const selector_part *parts, int at,
                          size_t node) {
  size_t parent;
  if (++c->work > 20000000) {
    c->failed = EXR_LIMIT;
    return 0;
  }
  if (!part_matches(&d->nodes[node], parts[at]))
    return 0;
  if (!at)
    return 1;
  parent = d->nodes[node].parent;
  while (parent != SIZE_MAX) {
    if (selector_match(c, d, parts, at - 1, parent))
      return 1;
    if (parts[at].child || c->failed)
      break;
    parent = d->nodes[parent].parent;
  }
  return 0;
}
static int match(css *c, const exr_document *d, size_t node, const char *selectors,
                 unsigned *best) {
  const char *p = selectors;
  int found = 0;
  *best = 0;
  while (*p) {
    selector_part parts[16];
    unsigned specificity;
    size_t n = strcspn(p, ",");
    int count = selector_parse(p, n, parts, &specificity);
    if (count && selector_match(c, d, parts, count - 1, node)) {
      if (!found || specificity > *best)
        *best = specificity;
      found = 1;
    }
    p += n;
    if (*p)
      p++;
  }
  return found;
}
static int property(const char *s, size_t n) {
  static const char *names[PROPERTIES] = {
      "font-size",    "font-weight",   "font-style",     "color",         "line-height",
      "text-align",   "text-indent",   "display",        "width",         "height",
      "max-width",    "margin-top",    "margin-right",   "margin-bottom", "margin-left",
      "padding-top",  "padding-right", "padding-bottom", "padding-left",  "background-color",
      "border-width", "border-color",  "border-style",   "break-before",  "break-after", "direction",
      "font-family", "text-decoration-line", "writing-mode", "text-orientation", "max-height", "ruby-position", "ruby-align", "table-layout", "vertical-align", "border-collapse", "float", "clear", "hyphens",
      "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
      "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
      "border-top-style", "border-right-style", "border-bottom-style", "border-left-style"};
  int i;
  for (i = 0; i < PROPERTIES; i++)
    if (equal(s, n, names[i]))
      return i;
  if (equal(s, n, "text-decoration"))
    return DECORATION;
  if (equal(s, n, "page-break-before"))
    return BEFORE;
  if (equal(s, n, "page-break-after"))
    return AFTER;
  if (equal(s, n, "margin"))
    return PROPERTIES;
  if (equal(s, n, "padding"))
    return PROPERTIES + 1;
  if (equal(s, n, "border"))
    return PROPERTIES + 2;
  if (equal(s, n, "border-top"))
    return PROPERTIES + 3;
  if (equal(s, n, "border-right"))
    return PROPERTIES + 4;
  if (equal(s, n, "border-bottom"))
    return PROPERTIES + 5;
  if (equal(s, n, "border-left"))
    return PROPERTIES + 6;
  if (equal(s, n, "background"))
    return BACKGROUND;
  return -1;
}
/* Find a delimiter outside strings/functions. Unsupported constructs are skipped as units. */
size_t exr_css_delimiter(const char *s, size_t n, char wanted) {
  size_t i;
  int quote = 0, depth = 0;
  for (i = 0; i < n; i++) {
    char ch = s[i];
    if (ch == '\\' && i + 1 < n) {
      i++;
      continue;
    }
    if (quote) {
      if (ch == quote)
        quote = 0;
      continue;
    }
    if (ch == '\'' || ch == '"') {
      quote = ch;
      continue;
    }
    if (ch == '(' || ch == '[')
      depth++;
    else if ((ch == ')' || ch == ']') && depth)
      depth--;
    else if (!depth && ch == wanted)
      return i;
  }
  return n;
}
static char *clean_css(const char *s, size_t n) {
  char *out = malloc(n + 1);
  size_t i = 0, used = 0;
  int quote = 0;
  if (!out)
    return NULL;
  while (i < n) {
    if (!quote && i + 1 < n && s[i] == '/' && s[i + 1] == '*') {
      i += 2;
      while (i + 1 < n && !(s[i] == '*' && s[i + 1] == '/'))
        i++;
      i = i + 1 < n ? i + 2 : n;
      out[used++] = ' ';
    } else {
      char ch = s[i++];
      out[used++] = ch;
      if (ch == '\\' && i < n)
        out[used++] = s[i++];
      else if (quote && ch == quote)
        quote = 0;
      else if (!quote && (ch == '\'' || ch == '"'))
        quote = ch;
    }
  }
  out[used] = 0;
  return out;
}
static int length(const char *s, float em, float rem, int unitless, exr_length *out);
static int color(const char *s, uint32_t *out);
static int style_name(const char *v) {
  if (!strcmp(v, "none")) return 0;
  if (!strcmp(v, "solid")) return 1;
  if (!strcmp(v, "hidden")) return 2;
  if (!strcmp(v, "dashed")) return 3;
  if (!strcmp(v, "dotted")) return 4;
  if (!strcmp(v, "double")) return 5;
  return -1;
}
static int declarations(css *c, const char *s, size_t n, declaration **out, size_t *count) {
  size_t pos = 0, cap = 0;
  *out = NULL;
  *count = 0;
  while (pos < n) {
    size_t end = pos + exr_css_delimiter(s + pos, n - pos, ';'), colon, a, b;
    int prop, important = 0;
    char values[4][128] = {{0}};
    a = pos;
    while (a < end && ws(s[a]))
      a++;
    colon = a + exr_css_delimiter(s + a, end - a, ':');
    b = colon;
    while (b > a && ws(s[b - 1]))
      b--;
    prop = property(s + a, b - a);
    pos = end < n ? end + 1 : n;
    if (prop < 0 || colon == end)
      continue;
    a = colon + 1;
    while (a < end && ws(s[a]))
      a++;
    b = end;
    while (b > a && ws(s[b - 1]))
      b--;
    if (b - a >= 10 && equal(s + b - 9, 9, "important")) {
      size_t bang = b - 9;
      while (bang > a && ws(s[bang - 1]))
        bang--;
      if (bang > a && s[bang - 1] == '!') {
        important = 1;
        b = bang - 1;
        while (b > a && ws(s[b - 1]))
          b--;
      }
    }
    if (b == a || b - a >= 128)
      continue;
    {
      int targets[12], target_count = 0, t;
      char produced[12][128];
      if (prop == BORDER_WIDTH || prop == BORDER_COLOR || prop == BORDER_STYLE ||
          prop >= PROPERTIES) {
        size_t v = a;
        int lengths = 0;
        while (v < b && lengths < 4) {
          size_t start;
          while (v < b && ws(s[v]))
            v++;
          start = v;
          while (v < b && !ws(s[v]))
            v++;
          if (v > start)
            memcpy(values[lengths++], s + start, v - start);
        }
        while (v < b && ws(s[v]))
          v++;
        if (!lengths || v < b)
          continue;
        if (prop == PROPERTIES + 2 || (prop >= PROPERTIES + 3 && prop <= PROPERTIES + 6)) {
          /* border / border-top …: <width> || <style> || <color>, any order. */
          char parts[3][128] = {"3px", "black", "none"};
          int seen = 0, valid = 1;
          if (lengths > 3)
            continue;
          for (t = 0; t < lengths && valid; t++) {
            exr_length l;
            uint32_t rgba;
            int which;
            if (style_name(values[t]) >= 0)
              which = 2;
            else if (length(values[t], 1, 1, 0, &l) && !l.percent && l.value >= 0 && l.value <= 1024)
              which = 0;
            else if (color(values[t], &rgba))
              which = 1;
            else {
              valid = 0;
              break;
            }
            if (seen & (1 << which))
              valid = 0;
            else {
              seen |= 1 << which;
              strcpy(parts[which], values[t]);
            }
          }
          if (!valid)
            continue;
          if (prop == PROPERTIES + 2) {
            for (t = 0; t < 4; t++) {
              targets[target_count] = BORDER_TOP_WIDTH + t;
              strcpy(produced[target_count++], parts[0]);
              targets[target_count] = BORDER_TOP_COLOR + t;
              strcpy(produced[target_count++], parts[1]);
              targets[target_count] = BORDER_TOP_STYLE + t;
              strcpy(produced[target_count++], parts[2]);
            }
          } else {
            int side = prop - (PROPERTIES + 3);
            targets[target_count] = BORDER_TOP_WIDTH + side;
            strcpy(produced[target_count++], parts[0]);
            targets[target_count] = BORDER_TOP_COLOR + side;
            strcpy(produced[target_count++], parts[1]);
            targets[target_count] = BORDER_TOP_STYLE + side;
            strcpy(produced[target_count++], parts[2]);
          }
        } else if (prop == BORDER_WIDTH || prop == BORDER_COLOR || prop == BORDER_STYLE) {
          /* border-width/-color/-style accept one to four values, expanded like
             margin and padding. */
          int base = prop == BORDER_WIDTH ? BORDER_TOP_WIDTH :
                     prop == BORDER_COLOR ? BORDER_TOP_COLOR : BORDER_TOP_STYLE;
          for (t = 0; t < lengths; t++) {
            exr_length l;
            uint32_t rgba;
            if (prop == BORDER_WIDTH) {
              if (!length(values[t], 1, 1, 0, &l) || l.percent || l.value < 0 || l.value > 1024)
                break;
            } else if (prop == BORDER_COLOR) {
              if (!color(values[t], &rgba))
                break;
            } else if (style_name(values[t]) < 0)
              break;
          }
          if (t != lengths)
            continue;
          if (lengths == 1)
            strcpy(values[1], values[0]);
          if (lengths < 3)
            strcpy(values[2], values[0]);
          if (lengths < 4)
            strcpy(values[3], values[1]);
          for (t = 0; t < 4; t++) {
            targets[target_count] = base + t;
            strcpy(produced[target_count++], values[t]);
          }
        } else {
          int base = prop == PROPERTIES ? MT : PT;
          for (t = 0; t < lengths; t++) {
            exr_length l;
            if (!length(values[t], 1, 1, 0, &l) || (prop == PROPERTIES + 1 && l.value < 0))
              break;
          }
          if (t != lengths)
            continue;
          if (lengths == 1)
            strcpy(values[1], values[0]);
          if (lengths < 3)
            strcpy(values[2], values[0]);
          if (lengths < 4)
            strcpy(values[3], values[1]);
          for (t = 0; t < 4; t++) {
            targets[target_count] = base + t;
            strcpy(produced[target_count++], values[t]);
          }
        }
      } else {
        targets[0] = prop;
        memcpy(produced[0], s + a, b - a);
        produced[0][b - a] = 0;
        target_count = 1;
      }
      for (t = 0; t < target_count; t++) {
        declaration *v;
        if (++c->declarations > 131072 || *count >= 256 ||
            !exr_grow((void **)out, &cap, *count + 1, sizeof(**out))) {
          c->failed = EXR_LIMIT;
          return 0;
        }
        v = &(*out)[(*count)++];
        v->property = targets[t];
        v->important = important;
        strcpy(v->value, produced[t]);
      }
    }
  }
  return 1;
}
static int stylesheet(css *c, const char *source, size_t n, size_t chapter, int user,
                         const char *base, int embedded_fonts) {
  char *s;
  size_t i = 0;
  if (n > 1024 * 1024 - c->bytes) {
    c->failed = EXR_LIMIT;
    return 0;
  }
  c->bytes += n;
  s = clean_css(source, n);
  if (!s) {
    c->failed = EXR_MEMORY;
    return 0;
  }
  n = strlen(s);
  while (i < n) {
    size_t start, open, close, end;
    int depth = 1, quote = 0;
    rule *r;
    while (i < n && ws(s[i]))
      i++;
    start = i;
    open = i + exr_css_delimiter(s + i, n - i, '{');
    end = i + exr_css_delimiter(s + i, n - i, ';');
    if (s[i] == '@' && end < open) {
      i = end + 1;
      continue;
    }
    if (open == n)
      break;
    close = open + 1;
    for (; close < n; close++) {
      char ch = s[close];
      if (ch == '\\' && close + 1 < n) {
        close++;
        continue;
      }
      if (quote) {
        if (ch == quote)
          quote = 0;
        continue;
      }
      if (ch == '\'' || ch == '"')
        quote = ch;
      else if (ch == '{')
        depth++;
      else if (ch == '}' && !--depth)
        break;
    }
    if (close == n)
      break;
    i = close + 1;
    end = open;
    while (end > start && ws(s[end - 1])) end--;
    if (embedded_fonts && equal(s + start, end - start, "@font-face")) {
      exr_font_rule font;
      if (exr_parse_font_rule(s + open + 1, close - open - 1, base, chapter, &font)) {
        if (c->font_count >= 64 ||
            !exr_grow((void **)&c->fonts, &c->font_capacity, c->font_count + 1, sizeof(font))) {
          c->failed = EXR_LIMIT;
          break;
        }
        c->fonts[c->font_count++] = font;
      }
      continue;
    }
    if (s[start] == '@' || open - start > 512)
      continue;
    if (c->count >= 4096 ||
        !exr_grow((void **)&c->rules, &c->capacity, c->count + 1, sizeof(rule))) {
      c->failed = EXR_LIMIT;
      break;
    }
    r = &c->rules[c->count++];
    memset(r, 0, sizeof(*r));
    r->chapter = chapter;
    r->user = user;
    r->selector = exr_copy(s + start, open - start);
    if (!r->selector) {
      c->failed = EXR_MEMORY;
      break;
    }
    if (!declarations(c, s + open + 1, close - open - 1, &r->declarations, &r->count))
      break;
  }
  free(s);
  return !c->failed;
}
static int length(const char *s, float em, float rem, int unitless, exr_length *out) {
  char *end;
  float v;
  if (!strcmp(s, "auto")) {
    *out = (exr_length){-1, 0};
    return 1;
  }
  v = strtof(s, &end);
  if (end == s || !isfinite(v) || v < 0 || v > 10000)
    return 0;
  out->percent = 0;
  if (!strcmp(end, "em"))
    v *= em;
  else if (!strcmp(end, "rem"))
    v *= rem;
  else if (!strcmp(end, "pt"))
    v *= 96.0f / 72;
  else if (!strcmp(end, "%")) {
    v /= 100;
    out->percent = 1;
  } else if (strcmp(end, "px") && (*end || (!unitless && v != 0)))
    return 0;
  if (!isfinite(v) || v > 10000)
    return 0;
  out->value = v;
  return 1;
}
static int color(const char *s, uint32_t *out) {
  static const struct {
    const char *name;
    uint32_t value;
  } named[] = {{"black", 0x000000ff},  {"white", 0xffffffff},  {"red", 0xff0000ff},
               {"green", 0x008000ff},  {"blue", 0x0000ffff},   {"gray", 0x808080ff},
               {"grey", 0x808080ff},   {"transparent", 0},     {"navy", 0x000080ff},
               {"yellow", 0xffff00ff}, {"orange", 0xffa500ff}, {"purple", 0x800080ff}};
  size_t i, n = strlen(s);
  if (s[0] == '#' && (n == 4 || n == 5 || n == 7 || n == 9)) {
    uint32_t v = 0;
    for (i = 1; i < n; i++) {
      unsigned ch = (unsigned char)s[i], digit;
      if (!isxdigit(ch))
        return 0;
      digit = isdigit(ch) ? ch - '0' : (unsigned)tolower(ch) - 'a' + 10;
      v = n < 6 ? (v << 8) | (digit * 17) : (v << 4) | digit;
    }
    if (n == 4 || n == 7)
      v = (v << 8) | 255;
    *out = v;
    return 1;
  }
  for (i = 0; i < sizeof(named) / sizeof(*named); i++)
    if (equal(s, n, named[i].name)) {
      *out = named[i].value;
      return 1;
    }
  return 0;
}
static int apply(exr_style *s, const exr_style *parent, int prop, const char *v, float root) {
  exr_length l;
  float number;
  char *end;
  uint32_t rgba;
  if (!strcmp(v, "inherit")) {
    if (prop == FAMILY)
      s->family = parent->family;
    else if (prop == FONT_SIZE)
      s->font_size = parent->font_size;
    else if (prop == WEIGHT)
      s->flags = (s->flags & ~1u) | (parent->flags & 1u);
    else if (prop == ITALIC)
      s->flags = (s->flags & ~2u) | (parent->flags & 2u);
    else if (prop == DECORATION)
      s->flags=(s->flags & ~EXR_DECORATIONS) | (parent->flags & EXR_DECORATIONS);
    else if (prop == COLOR)
      s->color = parent->color;
    else if (prop == LEADING) {
      s->leading = parent->leading;
      s->leading_relative = parent->leading_relative;
    } else if (prop == ALIGN)
      s->align = parent->align;
    else if (prop == DIRECTION)
      s->direction = parent->direction;
    else if (prop == WRITING_MODE)
      s->writing_mode = parent->writing_mode;
    else if (prop == ORIENTATION)
      s->orientation = parent->orientation;
    else if (prop == RUBY_POSITION)
      s->ruby_position = parent->ruby_position;
    else if (prop == RUBY_ALIGN)
      s->ruby_align = parent->ruby_align;
    else if (prop == INDENT)
      s->indent = parent->indent;
    else if (prop == TABLE_LAYOUT)
      s->table_fixed = parent->table_fixed;
    else if (prop == VERTICAL_ALIGN)
      s->vertical_align = parent->vertical_align;
    else if (prop == BORDER_COLLAPSE)
      s->border_collapse = parent->border_collapse;
    else if (prop == FLOAT_SIDE)
      s->float_side = parent->float_side;
    else if (prop == CLEAR_SIDE)
      s->clear_side = parent->clear_side;
    else if (prop == HYPHENS)
      s->hyphens = parent->hyphens;
    else if (prop >= BORDER_TOP_WIDTH && prop <= BORDER_LEFT_STYLE) {
      int kind = (prop - BORDER_TOP_WIDTH) / 4, side = (prop - BORDER_TOP_WIDTH) % 4;
      if (kind == 0)
        s->border_width[side] = parent->border_width[side];
      else if (kind == 1)
        s->border_color[side] = parent->border_color[side];
      else
        s->border_style[side] = parent->border_style[side];
    } else
      return 0;
    return 1;
  }
  if (prop == FAMILY) {
    size_t at = 0;
    char family[128];
    int result, count = 0;
    while ((result = exr_family_next(v, &at, family)) == 1) count++;
    if (!count || result < 0) return 0;
    s->family = v;
  } else if (prop == WRITING_MODE) {
    if (!strcmp(v, "horizontal-tb")) s->writing_mode = EXR_WRITING_HORIZONTAL_TB;
    else if (!strcmp(v, "vertical-rl")) s->writing_mode = EXR_WRITING_VERTICAL_RL;
    else if (!strcmp(v, "vertical-lr")) s->writing_mode = EXR_WRITING_VERTICAL_LR;
    else return 0;
  } else if (prop == ORIENTATION) {
    if (!strcmp(v, "mixed")) s->orientation = EXR_ORIENTATION_MIXED;
    else if (!strcmp(v, "upright")) s->orientation = EXR_ORIENTATION_UPRIGHT;
    else if (!strcmp(v, "sideways")) s->orientation = EXR_ORIENTATION_SIDEWAYS;
    else return 0;
  } else if (prop == RUBY_POSITION) {
    if (!strcmp(v,"over")) s->ruby_position=0;
    else if (!strcmp(v,"under")) s->ruby_position=1;
    else return 0;
  } else if (prop == RUBY_ALIGN) {
    if (!strcmp(v,"center")) s->ruby_align=0;
    else if (!strcmp(v,"start")) s->ruby_align=1;
    else if (!strcmp(v,"space-between")) s->ruby_align=2;
    else if (!strcmp(v,"space-around")) s->ruby_align=3;
    else return 0;
  } else if (prop == DIRECTION) {
    if (!strcmp(v, "ltr")) s->direction = EXR_DIRECTION_LTR;
    else if (!strcmp(v, "rtl")) s->direction = EXR_DIRECTION_RTL;
    else return 0;
  } else if (prop == COLOR || prop == BACKGROUND || prop == BORDER_COLOR) {
    int side;
    if (!color(v, &rgba))
      return 0;
    if (prop == COLOR)
      s->color = rgba;
    else if (prop == BACKGROUND)
      s->background = rgba;
    else
      for (side = 0; side < 4; side++)
        s->border_color[side] = rgba;
  } else if (prop == FONT_SIZE) {
    if (!length(v, parent->font_size, root, 0, &l) || l.value < 0)
      return 0;
    number = l.percent ? l.value * parent->font_size : l.value;
    if (number < 4 || number > 256)
      return 0;
    s->font_size = number;
  } else if (prop == LEADING) {
    if (!strcmp(v, "normal")) {
      s->leading = 1.2f;
      s->leading_relative = 1;
      return 1;
    }
    number = strtof(v, &end);
    if (end != v && !*end && isfinite(number) && number >= 0.8f && number <= 10) {
      s->leading = number;
      s->leading_relative = 1;
      return 1;
    }
    if (!length(v, s->font_size, root, 0, &l) || l.value < 0)
      return 0;
    s->leading = l.percent ? l.value * s->font_size : l.value;
    s->leading_relative = 0;
  } else if (prop == WEIGHT) {
    if (!strcmp(v, "bold") || !strcmp(v, "bolder"))
      s->flags |= 1;
    else if (!strcmp(v, "normal") || !strcmp(v, "lighter"))
      s->flags &= ~1u;
    else {
      number = strtof(v, &end);
      if (*end || end == v || !isfinite(number) || number < 100 || number > 900)
        return 0;
      if (number >= 600)
        s->flags |= 1;
      else
        s->flags &= ~1u;
    }
  } else if (prop == ITALIC) {
    if (!strcmp(v, "italic") || !strcmp(v, "oblique"))
      s->flags |= 2;
    else if (!strcmp(v, "normal"))
      s->flags &= ~2u;
    else
      return 0;
  } else if (prop == DECORATION) {
    unsigned flags=0; size_t at=0;
    if(strcmp(v,"none")) {
      while(v[at]) {
        size_t start;
        while(ws(v[at])) at++;
        start=at; while(v[at] && !ws(v[at])) at++;
        if(at==start) break;
        if(equal(v+start,at-start,"underline")) flags|=EXR_GLYPH_UNDERLINE;
        else if(equal(v+start,at-start,"line-through")) flags|=EXR_GLYPH_STRIKE;
        else return 0;
      }
      if(!flags) return 0;
    }
    s->flags=(s->flags & ~EXR_DECORATIONS)|flags;
  } else if (prop == ALIGN) {
    if (!strcmp(v, "left"))
      s->align = 0;
    else if (!strcmp(v, "center"))
      s->align = 1;
    else if (!strcmp(v, "right"))
      s->align = 2;
    else if (!strcmp(v, "start"))
      s->align = 4;
    else if (!strcmp(v, "end"))
      s->align = 5;
    else if (!strcmp(v, "justify"))
      s->align = 3;
    else
      return 0;
  } else if (prop == VERTICAL_ALIGN) {
    if(!strcmp(v,"baseline")) s->vertical_align=EXR_CELL_BASELINE;
    else if(!strcmp(v,"top")) s->vertical_align=EXR_CELL_TOP;
    else if(!strcmp(v,"middle")) s->vertical_align=EXR_CELL_MIDDLE;
    else if(!strcmp(v,"bottom")) s->vertical_align=EXR_CELL_BOTTOM;
    else if(!strcmp(v,"sub") || !strcmp(v,"super") || !strcmp(v,"text-top") || !strcmp(v,"text-bottom") ||
            (length(v[0]=='-' ? v+1 : v,s->font_size,root,0,&l) && l.value>=0)) s->vertical_align=EXR_CELL_BASELINE;
    else return 0;
  } else if(prop==HYPHENS) {
    if(!strcmp(v,"none")) s->hyphens=EXR_HYPHENS_NONE;
    else if(!strcmp(v,"manual")) s->hyphens=EXR_HYPHENS_MANUAL;
    else if(!strcmp(v,"auto")) s->hyphens=EXR_HYPHENS_AUTO;
    else return 0;
  } else if (prop == FLOAT_SIDE || prop == CLEAR_SIDE) {
    int side;
    if(!strcmp(v,"none")) side=0;
    else if(!strcmp(v,"left")) side=1;
    else if(!strcmp(v,"right")) side=2;
    else if(prop==CLEAR_SIDE && !strcmp(v,"both")) side=3;
    else return 0;
    if(prop==FLOAT_SIDE) s->float_side=side; else s->clear_side=side;
  } else if (prop == BORDER_COLLAPSE) {
    if(!strcmp(v,"collapse")) s->border_collapse=1;
    else if(!strcmp(v,"separate")) s->border_collapse=0;
    else return 0;
  } else if (prop == TABLE_LAYOUT) {
    if(!strcmp(v,"fixed")) s->table_fixed=1;
    else if(!strcmp(v,"auto")) s->table_fixed=0;
    else return 0;
  } else if (prop == DISPLAY) {
    if (!strcmp(v, "none"))
      s->display = EXR_CSS_NONE;
    else if (!strcmp(v, "block"))
      s->display = EXR_CSS_BLOCK;
    else if (!strcmp(v, "inline"))
      s->display = EXR_CSS_INLINE;
    else if (!strcmp(v, "table"))
      s->display = EXR_CSS_TABLE;
    else if (!strcmp(v, "table-row"))
      s->display = EXR_CSS_ROW;
    else if (!strcmp(v, "table-cell"))
      s->display = EXR_CSS_CELL;
    else
      return 0;
  } else if (prop == BORDER_STYLE) {
    int style = style_name(v), side;
    if (style < 0)
      return 0;
    for (side = 0; side < 4; side++)
      s->border_style[side] = style;
  } else if (prop == BEFORE || prop == AFTER) {
    int page = !strcmp(v, "page") || !strcmp(v, "always");
    if (!page && strcmp(v, "auto"))
      return 0;
    if (prop == BEFORE)
      s->before = page;
    else
      s->after = page;
  } else if (prop >= BORDER_TOP_WIDTH && prop <= BORDER_LEFT_STYLE) {
    int kind = (prop - BORDER_TOP_WIDTH) / 4, side = (prop - BORDER_TOP_WIDTH) % 4;
    if (kind == 0) {
      if (!length(v, s->font_size, root, 0, &l) || l.percent || l.value < 0 || l.value > 1024)
        return 0;
      s->border_width[side] = l.value;
    } else if (kind == 1) {
      if (!color(v, &rgba))
        return 0;
      s->border_color[side] = rgba;
    } else {
      int style = style_name(v);
      if (style < 0)
        return 0;
      s->border_style[side] = style;
    }
  } else {
    if (!length(v, s->font_size, root, 0, &l))
      return 0;
    if (prop == WIDTH)
      s->width = l;
    else if (prop == HEIGHT)
      s->height = l;
    else if (prop == MAX_WIDTH)
      s->max_width = l;
    else if (prop == MAX_HEIGHT)
      s->max_height = l;
    else if (prop >= MT && prop <= ML)
      s->margin[prop - MT] = l;
    else if (prop >= PT && prop <= PL) {
      if (l.value < 0)
        return 0;
      s->padding[prop - PT] = l;
    } else if (prop == INDENT || prop == BORDER_WIDTH) {
      int side;
      if (l.percent || l.value < 0 || l.value > 1024)
        return 0;
      if (prop == INDENT)
        s->indent = l.value;
      else
        for (side = 0; side < 4; side++)
          s->border_width[side] = l.value;
    } else
      return 0;
  }
  return 1;
}
static void compete(winner *w, const declaration *a, size_t count, uint64_t base,
                    const exr_style *style, const exr_style *parent, float root) {
  size_t i;
  for (i = 0; i < count; i++) {
    exr_style trial = *style;
    uint64_t rank = base + i + 1;
    if (a[i].important)
      rank |= UINT64_C(1) << 60;
    if (rank >= w[a[i].property].rank && apply(&trial, parent, a[i].property, a[i].value, root)) {
      w[a[i].property].value = a[i].value;
      w[a[i].property].rank = rank;
    }
  }
}
exr_status exr_compute_styles(const exr_document *d, const exr_layout_config *config,
                              exr_style **out, exr_font_rule **fonts, size_t *font_count,
                              exr_error *e) {
  css c = {0};
  exr_style *styles = NULL, initial = {0};
  const exr_layout_options *o = &config->page;
  size_t i, r, family_bytes = 0;
  int side;
  initial.font_size = o->font_size;
  initial.leading = o->line_height;
  initial.leading_relative = 1;
  initial.color = 255;
  for (side = 0; side < 4; side++) {
    initial.border_color[side] = 255;
    initial.border_width[side] = 3;
  }
  initial.width.value = initial.height.value = initial.max_width.value = initial.max_height.value = -1;
  initial.display = EXR_CSS_BLOCK;
  initial.direction = config->direction;
  initial.align = 4;
  *out = NULL;
  *fonts = NULL;
  *font_count = 0;
  c.failed = exr_control_poll(&config->control, EXR_STAGE_STYLE, 0, d->node_count, e);
  if (c.failed) goto done;
  if (config->document_css)
    for (i = 0; i < d->node_count; i++) {
      const exr_node *n = &d->nodes[i];
      if (!strcmp(exr_html_tag(d, n), "style")) {
        size_t child;
        for (child = n->first_child; child != SIZE_MAX; child = d->nodes[child].next_sibling)
          if (d->nodes[child].text &&
              !stylesheet(&c, d->nodes[child].text, strlen(d->nodes[child].text), n->chapter, 0,
                           n->chapter < d->chapter_count ? d->chapters[n->chapter].path : "",
                           config->embedded_fonts))
            goto done;
      } else if (!strcmp(exr_html_tag(d, n), "link") &&
                 word_in(exr_node_attribute(n, "rel"), "stylesheet", 10)) {
        const char *href = exr_node_attribute(n, "href");
        size_t resource, target, size;
        void *bytes = NULL;
        exr_error ignored = {0};
        exr_buffer decoded = {0};
        if (!href ||
            exr_document_resolve(d, n->chapter, href, &resource, &target, &ignored) != EXR_OK ||
            resource == SIZE_MAX)
          continue;
        c.failed = exr_document_resource(d, resource, &bytes, &size, e);
        if (c.failed)
          goto done;
        c.failed = exr_decode(bytes, size, &decoded, e);
        exr_free(bytes);
        if (!c.failed)
          stylesheet(&c, decoded.data ? decoded.data : "", decoded.size, n->chapter, 0,
                       d->resources[resource].path, config->embedded_fonts);
        free(decoded.data);
        if (c.failed)
          goto done;
      }
    }
  if (config->user_css && !stylesheet(&c, config->user_css, strlen(config->user_css), SIZE_MAX, 1,
                                      "", config->embedded_fonts))
    goto done;
  styles = calloc(d->node_count, sizeof(*styles));
  if (!styles) {
    c.failed = EXR_MEMORY;
    goto done;
  }
  for (i = 0; i < d->node_count; i++) {
    const exr_node *n = &d->nodes[i];
    if (!(i & 127)) {
      c.failed = exr_control_poll(&config->control, EXR_STAGE_STYLE, i, d->node_count, e);
      if (c.failed) goto done;
    }
    const exr_style *parent = n->parent == SIZE_MAX ? &initial : &styles[n->parent];
    exr_style *s = &styles[i];
    winner w[PROPERTIES] = {{0}};
    declaration *inline_declarations = NULL;
    size_t inline_count = 0;
    const char *name = exr_html_tag(d, n), *attr;
    int p;
    *s = initial;
    s->font_size = parent->font_size;
    s->family = parent->family;
    s->flags = parent->flags;
    s->color = parent->color;
    s->leading = parent->leading;
    s->leading_relative = parent->leading_relative;
    s->align = parent->align;
    s->direction = parent->direction;
    s->writing_mode = parent->writing_mode;
    s->orientation = parent->orientation;
    s->ruby_position = parent->ruby_position;
    s->ruby_align = parent->ruby_align;
    s->indent = parent->indent;
    s->border_collapse = parent->border_collapse;
    s->hyphens = parent->hyphens;
    s->display = EXR_CSS_INLINE;
    /* HTML table defaults; other host-defined elements retain the CSS initial
       baseline value unless the author explicitly inherits it. */
    if(!strcmp(name,"thead") || !strcmp(name,"tbody") || !strcmp(name,"tfoot")) s->vertical_align=EXR_CELL_MIDDLE;
    if(!strcmp(name,"tr") || !strcmp(name,"td") || !strcmp(name,"th")) s->vertical_align=parent->vertical_align;
    attr=exr_node_attribute(n,"valign");
    if(attr && (n->kind==EXR_NODE_CELL || n->kind==EXR_NODE_ROW || !strcmp(name,"thead") || !strcmp(name,"tbody") || !strcmp(name,"tfoot"))) {
      size_t length=strlen(attr);
      if(equal(attr,length,"top")) s->vertical_align=EXR_CELL_TOP;
      else if(equal(attr,length,"middle")) s->vertical_align=EXR_CELL_MIDDLE;
      else if(equal(attr,length,"bottom")) s->vertical_align=EXR_CELL_BOTTOM;
      else if(equal(attr,length,"baseline")) s->vertical_align=EXR_CELL_BASELINE;
    }
    if (!strcmp(name,"rtc") || (!strcmp(name,"rt") &&
        (n->parent==SIZE_MAX || strcmp(exr_html_tag(d,&d->nodes[n->parent]),"rtc"))))
      s->font_size=fmaxf(4,parent->font_size*.5f);
    if (!strcmp(name,"rp")) s->display=EXR_CSS_NONE;
    attr = exr_node_attribute(n, "dir");
    if (attr) {
      if (!strcmp(attr, "rtl")) s->direction = EXR_DIRECTION_RTL;
      else if (!strcmp(attr, "ltr")) s->direction = EXR_DIRECTION_LTR;
      else if (!strcmp(attr, "auto")) s->direction = EXR_DIRECTION_AUTO;
    }
    if (n->kind == EXR_NODE_DOCUMENT || n->kind == EXR_NODE_CHAPTER ||
        n->kind == EXR_NODE_SECTION || n->kind == EXR_NODE_PARAGRAPH ||
        n->kind == EXR_NODE_HEADING || n->kind == EXR_NODE_LIST || n->kind == EXR_NODE_LIST_ITEM ||
        n->kind == EXR_NODE_NOTE || !strcmp(name, "div") || !strcmp(name, "body") ||
        !strcmp(name, "html") || !strcmp(name, "figure") || !strcmp(name, "figcaption") ||
        !strcmp(name, "blockquote") || !strcmp(name, "pre"))
      s->display = EXR_CSS_BLOCK;
    if (n->kind == EXR_NODE_PARAGRAPH || n->kind == EXR_NODE_HEADING)
      s->margin[2].value = o->paragraph_spacing;
    if (n->kind == EXR_NODE_HEADING) {
      s->font_size = fminf(256, s->font_size * 1.35f);
      s->flags |= 1;
    }
    if (!strcmp(name, "strong") || !strcmp(name, "b") || !strcmp(name, "th"))
      s->flags |= 1;
    if (!strcmp(name, "em") || !strcmp(name, "i"))
      s->flags |= 2;
    if (!strcmp(name,"u")) s->flags|=EXR_GLYPH_UNDERLINE;
    if (!strcmp(name,"s") || !strcmp(name,"strike") || !strcmp(name,"del")) s->flags|=EXR_GLYPH_STRIKE;
    if (n->kind == EXR_NODE_LIST)
      s->padding[3].value = s->font_size;
    if (n->kind == EXR_NODE_TABLE)
      s->display = EXR_CSS_TABLE;
    if (n->kind == EXR_NODE_ROW)
      s->display = EXR_CSS_ROW;
    if (n->kind == EXR_NODE_CELL) {
      s->display = EXR_CSS_CELL;
    }
    if (n->kind == EXR_NODE_IMAGE || n->kind == EXR_NODE_CELL || n->kind == EXR_NODE_TABLE ||
        !strcmp(name,"col") || !strcmp(name,"colgroup")) {
      attr = exr_node_attribute(n, "width");
      if (attr)
        length(attr, s->font_size, o->font_size, 1, &s->width);
      attr = exr_node_attribute(n, "height");
      if (attr)
        length(attr, s->font_size, o->font_size, 1, &s->height);
    }
    for (r = 0; r < c.count; r++) {
      rule *v = &c.rules[r];
      unsigned specificity;
      if (++c.work > 20000000) {
        c.failed = EXR_LIMIT;
        goto done;
      }
      if ((v->chapter == SIZE_MAX || v->chapter == n->chapter) &&
          match(&c, d, i, v->selector, &specificity)) {
        uint64_t rank = ((uint64_t)specificity << 24) | ((uint64_t)r << 8);
        if (v->user)
          rank |= UINT64_C(1) << 62;
        compete(w, v->declarations, v->count, rank, s, parent, o->font_size);
      }
      if (c.failed)
        goto done;
    }
    attr = config->document_css ? exr_node_attribute(n, "style") : NULL;
    if (attr) {
      char *clean = clean_css(attr, strlen(attr));
      if (!clean) {
        c.failed = EXR_MEMORY;
        goto done;
      }
      declarations(&c, clean, strlen(clean), &inline_declarations, &inline_count);
      free(clean);
      if (c.failed) {
        free(inline_declarations);
        goto done;
      }
      compete(w, inline_declarations, inline_count, UINT64_C(1) << 56, s, parent, o->font_size);
    }
    for (p = 0; p < PROPERTIES; p++)
      if (w[p].value)
        apply(s, parent, p, w[p].value, o->font_size);
    s->writing_declared = w[WRITING_MODE].value != NULL;
    if(s->float_side && s->display!=EXR_CSS_NONE && s->display!=EXR_CSS_TABLE) s->display=EXR_CSS_BLOCK;
    if (s->writing_mode != EXR_WRITING_HORIZONTAL_TB) {
      if ((n->kind == EXR_NODE_PARAGRAPH || n->kind == EXR_NODE_HEADING) && !w[MB].value) {
        int end = s->writing_mode == EXR_WRITING_VERTICAL_RL ? ML : MR;
        s->margin[2].value = 0;
        if (!w[end].value) s->margin[end - MT].value = o->paragraph_spacing;
      }
      if (n->kind == EXR_NODE_LIST && !w[PL].value) {
        s->padding[3].value = 0;
        if (!w[PT].value) s->padding[0].value = s->font_size;
      }
    }
    s->flags |= parent->flags & EXR_DECORATIONS;
    if (s->family && s->family != parent->family) {
      if (parent->family && !strcmp(parent->family, s->family)) s->family = parent->family;
      else {
        size_t length = strlen(s->family) + 1;
        const char *copy = NULL;
        if (length <= 1024 * 1024 - family_bytes) copy = exr_copy(s->family, length - 1);
        if (!copy) {
          s->family = NULL;
          free(inline_declarations);
          c.failed = length > 1024 * 1024 - family_bytes ? EXR_LIMIT : EXR_MEMORY;
          goto done;
        }
        family_bytes += length;
        s->family = copy;
        s->family_owned = 1;
      }
    }
    free(inline_declarations);
    if ((n->parent != SIZE_MAX && parent->display == EXR_CSS_NONE) || !strcmp(name, "head") ||
        !strcmp(name, "script") || !strcmp(name, "style") || !strcmp(name, "template") ||
        exr_node_attribute(n, "hidden"))
      s->display = EXR_CSS_NONE;
  }
done:
  for (i = 0; i < c.count; i++) {
    free(c.rules[i].selector);
    free(c.rules[i].declarations);
  }
  free(c.rules);
  if (c.failed) {
    exr_styles_free(styles, d->node_count);
    free(c.fonts);
    return exr_fail(e, c.failed, c.failed == EXR_CANCELLED ? "Operation cancelled" :
                     "Stylesheet decoding or complexity limit failed");
  }
  *out = styles;
  *fonts = c.fonts;
  *font_count = c.font_count;
  return EXR_OK;
}
void exr_styles_free(exr_style *styles, size_t count) {
  size_t i;
  if (!styles) return;
  for (i = 0; i < count; i++)
    if (styles[i].family_owned) free((void *)styles[i].family);
  free(styles);
}
