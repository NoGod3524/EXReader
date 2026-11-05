/* SPDX-License-Identifier: MIT */
/* Installed C example: inspect a conflict, then apply the user's explicit group choice. */
#include <reader_conflict_actions.h>
#include <string.h>
int main(int argc,char **argv){
  reader_conflict_owner *owner=0;reader_conflict_snapshot *snapshot=0;reader_conflict_error error;
  reader_conflict_target target;reader_group_command group;reader_conflict_result result;
  const reader_conflict_view *view;
  memset(&target,0,sizeof(target));memset(&group,0,sizeof(group));memset(&error,0,sizeof(error));
  if(argc!=3)return 1;
  if(reader_conflict_prepare(0,&target,0,&snapshot,&error)!=READER_CONFLICT_ARGUMENT)return 2;
  if(reader_conflict_open(argv[1],&owner,&error))return 3;
  target.kind=READER_CONFLICT_TARGET_GROUP;target.group_kind=READER_GROUP_TAG;target.group_id=argv[2];
  if(reader_conflict_prepare(owner,&target,0,&snapshot,&error))return 4;
  view=reader_conflict_snapshot_view(snapshot);
  if(!view||view->head_count!=2||view->state!=READER_CONFLICT_STATE_CONCURRENT||!view->resolvable||!view->heads[0].wire[0])return 5;
  group.operation=READER_COMMAND_PUT;group.kind=READER_GROUP_TAG;group.id=argv[2];group.name="C explicit merge";
  if(reader_conflict_resolve_group(owner,snapshot,0,&group,0,&result,&error)||!result.committed||!result.command.created||result.observed_heads!=2)return 6;
  reader_conflict_snapshot_free(snapshot);
  return reader_conflict_close(&owner,&error)?7:0;
}
