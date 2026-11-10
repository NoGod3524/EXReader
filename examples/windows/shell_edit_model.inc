/* SPDX-License-Identifier: MIT */
/* UI-thread adapter for #119. No second undo engine: caret records follow the
   SDK's transactions; all document bytes and undo versions belong to the SDK. */
#include <exr/edit.h>

enum { EDIT_HISTORY = 100, EDIT_LIMIT = 16*1024*1024 };
typedef struct { exr_edit_id id; size_t start,end; } edit_span;
typedef struct { size_t anchor,focus; } edit_selection;
typedef struct { edit_selection before,after; } edit_step;
typedef struct {
  exr_edit_doc *doc;
  exr_edit_tx *tx;
  char *text,*saved;
  unsigned char *boundaries;
  size_t size,count;
  edit_span *spans;
  edit_selection selection,tx_before;
  edit_step history[EDIT_HISTORY];
  size_t history_count,cursor;
} edit_model;

static exr_status edit_refresh(edit_model *m) {
  size_t count=exr_edit_block_count(m->doc), size=0, at=0;
  if (count>EDIT_LIMIT/sizeof(edit_span)) return EXR_LIMIT;
  edit_span *spans=calloc(count ? count:1,sizeof(*spans));
  if (!spans) return EXR_MEMORY;
  for (size_t i=0;i<count;i++) {
    const exr_edit_block *b=exr_edit_block_at(m->doc,i);
    size_t n=b->kind==EXR_EDIT_PARAGRAPH ? 0:3;
    for (size_t j=0;j<b->run_count;j++) {
      size_t bytes=b->runs[j].kind==EXR_EDIT_TEXT ? b->runs[j].text_size:3;
      if (bytes>EDIT_LIMIT-n) { free(spans); return EXR_LIMIT; }
      n+=bytes;
    }
    if (n+(i!=0)>EDIT_LIMIT-size) { free(spans); return EXR_LIMIT; }
    size+=n+(i!=0);
  }
  char *text=malloc(size+1); unsigned char *boundaries=NULL;
  if (!text) { free(spans); return EXR_MEMORY; }
  for (size_t i=0;i<count;i++) {
    const exr_edit_block *b=exr_edit_block_at(m->doc,i);
    if (i) text[at++]='\n';
    spans[i].id=b->id; spans[i].start=at;
    if (b->kind!=EXR_EDIT_PARAGRAPH) { memcpy(text+at,"\xef\xbf\xbc",3); at+=3; }
    for (size_t j=0;j<b->run_count;j++) {
      const exr_edit_run *r=b->runs+j;
      size_t bytes=r->kind==EXR_EDIT_TEXT ? r->text_size:3;
      memcpy(text+at,r->kind==EXR_EDIT_TEXT ? r->text:"\xef\xbf\xbc",bytes); at+=bytes;
    }
    spans[i].end=at;
  }
  text[at]=0;
  exr_status status=exr_text_analyze(text,at,&boundaries,NULL);
  if (status!=EXR_OK) { free(text); free(spans); return status; }
  free(m->text); free(m->spans); exr_free(m->boundaries);
  m->text=text; m->spans=spans; m->boundaries=boundaries; m->size=at; m->count=count;
  m->selection.anchor=min(m->selection.anchor,at); m->selection.focus=min(m->selection.focus,at);
  return EXR_OK;
}
static int edit_dirty(const edit_model *m) { return !m->saved || strcmp(m->saved,m->text); }
static int edit_mark_saved(edit_model *m) {
  char *saved=malloc(m->size+1);
  if (!saved) return 0;
  memcpy(saved,m->text,m->size+1); free(m->saved); m->saved=saved; return 1;
}
static size_t edit_span_at(const edit_model *m,size_t offset) {
  for (size_t i=0;i<m->count;i++) if (offset<=m->spans[i].end) return i;
  return m->count ? m->count-1:0;
}
static size_t edit_boundary(const edit_model *m,size_t offset,int forward) {
  if (forward) { if (offset<m->size) offset++; }
  else if (offset) offset--;
  while (offset && offset<m->size && !(m->boundaries[offset]&EXR_BOUNDARY_GRAPHEME))
    offset=forward ? offset+1:offset-1;
  return offset;
}
static exr_status edit_finish(edit_model *m) {
  if (!m->tx) return EXR_OK;
  exr_edit_tx *tx=m->tx; m->tx=NULL;
  exr_status status=exr_edit_commit(tx);
  if (status!=EXR_OK) { m->selection=m->tx_before; edit_refresh(m); return status; }
  if (m->cursor==EDIT_HISTORY) {
    memmove(m->history,m->history+1,(EDIT_HISTORY-1)*sizeof(*m->history)); m->cursor--;
  }
  m->history[m->cursor++]=(edit_step){m->tx_before,m->selection};
  m->history_count=m->cursor;
  return EXR_OK;
}
static exr_status edit_begin(edit_model *m) {
  if (m->tx) return EXR_OK;
  m->tx=exr_edit_begin(m->doc); m->tx_before=m->selection;
  return m->tx ? EXR_OK:EXR_MEMORY;
}
static exr_status edit_abort(edit_model *m,exr_status status) {
  if (m->tx) { exr_edit_rollback(m->tx); m->tx=NULL; m->selection=m->tx_before; edit_refresh(m); }
  return status;
}
static exr_status edit_history_move(edit_model *m,int redo) {
  exr_status status=edit_finish(m);
  if (status!=EXR_OK) return status;
  if ((!redo && !m->cursor) || (redo && m->cursor==m->history_count)) return EXR_ARGUMENT;
  status=redo ? exr_edit_redo(m->doc):exr_edit_undo(m->doc);
  if (status!=EXR_OK) return status;
  if (redo) { m->selection=m->history[m->cursor].after; m->cursor++; }
  else { m->cursor--; m->selection=m->history[m->cursor].before; }
  return edit_refresh(m);
}
static void edit_model_free(edit_model *m) {
  exr_edit_doc_free(m->doc); free(m->text); free(m->saved); free(m->spans); exr_free(m->boundaries);
  memset(m,0,sizeof(*m));
}
static exr_status edit_seed(edit_model *m,const char *text,size_t size) {
  if (size>EDIT_LIMIT) return EXR_LIMIT;
  size_t count=1, at=0;
  for (size_t i=0;i<size;i++) if (text[i]=='\n') count++;
  exr_edit_block *blocks=calloc(count,sizeof(*blocks));
  exr_edit_run *runs=calloc(count,sizeof(*runs));
  if (!blocks || !runs) { free(blocks); free(runs); return EXR_MEMORY; }
  for (size_t i=0;i<count;i++) {
    size_t end=at; while (end<size && text[end]!='\n') end++;
    blocks[i].kind=EXR_EDIT_PARAGRAPH; blocks[i].runs=runs+i; blocks[i].run_count=1;
    runs[i].kind=EXR_EDIT_TEXT; runs[i].text=text+at; runs[i].text_size=end-at; at=end+1;
  }
  exr_edit_options options={EDIT_HISTORY};
  exr_status status=exr_edit_doc_create(NULL,0,blocks,count,NULL,0,&options,&m->doc);
  free(blocks); free(runs);
  if (status==EXR_OK) status=edit_refresh(m);
  if (status==EXR_OK && !edit_mark_saved(m)) status=EXR_MEMORY;
  return status;
}
/* Copy run slices before mutating their owner. The SDK deep-copies these views
   on insert, preserving run formatting and uninterpreted inline XML. */
