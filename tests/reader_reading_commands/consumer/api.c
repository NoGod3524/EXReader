/* SPDX-License-Identifier: MIT */
/* C11 consumer of the installed public header: a real SDK capture is saved as a
   highlight through the C ABI, retried by ID, and read back by the revision API. */
#include <reader_reading_commands.h>
#include <reader_commands.h>
#include <stdio.h>
#include <string.h>

int main(int argc,char **argv){
  reader_revisions *store=NULL;reader_revision_error re;reader_command_context cc;reader_command_result cr;reader_command_error ce;reader_book_command book;
  exr_node_input nodes[4];exr_chapter_input chapter;exr_document_input input;exr_document *doc=NULL;exr_anchor anchor;exr_error e;
  reader_rc_context ctx;reader_rc_command cmd;reader_rc_result res,again;reader_rc_error err;reader_rs_capture cap;
  const char *sha="2222222222222222222222222222222222222222222222222222222222222222";
  const char *book_key="txt:2222222222222222222222222222222222222222222222222222222222222222";
  const char *revision="0123456789abcdef0123456789abcdef",*annotation="fedcba9876543210fedcba9876543210";
  char *wire=NULL;size_t bytes=0;reader_revision_info info;int failed=0;
  if(argc<2)return 2;
  memset(&re,0,sizeof(re));memset(&cc,0,sizeof(cc));memset(&cr,0,sizeof(cr));memset(&ce,0,sizeof(ce));memset(&book,0,sizeof(book));
  memset(nodes,0,sizeof(nodes));memset(&chapter,0,sizeof(chapter));memset(&input,0,sizeof(input));memset(&anchor,0,sizeof(anchor));memset(&e,0,sizeof(e));
  memset(&ctx,0,sizeof(ctx));memset(&cmd,0,sizeof(cmd));memset(&res,0,sizeof(res));memset(&again,0,sizeof(again));memset(&err,0,sizeof(err));memset(&cap,0,sizeof(cap));
  if(reader_revisions_open(argv[1],&store,&re)!=READER_REV_OK){fprintf(stderr,"open: %s\n",re.message);return 2;}
  cc.store=store;book.operation=READER_COMMAND_PUT;book.book_key=book_key;book.format="txt";book.source_sha256=sha;book.title="C";book.author="";book.sort_title="C";book.source_bytes=64;
  if(reader_command_apply_book(&cc,&book,&cr,&ce)!=READER_COMMAND_OK){fprintf(stderr,"book: %s\n",ce.message);return 2;}
  nodes[0].kind=EXR_NODE_DOCUMENT;nodes[0].parent=SIZE_MAX;nodes[1].kind=EXR_NODE_CHAPTER;nodes[1].parent=0;nodes[2].kind=EXR_NODE_PARAGRAPH;nodes[2].parent=1;
  nodes[3].kind=EXR_NODE_TEXT;nodes[3].parent=2;nodes[3].text="C consumer highlight target";
  chapter.path="c.xhtml";chapter.root=1;chapter.in_reading_order=1;input.nodes=nodes;input.node_count=4;input.chapters=&chapter;input.chapter_count=1;
  if(exr_document_create(&input,&doc,&e)!=EXR_OK||exr_anchor_create(doc,11,20,&anchor,&e)!=EXR_OK){fprintf(stderr,"sdk: %s\n",e.message);return 2;}
  cap.mode=READER_RS_REFLOW_GLOBAL;cap.anchor=&anchor;
  ctx.store=store;ctx.revision_id=revision;ctx.parser_version="exreader-sdk-c-consumer";
  cmd.kind=READER_RC_HIGHLIGHT;cmd.operation=READER_RC_PUT;cmd.book_key=book_key;cmd.annotation_id=annotation;cmd.capture=&cap;cmd.text="c text";
  if(reader_rc_apply(&ctx,&cmd,&res,&err)!=READER_RC_OK||res.created!=1){fprintf(stderr,"apply: %s\n",err.message);failed=1;}
  if(reader_rc_apply(&ctx,&cmd,&again,&err)!=READER_RC_OK||again.created!=0||strcmp(res.sha256,again.sha256)){fprintf(stderr,"retry: %s\n",err.message);failed=1;}
  if(reader_revision_get(store,revision,&wire,&bytes,&info,&re)!=READER_REV_OK||bytes!=res.bytes||strcmp(info.sha256,res.sha256)||strcmp(info.operation,"put")){fprintf(stderr,"readback\n");failed=1;}
  reader_revision_bytes_free(wire);
  if(reader_rc_apply(NULL,&cmd,&res,&err)!=READER_RC_ARGUMENT){fprintf(stderr,"null context\n");failed=1;}
  printf("%s sha=%s failed=%d\n",READER_READING_COMMANDS_VERSION,res.sha256,failed);
  exr_anchor_free(&anchor);exr_document_free(doc);reader_revisions_close(&store,&re);
  return failed;
}
