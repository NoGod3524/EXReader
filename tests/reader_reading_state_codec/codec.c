/* SPDX-License-Identifier: MIT */
/* Pure-value installed codec consumer: no SDK handles or SDK functions. */
#include <reader_reading_state.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(value) do { if(!(value)){fprintf(stderr,"codec check line %d\n",__LINE__);return 1;} } while(0)
int main(void){
  reader_revisions *store=NULL;reader_rs_error error={0};
  reader_rs_envelope envelope={0};reader_rs_capture capture={0};exr_anchor anchor={0};
  reader_rs_record record={0};char *wire=NULL;size_t bytes=0;
  CHECK(reader_revisions_open(":memory:",&store,NULL)==READER_REV_OK);
  envelope.revision_id="00000000000000000000000000000001";envelope.operation="put";
  envelope.entity_kind="annotation";envelope.annotation_id="00000000000000000000000000000002";
  envelope.book_key="txt:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  envelope.parser_version="exreader-sdk-3.40.0";envelope.note_text="product-owned";
  capture.mode=READER_RS_REFLOW_GLOBAL;capture.anchor=&anchor;
  anchor.start=2;anchor.end=7;anchor.exact="quote";anchor.prefix="p ";anchor.suffix=" s";
  CHECK(reader_rs_encode(store,&envelope,&capture,&wire,&bytes,&error)==READER_RS_OK);
  CHECK(reader_rs_decode(store,wire,bytes,&record,&error)==READER_RS_OK);
  CHECK(record.anchor_version==1&&record.start==2&&record.end==7&&!strcmp(record.exact,"quote"));
  reader_rs_record_free(&record);reader_rs_free(wire);wire=NULL;
  anchor.end=2;anchor.exact="";anchor.chapter="chapter.xhtml";
  CHECK(reader_rs_encode(store,&envelope,&capture,&wire,&bytes,&error)==READER_RS_NOT_REPRESENTABLE&&wire==NULL&&bytes==0);
  CHECK(reader_rs_encode_v2(store,&envelope,&capture,0,&wire,&bytes,&error)==READER_RS_OK);
  CHECK(reader_rs_decode(store,wire,bytes,&record,&error)==READER_RS_OK);
  CHECK(record.anchor_version==2&&record.start==2&&record.end==2&&record.exact_size==0&&record.chapter&&!strcmp(record.chapter,anchor.chapter));
  reader_rs_record_free(&record);reader_rs_free(wire);wire=NULL;
  CHECK(reader_rs_decode(store,"{}",2,&record,&error)==READER_RS_REVISION);
  CHECK(reader_revisions_close(&store,NULL)==READER_REV_OK);
  puts("installed codec v1/v2 values and rejection passed; no SDK linked");return 0;
}
