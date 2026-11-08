/* SPDX-License-Identifier: MIT */
#include "document_internal.h"

/* Retained node ranges already encode projection visibility, block breaks and
   cross-inline whitespace. Replay only each text node's non-space scalars;
   never rebuild or mutate the projection used by layout. */
static exr_status mapping(const exr_document *d,size_t chapter,size_t wanted,const exr_cfi_point *point,
                          const exr_control *control,exr_cfi_point *out,size_t *offset,exr_error *e) {
  size_t i,lo,hi; exr_status status;
  if(!d || chapter>=d->chapter_count) return exr_fail(e,EXR_ARGUMENT,"Invalid CFI offset chapter");
  if(d->view) return exr_fail(e,EXR_UNSUPPORTED,"CFI offset mapping requires a retained DOM snapshot");
  lo=d->nodes[d->chapters[chapter].root].start;hi=d->nodes[d->chapters[chapter].root].end;
  if(!point && (lo==SIZE_MAX || wanted<lo || wanted>hi || wanted>d->size ||
      (wanted<d->size && ((unsigned char)d->text[wanted]&0xc0)==0x80)))
    return exr_fail(e,EXR_ARGUMENT,"CFI offset is not a projected UTF-8 boundary in this chapter");
  if(point && (point->node>=d->node_count || d->nodes[point->node].chapter!=chapter || point->side>2))
    return exr_fail(e,EXR_ARGUMENT,"Invalid CFI point for offset mapping");
  status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  if(point && d->nodes[point->node].kind!=EXR_NODE_TEXT) {
    const exr_node *v=&d->nodes[point->node];size_t child=v->first_child,k=0;
    if(v->start==SIZE_MAX) return exr_fail(e,EXR_FORMAT,"Unprojected CFI element");
    if(point->offset==SIZE_MAX) { *offset=v->start;return exr_fail(e,EXR_OK,""); }
    while(child!=SIZE_MAX && k<point->offset) { child=d->nodes[child].next_sibling;k++; }
    if(k!=point->offset) return exr_fail(e,EXR_ARGUMENT,"CFI child offset exceeds element");
    while(child!=SIZE_MAX && d->nodes[child].start==SIZE_MAX) child=d->nodes[child].next_sibling;
    *offset=child==SIZE_MAX ? v->end : d->nodes[child].start;
    return exr_fail(e,EXR_OK,"");
  }
  for(i=0;i<d->node_count;i++) {
    const exr_node *v=&d->nodes[i];size_t at=0,units=0,pos,n,next_check=4096;const char *s;
    if(!(i%256)) { status=exr_control_cancel(control,e);if(status!=EXR_OK) return status; }
    if(v->chapter!=chapter || v->kind!=EXR_NODE_TEXT || (point && point->node!=i) || v->start==SIZE_MAX) continue;
    s=v->text ? v->text : "";n=strlen(s);pos=v->start;
    while(at<n) {
      size_t begin=at;uint32_t cp;
      if(!exr_next(s,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Invalid raw XML text in CFI mapping");
      if(!exr_projection_space(cp)) {
        if(pos<v->end && d->text[pos]==' ') pos++;
        if(pos>v->end || at-begin>v->end-pos || memcmp(d->text+pos,s+begin,at-begin))
          return exr_fail(e,EXR_FORMAT,"CFI DOM projection does not match retained text");
        if(!point && wanted==pos) { *out=(exr_cfi_point){i,units,0};return exr_fail(e,EXR_OK,""); }
      }
      if(point && point->offset==units) { *offset=pos;return exr_fail(e,EXR_OK,""); }
      if(!exr_projection_space(cp)) {
        pos+=at-begin;
        if(!point && wanted==pos) { *out=(exr_cfi_point){i,units+(cp>0xffff ? 2 : 1),0};return exr_fail(e,EXR_OK,""); }
      } else if(pos<d->size && d->text[pos]==' ') pos++;
      units+=cp>0xffff ? 2 : 1;
      if(at>=next_check) { status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;next_check=at+4096; }
    }
    if(point && point->offset==units) { *offset=pos;return exr_fail(e,EXR_OK,""); }
  }
  /* Empty chapters have no projected character to select. */
  if(!point && lo==hi && wanted==lo) {
    size_t root=d->nodes[d->chapters[chapter].root].first_child;
    while(root!=SIZE_MAX && d->nodes[root].kind==EXR_NODE_TEXT) root=d->nodes[root].next_sibling;
    if(root!=SIZE_MAX) { *out=(exr_cfi_point){root,0,0};return exr_fail(e,EXR_OK,""); }
  }
  return exr_fail(e,EXR_ARGUMENT,"CFI boundary has no projected scalar mapping");
}
exr_status exr_document_cfi_point_at(const exr_document *d,size_t chapter,size_t offset,const exr_control *control,
                                     exr_cfi_point *out,exr_error *e) {
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI mapping point output");
  *out=(exr_cfi_point){SIZE_MAX,SIZE_MAX,0};
  return mapping(d,chapter,offset,NULL,control,out,NULL,e);
}
exr_status exr_document_cfi_point_offset(const exr_document *d,size_t chapter,const exr_cfi_point *point,
                                         const exr_control *control,size_t *out,exr_error *e) {
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing CFI mapping offset output");
  *out=SIZE_MAX;
  if(!point) return exr_fail(e,EXR_ARGUMENT,"Missing CFI mapping point");
  return mapping(d,chapter,0,point,control,NULL,out,e);
}
