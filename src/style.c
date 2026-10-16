/* SPDX-License-Identifier: GPL-3.0-only */
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
  if (!node->name)
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
      "border-width", "border-color",  "border-style",   "break-before",  "break-after"};
  int i;
  for (i = 0; i < PROPERTIES; i++)
    if (equal(s, n, names[i]))
      return i;
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
  if (equal(s, n, "background"))
    return BACKGROUND;
  return -1;
}
/* Find a delimiter outside strings/functions. Unsupported constructs are skipped as units. */
static size_t delimiter(const char *s, size_t n, char wanted) {
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
static int declarations(css *c, const char *s, size_t n, declaration **out, size_t *count) {
  size_t pos = 0, cap = 0;
  *out = NULL;
  *count = 0;
  while (pos < n) {
    size_t end = pos + delimiter(s + pos, n - pos, ';'), colon, a, b, k;
    int prop, important = 0, copies = 1;
    char values[4][128] = {{0}};
    a = pos;
    while (a < end && ws(s[a]))
      a++;
    colon = a + delimiter(s + a, end - a, ':');
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
    if (prop >= PROPERTIES) {
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
      if (prop == PROPERTIES + 2) {
        char border_values[3][128] = {"3px", "black", "none"};
        int t, seen = 0, valid = 1;
        if (lengths > 3)
          continue;
        for (t = 0; t < lengths; t++) {
          exr_length l;
          uint32_t rgba;
          int which;
          if (!strcmp(values[t], "solid") || !strcmp(values[t], "none"))
            which = 2;
          else if (length(values[t], 1, 1, 0, &l) && !l.percent && l.value >= 0 && l.value <= 1024)
            which = 0;
          else if (color(values[t], &rgba))
            which = 1;
          else {
            valid = 0;
            break;
          }
          if (seen & (1 << which)) {
            valid = 0;
            break;
          }
          seen |= 1 << which;
          strcpy(border_values[which], values[t]);
        }
        if (!valid)
          continue;
        for (t = 0; t < 3; t++)
          strcpy(values[t], border_values[t]);
        prop = BORDER_WIDTH;
        copies = 3;
      } else {
        int t;
        exr_length l;
        for (t = 0; t < lengths; t++)
          if (!length(values[t], 1, 1, 0, &l) || (prop == PROPERTIES + 1 && l.value < 0))
            break;
        if (t != lengths)
          continue;
        if (lengths == 1)
          strcpy(values[1], values[0]);
        if (lengths < 3)
          strcpy(values[2], values[0]);
        if (lengths < 4)
          strcpy(values[3], values[1]);
        prop = prop == PROPERTIES ? MT : PT;
        copies = 4;
      }
    } else
      memcpy(values[0], s + a, b - a);
    for (k = 0; k < (size_t)copies; k++) {
      declaration *v;
      if (++c->declarations > 131072 || *count >= 256 ||
          !exr_grow((void **)out, &cap, *count + 1, sizeof(**out))) {
        c->failed = EXR_LIMIT;
        return 0;
      }
      v = &(*out)[(*count)++];
      v->property = prop + (int)k;
      v->important = important;
      strcpy(v->value, values[k]);
    }
  }
  return 1;
}
static int stylesheet(css *c, const char *source, size_t n, size_t chapter, int user) {
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
    open = i + delimiter(s + i, n - i, '{');
    end = i + delimiter(s + i, n - i, ';');
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
    if (prop == FONT_SIZE)
      s->font_size = parent->font_size;
    else if (prop == WEIGHT)
      s->flags = (s->flags & ~1u) | (parent->flags & 1u);
    else if (prop == ITALIC)
      s->flags = (s->flags & ~2u) | (parent->flags & 2u);
    else if (prop == COLOR)
      s->color = parent->color;
    else if (prop == LEADING) {
      s->leading = parent->leading;
      s->leading_relative = parent->leading_relative;
    } else if (prop == ALIGN)
      s->align = parent->align;
    else if (prop == INDENT)
      s->indent = parent->indent;
    else
      return 0;
    return 1;
  }
  if (prop == COLOR || prop == BACKGROUND || prop == BORDER_COLOR) {
    if (!color(v, &rgba))
      return 0;
    if (prop == COLOR)
      s->color = rgba;
    else if (prop == BACKGROUND)
      s->background = rgba;
    else
      s->border_color = rgba;
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
  } else if (prop == ALIGN) {
    if (!strcmp(v, "left") || !strcmp(v, "start"))
      s->align = 0;
    else if (!strcmp(v, "center"))
      s->align = 1;
    else if (!strcmp(v, "right") || !strcmp(v, "end"))
      s->align = 2;
    else if (!strcmp(v, "justify"))
      s->align = 3;
    else
      return 0;
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
    if (!strcmp(v, "solid"))
      s->border_style = 1;
    else if (!strcmp(v, "none") || !strcmp(v, "hidden"))
      s->border_style = 0;
    else
      return 0;
  } else if (prop == BEFORE || prop == AFTER) {
    int page = !strcmp(v, "page") || !strcmp(v, "always");
    if (!page && strcmp(v, "auto"))
      return 0;
    if (prop == BEFORE)
      s->before = page;
    else
      s->after = page;
  } else {
    if (!length(v, s->font_size, root, 0, &l))
      return 0;
    if (prop == WIDTH)
      s->width = l;
    else if (prop == HEIGHT)
      s->height = l;
    else if (prop == MAX_WIDTH)
      s->max_width = l;
    else if (prop >= MT && prop <= ML)
      s->margin[prop - MT] = l;
    else if (prop >= PT && prop <= PL) {
      if (l.value < 0)
        return 0;
      s->padding[prop - PT] = l;
    } else if (prop == INDENT || prop == BORDER_WIDTH) {
      if (l.percent || l.value < 0 || l.value > 1024)
        return 0;
      if (prop == INDENT)
        s->indent = l.value;
      else
        s->border_width = l.value;
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
                              exr_style **out, exr_error *e) {
  css c = {0};
  exr_style *styles = NULL, initial = {0};
  const exr_layout_options *o = &config->page;
  size_t i, r;
  initial.font_size = o->font_size;
  initial.leading = o->line_height;
  initial.leading_relative = 1;
  initial.color = initial.border_color = 255;
  initial.border_width = 3;
  initial.width.value = initial.height.value = initial.max_width.value = -1;
  initial.display = EXR_CSS_BLOCK;
  *out = NULL;
  if (config->document_css)
    for (i = 0; i < d->node_count; i++) {
      const exr_node *n = &d->nodes[i];
      if (!strcmp(tag(n), "style")) {
        size_t child;
        for (child = n->first_child; child != SIZE_MAX; child = d->nodes[child].next_sibling)
          if (d->nodes[child].text &&
              !stylesheet(&c, d->nodes[child].text, strlen(d->nodes[child].text), n->chapter, 0))
            goto done;
      } else if (!strcmp(tag(n), "link") &&
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
          stylesheet(&c, decoded.data ? decoded.data : "", decoded.size, n->chapter, 0);
        free(decoded.data);
        if (c.failed)
          goto done;
      }
    }
  if (config->user_css && !stylesheet(&c, config->user_css, strlen(config->user_css), SIZE_MAX, 1))
    goto done;
  styles = calloc(d->node_count, sizeof(*styles));
  if (!styles) {
    c.failed = EXR_MEMORY;
    goto done;
  }
  for (i = 0; i < d->node_count; i++) {
    const exr_node *n = &d->nodes[i];
    const exr_style *parent = n->parent == SIZE_MAX ? &initial : &styles[n->parent];
    exr_style *s = &styles[i];
    winner w[PROPERTIES] = {{0}};
    declaration *inline_declarations = NULL;
    size_t inline_count = 0;
    const char *name = tag(n), *attr;
    int p;
    *s = initial;
    s->font_size = parent->font_size;
    s->flags = parent->flags;
    s->color = parent->color;
    s->leading = parent->leading;
    s->leading_relative = parent->leading_relative;
    s->align = parent->align;
    s->indent = parent->indent;
    s->display = EXR_CSS_INLINE;
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
    if (n->kind == EXR_NODE_LIST)
      s->padding[3].value = s->font_size;
    if (n->kind == EXR_NODE_TABLE)
      s->display = EXR_CSS_TABLE;
    if (n->kind == EXR_NODE_ROW)
      s->display = EXR_CSS_ROW;
    if (n->kind == EXR_NODE_CELL) {
      s->display = EXR_CSS_CELL;
    }
    if (n->kind == EXR_NODE_IMAGE) {
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
    free(styles);
    return exr_fail(e, c.failed, "Stylesheet decoding or complexity limit failed");
  }
  *out = styles;
  return EXR_OK;
}
