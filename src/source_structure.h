/* SPDX-License-Identifier: MIT */
#ifndef EXR_SOURCE_STRUCTURE_H
#define EXR_SOURCE_STRUCTURE_H
/* Recover plain-text chapter/paragraph lines embedded in XHTML text nodes.
   Iterate raw lines once, mapping to the existing normalized projection. No
   document nodes or source offsets are rewritten, including bounded readers. */
typedef struct {
  size_t raw, projected, start, end;
  int pending, previous_special, ready, indented;
  exr_block_kind kind;
} source_structure;
static int source_white(unsigned char c) { return c==' ' || c=='\t' || c=='\r' || c=='\n'; }
static exr_block_kind source_line(const char *text,size_t a,size_t b,int *indented) {
  size_t i=a,n=0; uint32_t cp; int digits=0,rule=1;
  *indented=b-a>=6 && !memcmp(text+a,"\xe3\x80\x80\xe3\x80\x80",6);
  while(i<b) {
    if(!exr_next(text,b,&i,&cp)) return EXR_BLOCK_BODY;
    if(cp!='_' && cp!='-' && cp!=0x2014 && cp!=0x2015 && cp!=' ' && cp!='\t') rule=0;
    if(cp!=' ' && cp!='\t') n++;
  }
  if(rule && n>=3) return EXR_BLOCK_ORNAMENT;
  i=a;
  if(!exr_next(text,b,&i,&cp) || cp!=0x7b2c || n>120) return EXR_BLOCK_BODY;
  while(i<b && exr_next(text,b,&i,&cp)) {
    if((cp>='0' && cp<='9') || cp==0x3007 || cp==0x96f6 || cp==0x4e00 || cp==0x4e8c ||
       cp==0x4e09 || cp==0x56db || cp==0x4e94 || cp==0x516d || cp==0x4e03 || cp==0x516b ||
       cp==0x4e5d || cp==0x5341 || cp==0x767e || cp==0x5343) { digits++;continue; }
    return digits && (cp==0x56de || cp==0x7ae0 || cp==0x8282) ? EXR_BLOCK_TITLE : EXR_BLOCK_BODY;
  }
  return EXR_BLOCK_BODY;
}
static void source_next(const exr_document *doc,const exr_node *node,source_structure *s) {
  const char *raw=node->text; size_t length=raw ? strlen(raw) : 0;
  s->ready=0;
  while(s->raw<length) {
    size_t a=s->raw,b=a,i,begin=SIZE_MAX; int indented,emit;
    exr_block_kind kind;
    while(b<length && raw[b]!='\n') b++;
    while(a<b && source_white((unsigned char)raw[a])) a++;
    kind=source_line(raw,a,b,&indented);
    emit=kind!=EXR_BLOCK_BODY || indented || s->previous_special;
    i=s->raw;
    while(i<b) {
      size_t at=i;uint32_t cp;
      if(!exr_next(raw,b,&i,&cp)) break;
      if(exr_projection_space(cp)) { s->pending=1;continue; }
      /* Pending projected whitespace can straddle inline nodes. Read its actual
         projected byte rather than guessing the preceding node's last scalar. */
      if(s->pending && s->projected<node->end && exr_doc_byte(doc,s->projected)==' ') s->projected++;
      s->pending=0;
      if(begin==SIZE_MAX) begin=s->projected;
      s->projected+=i-at;
    }
    s->raw=b<length ? b+1 : b;s->pending=1;
    if(begin!=SIZE_MAX) s->previous_special=kind!=EXR_BLOCK_BODY;
    if(emit && begin!=SIZE_MAX) {
      s->start=begin;s->end=s->projected;s->kind=kind;s->indented=indented;s->ready=1;return;
    }
  }
}
#endif
