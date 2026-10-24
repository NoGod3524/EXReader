/* SPDX-License-Identifier: MIT */
/* C11 consumer of the installed public header: real frozen-SDK captures are
   classified without allocation. A point is not wire-v1 representable, and a
   chapter-scoped quote cannot be carried by reflow_global. */
#include <reader_reading_state.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  exr_node_input nodes[4];exr_chapter_input chapter;exr_document_input input;exr_document *doc=NULL;
  exr_anchor point={0},quote={0};exr_error e;reader_rs_capture c;int failed=0;
  memset(nodes,0,sizeof(nodes));memset(&chapter,0,sizeof(chapter));memset(&input,0,sizeof(input));memset(&e,0,sizeof(e));
  nodes[0].kind=EXR_NODE_DOCUMENT;nodes[0].parent=SIZE_MAX;
  nodes[1].kind=EXR_NODE_CHAPTER;nodes[1].parent=0;
  nodes[2].kind=EXR_NODE_PARAGRAPH;nodes[2].parent=1;
  nodes[3].kind=EXR_NODE_TEXT;nodes[3].parent=2;nodes[3].text="点锚点 point";
  chapter.path="c.xhtml";chapter.root=1;chapter.in_reading_order=1;
  input.nodes=nodes;input.node_count=4;input.chapters=&chapter;input.chapter_count=1;
  if(exr_document_create(&input,&doc,&e)!=EXR_OK){fprintf(stderr,"document: %s\n",e.message);return 2;}
  if(exr_anchor_create(doc,3,3,&point,&e)!=EXR_OK||exr_anchor_create(doc,0,3,&quote,&e)!=EXR_OK){fprintf(stderr,"anchor: %s\n",e.message);return 2;}
  memset(&c,0,sizeof(c));c.mode=READER_RS_REFLOW_GLOBAL;c.anchor=&point;
  if(reader_rs_classify(&c)!=READER_RS_GAP_POINT)failed=1;
  c.anchor=&quote;
  if(reader_rs_classify(&c)!=(quote.chapter?READER_RS_GAP_CHAPTER_SCOPE:READER_RS_GAP_NONE))failed=1;
  printf("%s quote_gap=%d quote_chapter=%s failed=%d\n",READER_READING_STATE_VERSION,(int)reader_rs_classify(&c),quote.chapter?quote.chapter:"(none)",failed);
  exr_anchor_free(&point);exr_anchor_free(&quote);exr_document_free(doc);
  return failed;
}
