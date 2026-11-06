/* SPDX-License-Identifier: MIT */
/* Standalone observer self-check; compile against the same SDK as the probe. */
#define main cjk_probe_entry
#include "../tools/probes/cjk_measure.c"
#undef main
#include <assert.h>

int main(void) {
  exr_node_input input_nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,2,NULL,"\xe7\x94\xb2 \xef\xbc\x9a\xe4\xb9\x99",NULL,0},
    {EXR_NODE_BREAK,2,"br",NULL,NULL,0},
    {EXR_NODE_TEXT,2,NULL,"\xef\xbc\x8c\xe4\xb9\x99",NULL,0},
    {EXR_NODE_PARAGRAPH,1,"p",NULL,NULL,0},
    {EXR_NODE_TEXT,6,NULL,"\xe2\x80\x9d\xe4\xb9\x99",NULL,0}};
  exr_chapter_input chapter={"probe","probe.unit",1,1};
  exr_document_input input={"Probe categories",input_nodes,8,&chapter,1,NULL,0};
  exr_document *doc=NULL;exr_error error={0};size_t count;
  const exr_node *nodes;exr_glyph first={0};
  assert(tail_bad(0x201c) && !head_bad(0x201c));
  assert(head_bad(0x201d) && !tail_bad(0x201d));
  assert(punct(0xff1a) && punct(0x201c)); /* colon + opening quote */
  assert(punct(0x3002) && punct(0x201d)); /* period + closing quote */
  assert(exr_document_create(&input,&doc,&error)==EXR_OK);
  nodes=exr_document_nodes(doc,&count);
  first.node=3;first.start=nodes[3].start+4;
  assert(head_reason(doc,nodes,count,&first,0)==SOFT_WRAP);
  first.boundaries=EXR_BOUNDARY_GLUE;
  assert(head_reason(doc,nodes,count,&first,1)==UNBREAKABLE_OVERFLOW);
  first.boundaries=EXR_BOUNDARY_MANDATORY;
  assert(head_reason(doc,nodes,count,&first,0)==FORCED_BREAK);
  first.boundaries=0;first.node=5;first.start=nodes[5].start;
  assert(head_reason(doc,nodes,count,&first,0)==FORCED_BREAK);
  first.node=7;first.start=nodes[7].start;
  assert(head_reason(doc,nodes,count,&first,0)==PARAGRAPH_START);
  exr_document_free(doc);puts("CJK probe: quote sets and four head categories passed");
  return 0;
}
