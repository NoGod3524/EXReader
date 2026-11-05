/* SPDX-License-Identifier: MIT */
/* Plain C11 consumer of the explicit raw install family. It keeps every
 * original argument/lifetime assertion of the frozen consumer and adds the raw
 * profile identity, so the complete original contract is still exercised after
 * installation. No session action and no network is used here. */
#include <reader_revisions.h>
#include <reader_sync_view.h>
#include <stddef.h>
#include <string.h>
int c_contract(void){
  if(strcmp(READER_SYNC_VIEW_VERSION,"0.2.0"))return 1;
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
  /* The installed family must define the capability macro for this consumer. */
  return 1;
#endif
  if(READER_SYNC_VIEW_MAX_ROWS!=100||READER_SYNC_VIEW_DEFAULT_ROWS!=100||READER_SYNC_VIEW_SHARD_COUNT!=256u)return 2;
  if(READER_SYNC_VIEW_OK!=0||READER_SYNC_VIEW_ARGUMENT!=1||READER_SYNC_VIEW_MEMORY!=2||
     READER_SYNC_VIEW_SESSION!=3||READER_SYNC_VIEW_REVISIONS!=4)return 3;
  if(READER_SYNC_VIEW_IDLE!=0||READER_SYNC_VIEW_SYNCING!=1||READER_SYNC_VIEW_CANCELLING!=2||
     READER_SYNC_VIEW_CANCELLED!=3||READER_SYNC_VIEW_SWEEP_COMPLETE!=4||READER_SYNC_VIEW_FAILED!=5||
     READER_SYNC_VIEW_CLOSING!=6||READER_SYNC_VIEW_CLOSED!=7||READER_SYNC_VIEW_UNKNOWN!=8)return 4;
  if(READER_SYNC_VIEW_REASON_NONE!=0||READER_SYNC_VIEW_REASON_NEEDS_CREDENTIALS!=1||
     READER_SYNC_VIEW_REASON_OFFLINE!=2||READER_SYNC_VIEW_REASON_TLS!=3||READER_SYNC_VIEW_REASON_SERVER!=4||
     READER_SYNC_VIEW_REASON_ACCOUNT!=5||READER_SYNC_VIEW_REASON_STORAGE!=6||READER_SYNC_VIEW_REASON_CONFLICT!=7||
     READER_SYNC_VIEW_REASON_INTEGRITY!=8||READER_SYNC_VIEW_REASON_LIMIT!=9||READER_SYNC_VIEW_REASON_INTERNAL!=10)return 5;
  {
    reader_sync_view_snapshot *out=(reader_sync_view_snapshot *)1;
    reader_sync_view_error error;
    memset(&error,0x7f,sizeof(error));
    if(reader_sync_view_capture(NULL,NULL,NULL,&out,&error)!=READER_SYNC_VIEW_ARGUMENT||out!=NULL)return 6;
    if(error.status!=READER_SYNC_VIEW_ARGUMENT||error.message[0]==0)return 7;
    out=(reader_sync_view_snapshot *)1;
    if(reader_sync_view_capture(NULL,NULL,NULL,NULL,NULL)!=READER_SYNC_VIEW_ARGUMENT)return 8;
    if(out!=(reader_sync_view_snapshot *)1)return 9;
    if(reader_sync_view_capture(NULL,NULL,NULL,NULL,&error)!=READER_SYNC_VIEW_ARGUMENT)return 10;
  }
  {
    reader_sync_view_summary summary;
    memset(&summary,0x7f,sizeof(summary));
    if(reader_sync_view_summary_get(NULL,&summary)!=READER_SYNC_VIEW_ARGUMENT)return 11;
    if(summary.phase!=READER_SYNC_VIEW_IDLE||summary.pending_records!=0||summary.cursor[0]!=0)return 12;
    if(reader_sync_view_summary_get(NULL,NULL)!=READER_SYNC_VIEW_ARGUMENT)return 13;
  }
  {
    reader_sync_view_row row;
    size_t copied=9;
    memset(&row,0x7f,sizeof(row));
    if(reader_sync_view_rows(NULL,0,&row,1,&copied)!=READER_SYNC_VIEW_ARGUMENT||copied!=0)return 14;
    if(reader_sync_view_rows(NULL,0,NULL,1,NULL)!=READER_SYNC_VIEW_ARGUMENT)return 15;
  }
  {
    reader_sync_view_snapshot *empty=NULL;
    if(reader_sync_view_release(&empty)!=READER_SYNC_VIEW_OK||empty!=NULL)return 16;
    if(reader_sync_view_release(NULL)!=READER_SYNC_VIEW_ARGUMENT)return 17;
  }
  {
    int phase;
    for(phase=0;phase<=9;phase++){const char *text=reader_sync_view_phase_text((reader_sync_view_phase)phase);
      if(!text||!*text||strlen(text)>24)return 18;}
    if(strcmp(reader_sync_view_phase_text(READER_SYNC_VIEW_IDLE),"idle"))return 19;
    if(strcmp(reader_sync_view_phase_text((reader_sync_view_phase)77),"unknown"))return 20;
    for(phase=0;phase<=12;phase++){const char *text=reader_sync_view_reason_text((reader_sync_view_reason)phase);
      if(!text||!*text||strlen(text)>24)return 21;}
    if(strcmp(reader_sync_view_reason_text(READER_SYNC_VIEW_REASON_NONE),"none"))return 22;
    if(strcmp(reader_sync_view_reason_text((reader_sync_view_reason)77),"unknown"))return 23;
  }
  {
    reader_sync_view_options options={0,0};
    reader_sync_view_row row;
    reader_sync_view_summary summary;
    reader_sync_view_error error;
    if(options.row_limit!=0||options.detect_conflicts!=0)return 24;
    if(sizeof(row.revision_id)!=33||sizeof(row.entity_kind)!=16||sizeof(row.operation)!=8)return 25;
    if(sizeof(summary.cursor)!=104||sizeof(error.message)!=96)return 26;
    if(sizeof(summary.shard_count)!=sizeof(unsigned))return 27;
    if(sizeof(summary.transfer_bytes)<8||sizeof(summary.attempt)<8)return 28;
  }
  /* The same installed public headers must report the raw family of every
   * dependency this package was built against. */
  if(strcmp(READER_SESSION_VERSION,"0.2.0"))return 29;
  if(strcmp(READER_SYNC_VERSION,"0.2.0"))return 30;
  if(strcmp(READER_REVISIONS_VERSION,"0.4.0"))return 31;
  if(READER_REVISION_ANCHOR_MAX_VERSION!=2u)return 32;
  return 0;
}
