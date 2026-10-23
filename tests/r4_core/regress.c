/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"R4 check %u line %d\n",checks,__LINE__);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static int cancelled(void *context) { (void)context;return 1; }
static void check(const char *text,const exr_anchor *anchor,exr_anchor_state state,size_t start) {
  exr_document *doc=NULL;exr_fixed_text *fixed=NULL;exr_fixed_anchor f={0};
  exr_anchor_match match;exr_control control={cancelled,NULL,NULL};
  OK(exr_document_open_memory(EXR_TXT,text,strlen(text),&doc,&error));
  OK(exr_anchor_resolve(doc,anchor,&match,&error));CHECK(match.state==state);
  CHECK(match.start==(state==EXR_ANCHOR_FOUND?start:SIZE_MAX));
  CHECK(exr_anchor_resolve_ex(doc,anchor,&control,&match,&error)==EXR_CANCELLED);
  CHECK(match.state==EXR_ANCHOR_MISSING && match.start==SIZE_MAX && match.end==SIZE_MAX);
  OK(exr_fixed_text_create(text,strlen(text),NULL,0,NULL,&fixed,&error));
  f.start=f.end=SIZE_MAX;f.page_id="page";f.exact=anchor->exact;f.prefix=anchor->prefix;f.suffix=anchor->suffix;
  f.exact_size=strlen(f.exact);f.prefix_size=strlen(f.prefix);f.suffix_size=strlen(f.suffix);
  OK(exr_fixed_anchor_resolve("page",fixed,&f,NULL,&match,&error));CHECK(match.state==state);
  CHECK(match.start==(state==EXR_ANCHOR_FOUND?start:SIZE_MAX));
  CHECK(exr_fixed_anchor_resolve("page",fixed,&f,&control,&match,&error)==EXR_CANCELLED);
  CHECK(match.state==EXR_ANCHOR_MISSING && match.start==SIZE_MAX && match.end==SIZE_MAX);
  exr_fixed_text_free(fixed);exr_document_free(doc);
}
static void scopes(const char *first,const char *second,const char *third,const exr_anchor *anchor,
                   exr_anchor_state state,size_t expected) {
  exr_node_input nodes[10]={0};exr_chapter_input chapters[3]={0};exr_document_input input={0};
  const char *texts[]={first,second,third};exr_document *doc=NULL;exr_anchor a=*anchor;exr_anchor_match match;size_t i;
  nodes[0].kind=EXR_NODE_DOCUMENT;nodes[0].parent=SIZE_MAX;
  for(i=0;i<3;i++) {
    size_t root=1+i*3;nodes[root].kind=EXR_NODE_CHAPTER;nodes[root].parent=0;
    nodes[root+1].kind=EXR_NODE_PARAGRAPH;nodes[root+1].parent=root;
    nodes[root+2].kind=EXR_NODE_TEXT;nodes[root+2].parent=root+1;nodes[root+2].text=texts[i];
    chapters[i].root=root;chapters[i].path="same.xhtml";chapters[i].in_reading_order=1;
  }
  input.nodes=nodes;input.node_count=10;input.chapters=chapters;input.chapter_count=3;
  OK(exr_document_create(&input,&doc,&error));a.chapter="same.xhtml";
  OK(exr_anchor_resolve(doc,&a,&match,&error));CHECK(match.state==state);
  CHECK(match.start==(state==EXR_ANCHOR_FOUND?expected:SIZE_MAX));exr_document_free(doc);
}
int main(void) {
  char a[33],b[33],c[33],full[80],partial[80],text[512];exr_anchor anchor={0};
  memset(a,'a',32);memset(b,'b',32);memset(c,'c',32);a[32]=b[32]=c[32]=0;
  anchor.start=anchor.end=SIZE_MAX;anchor.exact="TOKEN";anchor.prefix=a;anchor.suffix=b;
  snprintf(full,sizeof(full),"%sTOKEN%s",a,b);snprintf(partial,sizeof(partial),"%sTOKEN%s",a,c);
  snprintf(text,sizeof(text),"%s|%s|later",full,full);check(text,&anchor,EXR_ANCHOR_AMBIGUOUS,0);
  snprintf(text,sizeof(text),"%s|%s|%s",partial,partial,full);
  check(text,&anchor,EXR_ANCHOR_FOUND,strlen(partial)*2+2+32);
  check(full,&anchor,EXR_ANCHOR_FOUND,32);
  check("missing",&anchor,EXR_ANCHOR_MISSING,0);
  scopes(full,full,partial,&anchor,EXR_ANCHOR_AMBIGUOUS,0);
  scopes(partial,partial,full,&anchor,EXR_ANCHOR_FOUND,strlen(partial)*2+2+32);
  anchor.exact="";snprintf(full,sizeof(full),"%s%s",a,b);snprintf(partial,sizeof(partial),"%s%s",a,c);
  snprintf(text,sizeof(text),"%s|%s",full,full);check(text,&anchor,EXR_ANCHOR_AMBIGUOUS,0);
  snprintf(text,sizeof(text),"%s|%s|%s",partial,partial,full);
  check(text,&anchor,EXR_ANCHOR_FOUND,strlen(partial)*2+2+32);
  scopes(full,full,partial,&anchor,EXR_ANCHOR_AMBIGUOUS,0);
  scopes(partial,partial,full,&anchor,EXR_ANCHOR_FOUND,strlen(partial)*2+2+32);
  printf("%u R4 ordinary/fixed/point/scope/cancellation checks passed\n",checks);return 0;
}