static size_t edit_slice(const exr_edit_block *b,size_t from,size_t to,exr_edit_run *out) {
  size_t at=0,count=0;
  for (size_t i=0;i<b->run_count;i++) {
    exr_edit_run r=b->runs[i]; size_t n=r.kind==EXR_EDIT_TEXT ? r.text_size:3;
    size_t a=max(at,from),z=min(at+n,to);
    if (a<z) {
      if (r.kind==EXR_EDIT_TEXT) { r.text+=a-at; r.text_size=z-a; }
      r.id=0; out[count++]=r;
    }
    at+=n;
  }
  return count;
}
static int edit_replace_allowed(edit_model *m,size_t a,size_t b) {
  if (!m->count || a>b || b>m->size || !(m->boundaries[a]&EXR_BOUNDARY_GRAPHEME) ||
      !(m->boundaries[b]&EXR_BOUNDARY_GRAPHEME)) return 0;
  size_t first=edit_span_at(m,a),last=edit_span_at(m,b);
  for (size_t i=first;i<=last;i++) {
    const exr_edit_block *block=exr_edit_block_at(m->doc,i);
    if (block->kind!=EXR_EDIT_PARAGRAPH) return 0;
    size_t at=m->spans[i].start;
    for (size_t j=0;j<block->run_count;j++) {
      const exr_edit_run *r=block->runs+j;
      size_t end=at+(r->kind==EXR_EDIT_TEXT ? r->text_size:3);
      if (r->kind!=EXR_EDIT_TEXT && ((a<end && b>at) || (a==b && a>at && a<end))) return 0;
      at=end;
    }
  }
  return 1;
}
static exr_status edit_replace(edit_model *m,size_t a,size_t b,const char *text,size_t size,int typing) {
  if (!size && a==b) return EXR_OK;
  if (!edit_replace_allowed(m,a,b)) return EXR_UNSUPPORTED;
  if (size>EDIT_LIMIT || m->size-(b-a)>EDIT_LIMIT-size) return EXR_LIMIT;
  unsigned char *valid=NULL;
  exr_status status=exr_text_analyze(text,size,&valid,NULL); exr_free(valid);
  if (status!=EXR_OK) return status;
  /* Embedded NUL/CR would make the exact flat representation ambiguous. */
  if (memchr(text,0,size) || memchr(text,'\r',size)) return EXR_ARGUMENT;
  if (!typing && (status=edit_finish(m))!=EXR_OK) return status;
  if ((status=edit_begin(m))!=EXR_OK) return status;
  size_t first=edit_span_at(m,a),last=edit_span_at(m,b);
  const exr_edit_block *left=exr_edit_block_at(m->doc,first),*right=exr_edit_block_at(m->doc,last);
  exr_edit_para_props props=left->props;
  size_t capacity=left->run_count+right->run_count+1;
  exr_edit_run *runs=calloc(capacity ? capacity:1,sizeof(*runs));
  if (!runs) return edit_abort(m,EXR_MEMORY);
  size_t prefix=edit_slice(left,0,a-m->spans[first].start,runs);
  exr_edit_run_props inherit={0};
  if (prefix && runs[prefix-1].kind==EXR_EDIT_TEXT) inherit=runs[prefix-1].props;
  else if (left->run_count && left->runs[0].kind==EXR_EDIT_TEXT) inherit=left->runs[0].props;
  exr_edit_id after=first ? m->spans[first-1].id:0;
  size_t at=0;
  do {
    size_t end=at,n=at ? 0:prefix;
    while (end<size && text[end]!='\n') end++;
    if (end>at) { runs[n]=(exr_edit_run){0}; runs[n].text=text+at; runs[n].text_size=end-at;
      runs[n].props=inherit; n++; }
    if (end==size) n+=edit_slice(right,b-m->spans[last].start,m->spans[last].end-m->spans[last].start,runs+n);
    exr_edit_id id=0;
    status=exr_edit_insert_paragraph(m->doc,after,runs,n,&props,&id);
    if (status!=EXR_OK) break;
    after=id;
    if (end==size) break;
    at=end+1;
  } while (at<=size);
  free(runs);
  for (size_t i=first;status==EXR_OK && i<=last;i++) status=exr_edit_delete_block(m->doc,m->spans[i].id);
  if (status!=EXR_OK) return edit_abort(m,status);
  m->selection.anchor=m->selection.focus=a+size;
  status=edit_refresh(m);
  if (status!=EXR_OK) return edit_abort(m,status);
  return typing ? EXR_OK:edit_finish(m);
}
static exr_status edit_enter(edit_model *m) {
  size_t a=min(m->selection.anchor,m->selection.focus),b=max(m->selection.anchor,m->selection.focus);
  exr_status status=edit_finish(m);
  if (status!=EXR_OK || !edit_replace_allowed(m,a,b)) return status!=EXR_OK ? status:EXR_UNSUPPORTED;
  if ((status=edit_begin(m))!=EXR_OK) return status;
  if (a!=b && (status=edit_replace(m,a,b,"",0,1))!=EXR_OK) return status;
  size_t index=edit_span_at(m,a),offset=a-m->spans[index].start,run=0;
  const exr_edit_block *block=exr_edit_block_at(m->doc,index);
  for (;run<block->run_count;run++) {
    size_t n=block->runs[run].kind==EXR_EDIT_TEXT ? block->runs[run].text_size:3;
    if (offset<n) break;
    offset-=n;
  }
  status=exr_edit_split_paragraph(m->doc,block->id,run,offset);
  if (status!=EXR_OK) return edit_abort(m,status);
  m->selection.anchor=m->selection.focus=a+1;
  status=edit_refresh(m);
  return status==EXR_OK ? edit_finish(m):edit_abort(m,status);
}
