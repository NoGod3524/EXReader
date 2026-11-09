/* SPDX-License-Identifier: MIT */
#include "document_internal.h"
#include "exr/layout.h"

typedef struct {
  exr_buffer xml;
  exr_ssml_chunk result;
  size_t capacity, block;
  const char *language;
  int paragraph, sentence;
} ssml_writer;

static int ssml_literal(ssml_writer *w,const char *s) { return exr_append(&w->xml,s,strlen(s)); }
static int ssml_escape(ssml_writer *w,const char *s,size_t size) {
  size_t i;
  for(i=0;i<size;i++) {
    const char *v=s[i]=='&' ? "&amp;" : s[i]=='<' ? "&lt;" : s[i]=='>' ? "&gt;" : NULL;
    if(v ? !ssml_literal(w,v) : !exr_append(&w->xml,s+i,1)) return 0;
  }
  return 1;
}
static int ssml_sentence_end(ssml_writer *w) {
  if(!w->sentence) return 1;
  w->result.sentences[w->result.sentence_count-1].ssml_end=w->xml.size;
  w->sentence=0;
  return ssml_literal(w,"</s>");
}
static int ssml_paragraph_end(ssml_writer *w,int pause) {
  if(!w->paragraph) return 1;
  if(!ssml_sentence_end(w) || !ssml_literal(w,"</p>")) return 0;
  w->paragraph=0;
  return !pause || ssml_literal(w,"<break time=\"300ms\"/>");
}
static int ssml_emit(ssml_writer *w,const char *text,size_t bytes,size_t characters,
                     size_t part,size_t start,size_t end,size_t block,const char *lang) {
  exr_ssml_sentence *s;
  if(w->paragraph && w->block!=block && !ssml_paragraph_end(w,1)) return 0;
  if(!w->paragraph) {
    if(!ssml_literal(w,"<p>")) return 0;
    w->paragraph=1;w->block=block;
  }
  if(w->sentence && (strcmp(w->language,lang) ||
     w->result.sentences[w->result.sentence_count-1].range.end.offset!=start) &&
     !ssml_sentence_end(w)) return 0;
  if(!w->sentence) {
    if(!exr_grow((void **)&w->result.sentences,&w->capacity,w->result.sentence_count+1,sizeof(*s))) return 0;
    if(!ssml_literal(w,"<s xml:lang=\"") || !ssml_literal(w,lang) || !ssml_literal(w,"\">")) return 0;
    s=&w->result.sentences[w->result.sentence_count++];
    s->range=(exr_text_range){{part,start},{part,start}};
    s->ssml_start=s->ssml_end=w->xml.size;
    w->language=lang;w->sentence=1;
  }
  if(!ssml_escape(w,text,bytes)) return 0;
  s=&w->result.sentences[w->result.sentence_count-1];s->range.end.offset=end;
  w->result.characters+=characters;
  return 1;
}
static int ssml_token(const char *list,const char *token) {
  size_t length=strlen(token);
  if(!list) return 0;
  while(*list) {
    size_t n;while(*list==' ' || *list=='\t' || *list=='\n' || *list=='\r') list++;
    n=strcspn(list," \t\r\n");
    if(n==length && !memcmp(list,token,n)) return 1;
    list+=n;
  }
  return 0;
}
static unsigned ssml_omit(const exr_node *n) {
  const char *role=exr_node_attribute(n,"role");
  const char *type=exr_node_attribute(n,"http://www.idpf.org/2007/ops|type");
  if(!type) type=exr_node_attribute(n,"epub:type");
  if(n->kind==EXR_NODE_TABLE) return EXR_SSML_HINT_TABLES;
  if(n->kind==EXR_NODE_IMAGE) return EXR_SSML_HINT_IMAGES;
  if(n->kind==EXR_NODE_NOTE || ssml_token(type,"noteref") || ssml_token(type,"footnote") ||
     ssml_token(type,"endnote") || ssml_token(role,"doc-noteref") ||
     ssml_token(role,"doc-footnote") || ssml_token(role,"doc-endnote")) return EXR_SSML_HINT_NOTES;
  return 0;
}
static const char *ssml_language(const exr_document *d,size_t index) {
  const char *lang=NULL;
  while(index!=SIZE_MAX) {
    const exr_node *n=&d->nodes[index];
    lang=exr_node_attribute(n,"http://www.w3.org/XML/1998/namespace|lang");
    if(!lang) lang=exr_node_attribute(n,"xml:lang");
    if(!lang) lang=exr_node_attribute(n,"lang");
    if(lang && *lang) break;
    index=n->parent;
  }
  if(!lang || !*lang) lang=d->language;
  return lang && (lang[0]=='e' || lang[0]=='E') && (lang[1]=='n' || lang[1]=='N') &&
    (!lang[2] || lang[2]=='-') ? "en-US" : "zh-CN";
}
static size_t ssml_after(const exr_document *d,size_t node) {
  while(node!=SIZE_MAX) {
    if(d->nodes[node].next_sibling!=SIZE_MAX) return d->nodes[node].next_sibling;
    node=d->nodes[node].parent;
  }
  return d->node_count;
}
void exr_ssml_chunk_free(exr_ssml_chunk *chunk) {
  if(!chunk) return;
  free(chunk->ssml);free(chunk->sentences);memset(chunk,0,sizeof(*chunk));
}
exr_status exr_document_ssml(exr_publication *p,exr_ssml_position from,size_t limit,
                            exr_ssml_chunk *out,unsigned flags,const exr_control *control,exr_error *e) {
  ssml_writer w={0};exr_document *d=NULL;exr_status status=EXR_OK;
  size_t count=0,part,node=0,at=0,block=0;const exr_part *parts;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing SSML output");
  memset(out,0,sizeof(*out));
  if(!limit) limit=800;
  parts=exr_publication_parts(p,&count);
  if(!p || from.part>count || (from.part==count && (from.offset || from.node)) ||
     flags&~7u || limit>65536 || (flags && limit<8))
    return exr_fail(e,EXR_ARGUMENT,"Invalid SSML cursor, flags or character budget");
  status=exr_control_cancel(control,e);if(status!=EXR_OK) return status;
  if(!ssml_literal(&w,"<speak xmlns=\"http://www.w3.org/2001/10/synthesis\" version=\"1.0\" xml:lang=\"zh-CN\">")) goto memory;
  w.result.next=from;
  for(part=from.part;part<count;part++) {
    if(!parts[part].in_reading_order) {w.result.next=(exr_ssml_position){part+1,0,0};continue;}
    status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;
    status=exr_publication_load(p,part,&d,e);if(status!=EXR_OK) goto done;
    at=part==from.part ? from.offset:0;node=part==from.part ? from.node:0;
    if(at>d->size || node>d->node_count || (at<d->size && ((unsigned char)d->text[at]&0xc0)==0x80)) {
      status=exr_fail(e,EXR_ARGUMENT,"SSML cursor is outside text or inside UTF-8");goto done;
    }
    block=0;
    while(node<d->node_count) {
      const exr_node *n=&d->nodes[node];unsigned omit=ssml_omit(n);const char *lang;
      if(!(node&255)) {status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;}
      if(n->start==SIZE_MAX || n->end<at || (n->end==at && n->start<n->end)) {node++;continue;}
      if(!omit && n->kind!=EXR_NODE_TEXT) {node++;continue;}
      if(n->start>at) at=n->start;
      while(block+1<d->count && at>=d->blocks[block+1].start) block++;
      lang=ssml_language(d,node);
      if(omit) {
        if(!ssml_sentence_end(&w)) goto memory;
        if(flags&omit) {
          int english=!strcmp(lang,"en-US");
          const char *hint=omit==EXR_SSML_HINT_IMAGES ? (english ? "Image.":"图。") :
            omit==EXR_SSML_HINT_TABLES ? (english ? "Table.":"表。") : (english ? "Note.":"注。");
          size_t chars=english ? strlen(hint):2;
          if(chars>limit-w.result.characters) break;
          if(!ssml_emit(&w,hint,strlen(hint),chars,part,at,n->end,block,lang) || !ssml_sentence_end(&w)) goto memory;
        }
        at=n->end;node=ssml_after(d,node);
      } else {
        while(at<n->end && w.result.characters<limit) {
          size_t start=at;uint32_t cp;
          if(!exr_next(d->text,n->end,&at,&cp)) {status=exr_fail(e,EXR_ENCODING,"Invalid SSML source UTF-8");goto done;}
          /* XML 1.0 excludes control characters even in plain-text inputs. */
          if((cp<32 && cp!=9 && cp!=10 && cp!=13) || cp==0xfffe || cp==0xffff) continue;
          if(!ssml_emit(&w,d->text+start,at-start,1,part,start,at,block,lang)) goto memory;
          if((cp=='.' || cp=='!' || cp=='?' || cp==0x3002 || cp==0xff01 || cp==0xff1f || cp==0xff1b) &&
             !ssml_sentence_end(&w)) goto memory;
        }
        if(at==n->end) node++;
      }
      if(w.result.characters==limit) break;
    }
    w.result.next=node==d->node_count ? (exr_ssml_position){part+1,0,0} : (exr_ssml_position){part,at,node};
    if(!ssml_paragraph_end(&w,d->count && at>=d->blocks[block].end)) goto memory;
    exr_document_free(d);d=NULL;
    if(w.result.characters) break;
  }
  /* Directory-only lookahead; do not load the next chapter just to detect EOF. */
  while(w.result.next.part<count && !parts[w.result.next.part].in_reading_order) w.result.next.part++;
  w.result.end=w.result.next.part==count;
  if(!ssml_literal(&w,"</speak>")) goto memory;
  status=exr_control_cancel(control,e);if(status!=EXR_OK) goto done;
  w.result.ssml=w.xml.data;w.result.size=w.xml.size;*out=w.result;
  return exr_fail(e,EXR_OK,"");
memory:
  status=exr_fail(e,EXR_MEMORY,"SSML allocation failed");
done:
  exr_document_free(d);free(w.xml.data);free(w.result.sentences);return status;
}
