/* SPDX-License-Identifier: MIT */
#include <reader_metadata.h>
#include <catalog.h>
#include <string.h>
int main(int argc,char **argv){
  reader_metadata_owner *owner=0;reader_metadata_snapshot *snapshot=0;
  reader_metadata_error error={0};reader_metadata_result result={0};
  reader_catalog *catalog=0;reader_catalog_error catalog_error={0};
  const char *sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  const char *key="txt:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  reader_catalog_book book={"txt",0,"C edited book","C author","C edited book","reflow_global",123,777,1};
  reader_metadata_verified_source source={"txt",0,123};
  reader_group_command group={READER_COMMAND_PUT,READER_GROUP_TAG,0,"C tag",0,0};
  reader_membership_command member={READER_COMMAND_PUT,READER_GROUP_TAG,0,0,0};
  char group_id[33];
  if(argc!=3)return 1;
  book.sha256=sha;source.source_sha256=sha;
  if(reader_catalog_open(argv[1],&catalog,&catalog_error)||reader_catalog_attach(catalog,&book,&catalog_error)||reader_catalog_close(&catalog,&catalog_error))return 2;
  if(reader_metadata_open(argv[1],argv[2],&owner,&error))return 3;
  if(reader_metadata_prepare_book(owner,key,&snapshot,&error)!=READER_METADATA_NEEDS_BOOTSTRAP)return 4;
  if(strcmp(reader_metadata_snapshot_view(snapshot)->book.title,"C edited book"))return 5;
  if(reader_metadata_stage_bootstrap(owner,snapshot,&source,&result,&error)||reader_metadata_finish_pending(owner,&result,&error)||!result.committed)return 6;
  reader_metadata_snapshot_free(snapshot);snapshot=0;
  if(reader_metadata_prepare_group(owner,READER_GROUP_TAG,0,&snapshot,&error)||reader_metadata_stage_group(owner,snapshot,&group,&result,&error))return 7;
  memcpy(group_id,result.command.entity_key,33);
  if(reader_metadata_apply_pending(owner,&result,&error)||!result.committed||!result.pending||reader_metadata_finish_pending(owner,&result,&error)||result.command.created||result.pending)return 8;
  reader_metadata_snapshot_free(snapshot);snapshot=0;
  member.group_id=group_id;member.book_key=key;
  if(reader_metadata_prepare_membership(owner,READER_GROUP_TAG,group_id,key,&snapshot,&error)||reader_metadata_stage_membership(owner,snapshot,&member,&result,&error)||reader_metadata_finish_pending(owner,&result,&error))return 9;
  reader_metadata_snapshot_free(snapshot);
  if(reader_metadata_pending(owner,&result,&error)!=READER_METADATA_NO_PENDING)return 10;
  return reader_metadata_close(&owner,&error)?11:0;
}
