/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <expat.h>

static const char *local_name(const char *name) {
  const char *p = strrchr(name, '|');
  return p ? p + 1 : name;
}
const char *exr_html_tag(const exr_document *d, const exr_node *node) {
  const char prefix[] = "http://www.w3.org/1999/xhtml|";
  if (!node->name)
    return "";
  if (d->format != EXR_CUSTOM)
    return local_name(node->name);
  return !strncmp(node->name, prefix, sizeof(prefix) - 1) ? node->name + sizeof(prefix) - 1 : "";
}
static int whitespace(unsigned char c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r'; }
static int token(const char *s, const char *word) {
  size_t n = strlen(word);
  while (s && *s) {
    const char *start;
    while (whitespace((unsigned char)*s))
      s++;
    start = s;
    while (*s && !whitespace((unsigned char)*s))
      s++;
    if ((size_t)(s - start) == n && !memcmp(start, word, n))
      return 1;
  }
  return 0;
}
char *exr_model_copy(exr_document *d, const char *s, size_t n) {
  char *copy;
  if (n >= EXR_MAX_TEXT - d->model_bytes)
    return NULL;
  copy = exr_copy(s, n);
  if (copy)
    d->model_bytes += n + 1;
  return copy;
}
size_t exr_model_node(exr_document *d, size_t parent, size_t chapter, exr_node_kind kind,
                      const char *name, const char *text, size_t length) {
  size_t index = d->node_count;
  exr_node *node;
  if (index >= EXR_MAX_NODES ||
      !exr_grow((void **)&d->nodes, &d->node_capacity, index + 1, sizeof(*d->nodes)) ||
      !exr_grow((void **)&d->last_children, &d->last_capacity, index + 1, sizeof(size_t)))
    return SIZE_MAX;
  node = &d->nodes[d->node_count++];
  memset(node, 0, sizeof(*node));
  node->kind = kind;
  node->parent = parent;
  node->chapter = chapter;
  node->first_child = node->next_sibling = node->start = node->end = SIZE_MAX;
  d->last_children[index] = SIZE_MAX;
  if (name && !(node->name = exr_model_copy(d, name, strlen(name))))
    return SIZE_MAX;
  if (text && !(node->text = exr_model_copy(d, text, length)))
    return SIZE_MAX;
  if (parent != SIZE_MAX) {
    size_t previous = d->last_children[parent];
    if (previous == SIZE_MAX)
      d->nodes[parent].first_child = index;
    else
      d->nodes[previous].next_sibling = index;
    d->last_children[parent] = index;
  }
  return index;
}
const exr_node *exr_document_nodes(const exr_document *d, size_t *n) {
  if (n)
    *n = d ? d->node_count : 0;
  return d ? d->nodes : NULL;
}
const exr_chapter *exr_document_chapters(const exr_document *d, size_t *n) {
  if (n)
    *n = d ? d->chapter_count : 0;
  return d ? d->chapters : NULL;
}
const exr_resource *exr_document_resources(const exr_document *d, size_t *n) {
  if (n)
    *n = d ? d->resource_count : 0;
  return d ? d->resources : NULL;
}
const char *exr_node_attribute(const exr_node *node, const char *name) {
  size_t i;
  if (!node || !name)
    return NULL;
  for (i = 0; i < node->attribute_count; i++)
    if (!strcmp(node->attributes[i].name, name))
      return node->attributes[i].value;
  return NULL;
}
void exr_model_free(exr_document *d) {
  size_t i, j;
  for (i = 0; i < d->node_count; i++) {
    exr_node *node = &d->nodes[i];
    free((void *)node->name);
    free((void *)node->text);
    for (j = 0; j < node->attribute_count; j++) {
      free((void *)node->attributes[j].name);
      free((void *)node->attributes[j].value);
    }
    free((void *)node->attributes);
  }
  for (i = 0; i < d->resource_count; i++) {
    free((void *)d->resources[i].id);
    free((void *)d->resources[i].path);
    free((void *)d->resources[i].media_type);
    free((void *)d->resources[i].properties);
    if (d->resource_data)
      free(d->resource_data[i].bytes);
  }
  if (d->owns_chapter_strings)
    for (i = 0; i < d->chapter_count; i++) {
      free((void *)d->chapters[i].id);
      free((void *)d->chapters[i].path);
    }
  free(d->nodes);
  free(d->last_children);
  free(d->chapters);
  free(d->resources);
  free(d->resource_data);
  if (d->shared_archive) {
    if (!--d->shared_archive->refs) {
      if (d->shared_archive->source.release)
        d->shared_archive->source.release(d->shared_archive->source.context);
      free(d->shared_archive->bytes);
      free(d->shared_archive);
    }
  } else {
    free(d->archive);
  }
}
static exr_node_kind element_kind(const char *name) {
  const char *s = local_name(name);
  if (!strcmp(s, "section") || !strcmp(s, "article"))
    return EXR_NODE_SECTION;
  if (!strcmp(s, "p"))
    return EXR_NODE_PARAGRAPH;
  if (s[0] == 'h' && s[1] >= '1' && s[1] <= '6' && !s[2])
    return EXR_NODE_HEADING;
  if (!strcmp(s, "ul") || !strcmp(s, "ol") || !strcmp(s, "dl"))
    return EXR_NODE_LIST;
  if (!strcmp(s, "li") || !strcmp(s, "dt") || !strcmp(s, "dd"))
    return EXR_NODE_LIST_ITEM;
  if (!strcmp(s, "a"))
    return EXR_NODE_LINK;
  if (!strcmp(s, "img") || !strcmp(s, "image"))
    return EXR_NODE_IMAGE;
  if (!strcmp(s, "table"))
    return EXR_NODE_TABLE;
  if (!strcmp(s, "tr"))
    return EXR_NODE_ROW;
  if (!strcmp(s, "td") || !strcmp(s, "th"))
    return EXR_NODE_CELL;
  if (!strcmp(s, "br"))
    return EXR_NODE_BREAK;
  return EXR_NODE_ELEMENT;
}
typedef struct {
  exr_document *doc;
  XML_Parser parser;
  size_t chapter, stack[257], depth;
  exr_buffer text;
  exr_status failed;
  const char *root_name;
} tree_parser;
static void stop(tree_parser *p, exr_status code) {
  p->failed = code;
  XML_StopParser(p->parser, XML_FALSE);
}
static int tree_text_flush(tree_parser *p) {
  if (p->text.size && exr_model_node(p->doc, p->stack[p->depth], p->chapter, EXR_NODE_TEXT, NULL,
                                     p->text.data, p->text.size) == SIZE_MAX) {
    stop(p, EXR_LIMIT);
    return 0;
  }
  p->text.size = 0;
  return 1;
}
static void XMLCALL tree_start(void *user, const char *name, const char **attrs) {
  tree_parser *p = user;
  exr_node *node;
  exr_attribute *a;
  size_t index, count = 0, i;
  if (!tree_text_flush(p))
    return;
  if (p->depth == 256) {
    stop(p, EXR_LIMIT);
    return;
  }
  if (!p->depth && strcmp(local_name(name), p->root_name)) {
    stop(p, EXR_FORMAT);
    return;
  }
  index = exr_model_node(p->doc, p->stack[p->depth], p->chapter, element_kind(name), name, NULL, 0);
  if (index == SIZE_MAX) {
    stop(p, EXR_LIMIT);
    return;
  }
  p->stack[++p->depth] = index;
  while (attrs[count * 2])
    count++;
  if (count > 256) {
    stop(p, EXR_LIMIT);
    return;
  }
  if (!count)
    return;
  a = calloc(count, sizeof(*a));
  if (!a) {
    stop(p, EXR_MEMORY);
    return;
  }
  node = &p->doc->nodes[index];
  node->attributes = a;
  node->attribute_count = count;
  for (i = 0; i < count; i++) {
    a[i].name = exr_model_copy(p->doc, attrs[i * 2], strlen(attrs[i * 2]));
    a[i].value = exr_model_copy(p->doc, attrs[i * 2 + 1], strlen(attrs[i * 2 + 1]));
    if (!a[i].name || !a[i].value) {
      stop(p, EXR_LIMIT);
      return;
    }
  }
  if (token(exr_node_attribute(node, "http://www.idpf.org/2007/ops|type"), "footnote") ||
      token(exr_node_attribute(node, "http://www.idpf.org/2007/ops|type"), "endnote") ||
      token(exr_node_attribute(node, "role"), "doc-footnote") ||
      token(exr_node_attribute(node, "role"), "doc-endnote"))
    node->kind = EXR_NODE_NOTE;
}
static void XMLCALL tree_end(void *user, const char *name) {
  tree_parser *p = user;
  (void)name;
  if (tree_text_flush(p) && p->depth)
    p->depth--;
}
static void XMLCALL tree_text(void *user, const XML_Char *s, int n) {
  tree_parser *p = user;
  if (!exr_append(&p->text, s, (size_t)n))
    stop(p, EXR_LIMIT);
}
static void XMLCALL tree_entity(void *user, const XML_Char *name, int parameter,
                                const XML_Char *value, int length, const XML_Char *base,
                                const XML_Char *system, const XML_Char *public_id,
                                const XML_Char *notation) {
  tree_parser *p = user;
  (void)name;
  (void)parameter;
  (void)value;
  (void)length;
  (void)base;
  (void)system;
  (void)public_id;
  (void)notation;
  stop(p, EXR_FORMAT);
}
exr_status exr_xml_tree(exr_document *d, const void *data, size_t n, size_t resource, int in_spine,
                         int linear, const char *root_name, exr_error *e) {
  tree_parser p = {0};
  exr_chapter *chapter;
  enum XML_Status parsed;
  exr_status result = EXR_OK;
  size_t root;
  if (!d->node_count &&
      exr_model_node(d, SIZE_MAX, SIZE_MAX, EXR_NODE_DOCUMENT, NULL, NULL, 0) == SIZE_MAX)
    return EXR_MEMORY;
  if (d->chapter_count >= 10000 || !exr_grow((void **)&d->chapters, &d->chapter_capacity,
                                             d->chapter_count + 1, sizeof(*d->chapters)))
    return exr_fail(e, EXR_LIMIT, "Chapter limit exceeded");
  p.doc = d;
  p.root_name = root_name;
  p.chapter = d->chapter_count;
  root = exr_model_node(d, 0, p.chapter, EXR_NODE_CHAPTER, NULL, NULL, 0);
  if (root == SIZE_MAX)
    return EXR_LIMIT;
  chapter = &d->chapters[d->chapter_count++];
  chapter->root = root;
  chapter->resource = resource;
  chapter->id = d->resources[resource].id;
  chapter->path = d->resources[resource].path;
  chapter->in_spine = in_spine;
  chapter->linear = linear;
  p.stack[0] = root;
  p.parser = XML_ParserCreateNS(NULL, '|');
  if (!p.parser)
    return exr_fail(e, EXR_MEMORY, "XML allocation failed");
  XML_SetUserData(p.parser, &p);
  XML_SetElementHandler(p.parser, tree_start, tree_end);
  XML_SetCharacterDataHandler(p.parser, tree_text);
  XML_SetEntityDeclHandler(p.parser, tree_entity);
  XML_SetParamEntityParsing(p.parser, XML_PARAM_ENTITY_PARSING_NEVER);
  parsed = XML_Parse(p.parser, data, (int)n, XML_TRUE);
  if (parsed != XML_STATUS_OK || p.failed)
    result = exr_fail(e, p.failed ? p.failed : EXR_FORMAT, "XML tree rejected: %s",
                      XML_ErrorString(XML_GetErrorCode(p.parser)));
  XML_ParserFree(p.parser);
  free(p.text.data);
  return result;
}
exr_status exr_xhtml(exr_document *d, const void *data, size_t n, size_t resource, int in_spine,
                     int linear, exr_error *e) {
  return exr_xml_tree(d, data, n, resource, in_spine, linear, "html", e);
}

/* This text projection keeps the existing layout/search API working. Raw tree text and
   all attributes remain available for the stylesheet-driven layout implementation. */
typedef struct {
  exr_document *doc;
  exr_buffer text;
  size_t block;
  int pending_space;
} projection;
static void end_block(projection *p) {
  p->block = SIZE_MAX;
  p->pending_space = 0;
}
static int project_text(projection *p, exr_node *node, unsigned heading) {
  const char *s = node->text;
  size_t i;
  node->start = SIZE_MAX;
  for (i = 0; s && s[i]; i++) {
    if (whitespace((unsigned char)s[i])) {
      if (p->block != SIZE_MAX)
        p->pending_space = 1;
      continue;
    }
    if (p->block == SIZE_MAX) {
      exr_block *b;
      if (p->text.size && !exr_append(&p->text, "\n", 1))
        return 0;
      if (p->doc->count >= EXR_MAX_ITEMS || !exr_grow((void **)&p->doc->blocks, &p->doc->capacity,
                                                      p->doc->count + 1, sizeof(exr_block)))
        return 0;
      p->block = p->doc->count++;
      b = &p->doc->blocks[p->block];
      b->start = b->end = p->text.size;
      b->heading = heading;
    }
    if (node->start == SIZE_MAX)
      node->start = p->text.size;
    if (p->pending_space && !exr_append(&p->text, " ", 1))
      return 0;
    p->pending_space = 0;
    if (!exr_append(&p->text, s + i, 1))
      return 0;
    p->doc->blocks[p->block].end = p->text.size;
  }
  if (node->start == SIZE_MAX)
    node->start = p->text.size;
  node->end = p->text.size;
  return 1;
}
static int project_node(projection *p, size_t index, unsigned heading) {
  exr_node *node = &p->doc->nodes[index];
  const char *tag = exr_html_tag(p->doc, node);
  size_t child, start = SIZE_MAX, end = 0;
  int boundary;
  if (node->kind == EXR_NODE_TEXT)
    return project_text(p, node, heading);
  if (!strcmp(tag, "head") || !strcmp(tag, "script") || !strcmp(tag, "style") ||
      !strcmp(tag, "object") || !strcmp(tag, "template") || exr_node_attribute(node, "hidden"))
    return 1;
  boundary = node->kind == EXR_NODE_CHAPTER || node->kind == EXR_NODE_SECTION ||
             node->kind == EXR_NODE_PARAGRAPH || node->kind == EXR_NODE_HEADING ||
             node->kind == EXR_NODE_LIST || node->kind == EXR_NODE_LIST_ITEM ||
             node->kind == EXR_NODE_TABLE || node->kind == EXR_NODE_ROW ||
             node->kind == EXR_NODE_CELL || node->kind == EXR_NODE_BREAK ||
             node->kind == EXR_NODE_NOTE || !strcmp(tag, "div") || !strcmp(tag, "blockquote") ||
             !strcmp(tag, "pre");
  if (boundary)
    end_block(p);
  if (node->kind == EXR_NODE_HEADING)
    heading =
        tag[0] == 'h' && tag[1] >= '1' && tag[1] <= '6' && !tag[2] ? (unsigned)(tag[1] - '0') : 1;
  for (child = node->first_child; child != SIZE_MAX; child = p->doc->nodes[child].next_sibling) {
    exr_node *v = &p->doc->nodes[child];
    if (!project_node(p, child, heading))
      return 0;
    if (v->start != SIZE_MAX && v->end > v->start) {
      if (start == SIZE_MAX)
        start = v->start;
      end = v->end;
    }
  }
  node->start = start == SIZE_MAX ? p->text.size : start;
  node->end = start == SIZE_MAX ? p->text.size : end;
  if (boundary)
    end_block(p);
  return 1;
}
exr_status exr_model_finish(exr_document *d, exr_error *e) {
  size_t i;
  if (d->node_count) {
    projection p = {0};
    p.doc = d;
    p.block = SIZE_MAX;
    for (i = 0; i < d->chapter_count; i++) {
      exr_chapter *chapter = &d->chapters[i];
      if (chapter->in_spine && chapter->linear && !project_node(&p, chapter->root, 0)) {
        free(p.text.data);
        return exr_fail(e, EXR_LIMIT, "Projected text exceeds limit");
      }
    }
    if (!p.text.data && !exr_append(&p.text, "", 0))
      return EXR_MEMORY;
    d->text = p.text.data;
    d->size = p.text.size;
    d->text_capacity = p.text.capacity;
    d->nodes[0].start = 0;
    d->nodes[0].end = d->size;
  } else if (d->count) {
    /* Other decoders retain their current paragraph fidelity through the same tree API. */
    size_t root;
    if (exr_model_node(d, SIZE_MAX, SIZE_MAX, EXR_NODE_DOCUMENT, NULL, NULL, 0) == SIZE_MAX)
      return EXR_MEMORY;
    root = exr_model_node(d, 0, 0, EXR_NODE_CHAPTER, NULL, NULL, 0);
    if (root == SIZE_MAX)
      return EXR_LIMIT;
    d->chapters = calloc(1, sizeof(*d->chapters));
    if (!d->chapters)
      return EXR_MEMORY;
    d->chapter_count = d->chapter_capacity = 1;
    d->chapters[0].id = d->chapters[0].path = "";
    d->chapters[0].root = root;
    d->chapters[0].resource = SIZE_MAX;
    d->chapters[0].in_spine = d->chapters[0].linear = 1;
    d->nodes[0].start = d->nodes[root].start = 0;
    d->nodes[0].end = d->nodes[root].end = d->size;
    for (i = 0; i < d->count; i++) {
      exr_block *b = &d->blocks[i];
      size_t block, text;
      char name[3] = "p";
      if (b->heading) {
        name[0] = 'h';
        name[1] = (char)('0' + b->heading);
        name[2] = 0;
      }
      block = exr_model_node(d, root, 0, b->heading ? EXR_NODE_HEADING : EXR_NODE_PARAGRAPH, name,
                             NULL, 0);
      if (block == SIZE_MAX)
        return EXR_LIMIT;
      text =
          exr_model_node(d, block, 0, EXR_NODE_TEXT, NULL, d->text + b->start, b->end - b->start);
      if (text == SIZE_MAX)
        return EXR_LIMIT;
      d->nodes[block].start = d->nodes[text].start = b->start;
      d->nodes[block].end = d->nodes[text].end = b->end;
    }
  }
  free(d->last_children);
  d->last_children = NULL;
  d->last_capacity = 0;
  return EXR_OK;
}

/* Shared semantic construction helpers used by format adapters. */
size_t exr_model_html(exr_document *d, size_t parent, size_t chapter, exr_node_kind kind,
                       const char *tag, const char *text) {
  exr_buffer expanded = {0}; size_t index;
  if (tag) {
    const char prefix[] = "http://www.w3.org/1999/xhtml|";
    if (!exr_append(&expanded, prefix, sizeof(prefix)-1) || !exr_append(&expanded, tag, strlen(tag))) {
      free(expanded.data); return SIZE_MAX;
    }
    tag = expanded.data;
  }
  index = exr_model_node(d, parent, chapter, kind, tag, text, text ? strlen(text) : 0);
  free(expanded.data); return index;
}
int exr_model_attribute(exr_document *d, size_t index, const char *key, const char *value) {
  exr_node *v = &d->nodes[index]; exr_attribute *a = (exr_attribute *)v->attributes; size_t i;
  for (i=0; i<v->attribute_count; i++) if (!strcmp(a[i].name,key)) break;
  if (i==v->attribute_count) {
    exr_attribute *grown;
    if (i>=256) return 0;
    grown = realloc(a,(i+1)*sizeof(*a)); if (!grown) return 0;
    a=grown; v->attributes=a; a[i].name=a[i].value=NULL; v->attribute_count++;
    a[i].name=exr_model_copy(d,key,strlen(key)); if (!a[i].name) return 0;
  }
  {
    char *copy=exr_model_copy(d,value,strlen(value)); if(!copy) return 0;
    free((void *)a[i].value); a[i].value=copy; return 1;
  }
}
exr_status exr_xml_memory_tree(const void *data, size_t size, const char *root,
                                exr_document **out, exr_error *e) {
  exr_document *d = calloc(1,sizeof(*d)); exr_resource *r; exr_status status;
  *out=NULL;
  if (!d) return exr_fail(e,EXR_MEMORY,"XML tree allocation failed");
  d->resources=calloc(1,sizeof(*d->resources));
  if (!d->resources) { exr_document_free(d); return EXR_MEMORY; }
  d->resource_count=d->resource_capacity=1; r=d->resources;
  r->id=exr_copy("source",6); r->path=exr_copy("source.xml",10);
  r->media_type=exr_copy("application/xml",15); r->properties=exr_copy("",0);
  if (!r->id || !r->path || !r->media_type || !r->properties) { exr_document_free(d); return EXR_MEMORY; }
  status=exr_xml_tree(d,data,size,0,1,1,root,e);
  if(status!=EXR_OK) { exr_document_free(d); return status; }
  *out=d; return EXR_OK;
}
