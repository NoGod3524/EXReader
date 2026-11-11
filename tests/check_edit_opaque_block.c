/* SPDX-License-Identifier: MIT */
#include <exr/edit.h>
#include <stdio.h>
#include <string.h>
#ifdef EXR_WITH_REFLOW
#include <exr/reflow.h>
#endif
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); return 1; } } while (0)
int main(int argc,char **argv) {
  const char xml[]="<w:customXml><w:p/></w:customXml>";
  exr_edit_block block={0}; exr_edit_doc *doc=NULL;
  const exr_edit_block *stored; exr_edit_id inserted=0;
  block.kind=EXR_EDIT_OPAQUE_BLOCK;block.opaque_xml=xml;block.opaque_size=sizeof(xml)-1;
  exr_status status=exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&doc);
  printf("opaque block create status=%d\n",status);
  CHECK(status==EXR_OK && doc);
  stored=exr_edit_block_at(doc,0);
  CHECK(stored && stored->kind==EXR_EDIT_OPAQUE_BLOCK);
  CHECK(stored->opaque_xml!=xml && stored->opaque_size==sizeof(xml)-1 && !memcmp(stored->opaque_xml,xml,sizeof(xml)-1));
#ifdef EXR_WITH_REFLOW
  {
    exr_font *font=NULL; exr_error error={0}; exr_pager *pager=NULL;
    exr_layout_config config=exr_layout_config_defaults();
    CHECK(argc==2 && exr_font_open(argv[1],&font,&error)==EXR_OK);
    status=exr_edit_pager_create(doc,font,&config,&pager,&error);
    printf("opaque block reflow status=%d (%s)\n",status,error.message);
    CHECK(status==EXR_UNSUPPORTED && !pager);
    exr_font_free(font);
  }
#else
  (void)argc; (void)argv;
#endif
  CHECK(exr_edit_insert_paragraph(doc,stored->id,NULL,0,NULL,&inserted)==EXR_OK);
  CHECK(exr_edit_undo(doc)==EXR_OK && exr_edit_block_count(doc)==1);
  CHECK(exr_edit_redo(doc)==EXR_OK && exr_edit_block_count(doc)==2);
  exr_edit_doc_free(doc);doc=NULL;
  block.opaque_size=0;
  CHECK(exr_edit_doc_create(NULL,0,&block,1,NULL,0,NULL,&doc)==EXR_ARGUMENT && !doc);
  puts("PASS: opaque XML retained across history; empty opaque block rejected");
  return 0;
}
