/* SPDX-License-Identifier: MIT */
#include <reader_commands.h>
#include <string.h>
int main(int argc,char **argv){
  reader_revisions *store=0;reader_revision_error revision={0};reader_command_error error={0};
  reader_command_result result={0};reader_command_context context={0};
  reader_book_command book={READER_COMMAND_PUT,"txt:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "txt","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","C book","Author","C book",123,0};
  reader_group_command group={READER_COMMAND_PUT,READER_GROUP_TAG,0,"C tag",0,0};
  reader_membership_command member={READER_COMMAND_PUT,READER_GROUP_TAG,0,0,0};
  uint16_t wide[]={0x4e66,0xd83d,0xde00};char utf8[8];size_t bytes=0;
  if(reader_command_utf16(wide,3,utf8,sizeof(utf8),&bytes,&error)||bytes!=7||memcmp(utf8,"\xe4\xb9\xa6\xf0\x9f\x98\x80",7))return 1;
  if(reader_command_apply_group(0,&group,&result,&error)!=READER_COMMAND_ARGUMENT)return 2;
  if(argc!=2||reader_revisions_open(argv[1],&store,&revision))return 3;
  context.store=store;
  if(reader_command_apply_book(&context,&book,&result,&error)||!result.created||!result.applied)return 4;
  if(reader_command_apply_group(&context,&group,&result,&error)||!result.created||!result.applied)return 5;
  member.group_id=result.entity_key;member.book_key=book.book_key;
  /* Copy before apply resets its result. */
  {char group_id[33];memcpy(group_id,result.entity_key,33);member.group_id=group_id;
    if(reader_command_apply_membership(&context,&member,&result,&error)||!result.created||!result.applied)return 6;}
  return reader_revisions_close(&store,&revision)?7:0;
}
