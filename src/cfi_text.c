/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
typedef struct {
  const exr_document *doc; const exr_control *control; exr_error *error; exr_status status;
  exr_buffer text; size_t bytes,visited,position,desired; unsigned whitespace,mapping,found;
  exr_cfi_point target,result;
} text_walk;
static int boundary(text_walk *w,size_t node,size_t offset) {
  if(w->target.node==node && w->target.offset==offset) w->position=w->bytes;
  if(w->mapping && w->desired==w->bytes) { w->result=(exr_cfi_point){node,offset,w->target.side}; w->found=1; }
  return 1;
}
static int walk(text_walk *w,size_t node,unsigned depth) {
  const exr_node *v=&w->doc->nodes[node]; size_t child,number=0;
  if(depth>256) { w->status=exr_fail(w->error,EXR_LIMIT,"CFI assertion XML depth exceeds 256"); return 0; }
  if(!(w->visited++%256)) { w->status=exr_control_poll(w->control,EXR_STAGE_READ,w->visited,0,w->error); if(w->status!=EXR_OK) return 0; }
  if(v->kind==EXR_NODE_TEXT) {
    const char *s=v->text ? v->text : ""; size_t n=strlen(s),at=0,offset=0,next_check=4096;
    while(at<n) {
      size_t start=at,bytes; uint32_t cp; unsigned whitespace;
      boundary(w,node,offset); if(w->found) return 1;
      if(at>=next_check) { w->status=exr_control_cancel(w->control,w->error); if(w->status!=EXR_OK) return 0; next_check=at+4096; }
      if(!exr_next(s,n,&at,&cp)) { w->status=exr_fail(w->error,EXR_ENCODING,"Invalid raw CFI text"); return 0; }
      whitespace=cp==32 || cp==9 || cp==10 || cp==13;
      bytes=whitespace ? !w->whitespace : at-start;
      if(bytes) {
        if(bytes>EXR_MAX_TEXT-1-w->bytes || (!w->mapping && !exr_append(&w->text,whitespace ? " " : s+start,bytes))) { w->status=exr_fail(w->error,EXR_LIMIT,"CFI assertion text exceeds byte budget"); return 0; }
        w->bytes+=bytes;
      }
      w->whitespace=whitespace; offset+=cp>0xffff ? 2 : 1;
    }
    return boundary(w,node,offset);
  }
  for(child=v->first_child;child!=SIZE_MAX;child=w->doc->nodes[child].next_sibling,number++) {
    if(w->target.node==node && w->target.offset==number) w->position=w->bytes;
    if(!walk(w,child,depth+1)) return 0;
    if(w->found) return 1;
  }
  if(w->target.node==node && w->target.offset==number) w->position=w->bytes;
  return 1;
}
exr_status exr_cfi_assertion_resolve(const exr_document *d,size_t chapter,const char *before,const char *after,
                                       const exr_control *control,exr_cfi_point *point,exr_error *e) {
  text_walk w={0}; exr_buffer query={0}; size_t root,n_before=before ? strlen(before) : 0,n_after=after ? strlen(after) : 0,start,end,second,last; exr_status status;
  w.doc=d; w.control=control; w.error=e; w.target=*point; w.position=SIZE_MAX;
  root=d->nodes[d->chapters[chapter].root].first_child;
  while(root!=SIZE_MAX && d->nodes[root].kind==EXR_NODE_TEXT) root=d->nodes[root].next_sibling;
  if(root==SIZE_MAX) return exr_fail(e,EXR_FORMAT,"CFI assertion has no XML root");
  if(!walk(&w,root,0)) { status=w.status; goto done; }
  if(w.position!=SIZE_MAX && n_before<=w.position && n_after<=w.text.size-w.position &&
     (!n_before || !memcmp(w.text.data+w.position-n_before,before,n_before)) &&
     (!n_after || !memcmp(w.text.data+w.position,after,n_after))) { status=EXR_OK; goto done; }
  if(!exr_append(&query,before,n_before) || !exr_append(&query,after,n_after)) { status=exr_fail(e,EXR_LIMIT,"CFI assertion query allocation failed"); goto done; }
  status=exr_find_bytes(w.text.data,w.text.size,query.data,query.size,0,control,&start,&end,e); if(status!=EXR_OK) goto done;
  if(start==SIZE_MAX) { status=exr_fail(e,EXR_FORMAT,"CFI text assertion does not match"); goto done; }
  status=exr_find_bytes(w.text.data,w.text.size,query.data,query.size,start+1,control,&second,&last,e); if(status!=EXR_OK) goto done;
  if(second!=SIZE_MAX) { status=exr_fail(e,EXR_FORMAT,"CFI text assertion correction is ambiguous"); goto done; }
  free(w.text.data); memset(&w.text,0,sizeof(w.text)); w.mapping=1; w.desired=start+n_before; w.bytes=w.whitespace=w.visited=0;
  if(!walk(&w,root,0)) { status=w.status; goto done; }
  if(!w.found) { status=exr_fail(e,EXR_FORMAT,"CFI assertion position cannot be mapped"); goto done; }
  *point=w.result; status=EXR_OK;
done:
  free(w.text.data); free(query.data); return status;
}

exr_status exr_cfi_context(const exr_document *d,size_t chapter,const exr_cfi_point *point,size_t context,
                              const exr_control *control,char **before,char **after,exr_error *e) {
  text_walk w={0}; size_t root,start,end,count=0; uint32_t cp; exr_status status;
  *before=*after=NULL; w.doc=d; w.control=control; w.error=e; w.target=*point; w.position=SIZE_MAX;
  root=d->nodes[d->chapters[chapter].root].first_child;
  while(root!=SIZE_MAX && d->nodes[root].kind==EXR_NODE_TEXT) root=d->nodes[root].next_sibling;
  if(root==SIZE_MAX) return exr_fail(e,EXR_FORMAT,"CFI context has no XML root");
  if(!walk(&w,root,0)) { status=w.status; goto done; }
  if(w.position==SIZE_MAX) { status=exr_fail(e,EXR_ARGUMENT,"CFI context needs a Unicode scalar boundary"); goto done; }
  start=end=w.position;
  while(start && count++<context) { start--; while(start && ((unsigned char)w.text.data[start]&0xc0)==0x80) start--; }
  count=0; while(end<w.text.size && count++<context) if(!exr_next(w.text.data,w.text.size,&end,&cp)) { status=exr_fail(e,EXR_ENCODING,"Invalid CFI context text"); goto done; }
  *before=exr_copy(w.text.data ? w.text.data+start : "",w.position-start);
  *after=exr_copy(w.text.data ? w.text.data+w.position : "",end-w.position);
  if(!*before || !*after) { free(*before); free(*after); *before=*after=NULL; status=exr_fail(e,EXR_MEMORY,"CFI context allocation failed"); goto done; }
  status=EXR_OK;
done:
  free(w.text.data); return status;
}
