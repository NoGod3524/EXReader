/* SPDX-License-Identifier: MIT */
#include "../src/document_internal.h"
#include <stdio.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)

typedef struct { size_t size,reads;int cancel_after_read; } counted_text;
static const char *span(void *context,size_t offset,size_t *available) {
  static const char letters[]="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  counted_text *text=context;
  *available=0;
  /* A virtual large source makes a full scan fail promptly, without memory
     allocation or a timing-dependent performance assertion. */
  if(++text->reads>64 || offset>text->size) return NULL;
  *available=text->size-offset;
  if(*available>sizeof(letters)-1) *available=sizeof(letters)-1;
  return letters;
}
static int cancelled(void *context) {
  counted_text *text=context;return text->cancel_after_read && text->reads>0;
}
static void boundary_source(void) {
  counted_text text={100u*1024u*1024u,0,0};exr_document document={0};exr_document_view view={0};
  exr_anchor anchor={0};exr_anchor_match match;exr_control control={0};
  view.context=&text;view.text=span;document.view=&view;document.size=text.size;
  anchor.exact="";anchor.prefix="";anchor.suffix="aaaa";
  OK(exr_anchor_resolve_ex(&document,&anchor,NULL,&match,&error));
  CHECK(match.state==EXR_ANCHOR_FOUND && match.start==0 && match.end==0 && text.reads<=64);
  text.reads=0;anchor.start=anchor.end=text.size;anchor.prefix="aaaa";anchor.suffix="";
  OK(exr_anchor_resolve_ex(&document,&anchor,NULL,&match,&error));
  CHECK(match.state==EXR_ANCHOR_FOUND && match.start==text.size && match.end==text.size && text.reads<=64);
  text.reads=0;text.cancel_after_read=1;control.cancelled=cancelled;control.context=&text;
  anchor.start=anchor.end=0;anchor.prefix="";anchor.suffix="aaaa";
  CHECK(exr_anchor_resolve_ex(&document,&anchor,&control,&match,&error)==EXR_CANCELLED);
  CHECK(match.state==EXR_ANCHOR_MISSING && match.start==SIZE_MAX && match.end==SIZE_MAX);
}
static exr_document *two_scopes(const char *first,const char *second) {
  exr_document_input input={0};exr_node_input nodes[7]={{0}};exr_chapter_input chapters[2]={{0}};
  exr_document *document=NULL;size_t i;const char *texts[]={first,second};
  nodes[0].kind=EXR_NODE_DOCUMENT;nodes[0].parent=SIZE_MAX;
  for(i=0;i<2;i++) {
    size_t root=1+i*3;
    nodes[root].kind=EXR_NODE_CHAPTER;nodes[root].parent=0;
    nodes[root+1].kind=EXR_NODE_PARAGRAPH;nodes[root+1].parent=root;
    nodes[root+2].kind=EXR_NODE_TEXT;nodes[root+2].parent=root+1;nodes[root+2].text=texts[i];
    chapters[i].path=i ? "next.xhtml" : "same.xhtml";chapters[i].root=root;chapters[i].in_reading_order=1;
  }
  input.nodes=nodes;input.node_count=7;input.chapters=chapters;input.chapter_count=2;
  OK(exr_document_create(&input,&document,&error));
  /* The public constructor requires unique paths. The EPUB parser can retain
     repeated spine entries, so represent that private state explicitly. */
  free((void *)document->chapters[1].path);
  document->chapters[1].path=exr_copy("same.xhtml",10);
  CHECK(document->chapters[1].path!=NULL);return document;
}
static void scope_semantics(void) {
  exr_document *document=NULL;exr_anchor anchor={0};exr_anchor_match match;
  anchor.exact="";anchor.prefix="";anchor.suffix="aaaa";anchor.chapter="same.xhtml";
  document=two_scopes("aaaa","aaaa");
  OK(exr_anchor_resolve(document,&anchor,&match,&error));
  CHECK(match.state==EXR_ANCHOR_AMBIGUOUS && match.start==SIZE_MAX && match.end==SIZE_MAX);
  exr_document_free(document);
  document=two_scopes("aaaa","baaaa");
  OK(exr_anchor_resolve(document,&anchor,&match,&error));
  CHECK(match.state==EXR_ANCHOR_FOUND && match.start==0);exr_document_free(document);
  document=two_scopes("baaaa","aaaa");
  OK(exr_anchor_resolve(document,&anchor,&match,&error));
  CHECK(match.state==EXR_ANCHOR_FOUND && match.start>0);exr_document_free(document);
  /* A mismatching boundary must retain the old full search and its ties. */
  anchor.chapter=NULL;anchor.suffix="bbbb";
  OK(exr_document_open_memory(EXR_TXT,"aaaabbbb",8,&document,&error));
  OK(exr_anchor_resolve(document,&anchor,&match,&error));
  CHECK(match.state==EXR_ANCHOR_AMBIGUOUS);exr_document_free(document);
}
int main(void) {
  boundary_source();scope_semantics();printf("%u boundary anchor checks passed\n",checks);return 0;
}
