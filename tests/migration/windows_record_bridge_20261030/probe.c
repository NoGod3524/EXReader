/* SPDX-License-Identifier: MIT */
#include <lm_win_record_bridge.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
static unsigned checks,failed;
static void ck(int ok,const char *name){checks++;if(!ok){failed++;fprintf(stderr,"FAIL %s native=%lu\n",name,(unsigned long)GetLastError());}}
static void cut(const char *mode,const char *at){
 if(!strcmp(mode,at)){printf("ready-%s\n",at);fflush(stdout);Sleep(INFINITE);}
}
int main(int argc,char **argv){
 wr_context c,other;wr_error e={0};wr_identity id,root_id,parent_id;lm_wr_record record={0},bad,next;
 lm_rb *bridge=NULL,*refused=NULL;lm_wp_custody *custody=NULL,*other_custody=NULL;
 lm_rb_result first,result;lm_wp_result publication;HANDLE target=INVALID_HANDLE_VALUE,h;
 WCHAR root[WR_PATH],other_path[WR_PATH],slot_path[WR_PATH],move_path[WR_PATH],parent_path[WR_PATH];
 const char payload[]="bridge payload\n";char sha[65];int ok;unsigned before;
 if(argc!=3||!wr_utf8(argv[1],root,&e))return 2;
 if(!wr_prepare(&c,root,1,&e))return 3;
 if(!wr_write_new(&c,L"target.bin",payload,sizeof(payload)-1,1,&target,&e)||
    !wr_identity_get(target,0,&id,&e))return 4;
 memcpy(record.source,SOURCE_SHA,41);memset(record.run,'a',32);record.run[32]=0;
 wr_identity_text(&c.root,record.root);wr_identity_text(&c.identities[c.count-2],record.parent);
 wr_identity_text(&id,record.target);lm_sha_bytes(payload,sizeof(payload)-1,sha);memcpy(record.payload_sha,sha,65);
 wcscpy(parent_path,c.paths[c.count-2]);wr_join(&c,L"bridge-slot-00.rec",slot_path,&e);
 ck(!lm_rb_prepare(&c,target,&record,0,&refused,&e)&&!refused,"zero-slots");
 ck(!lm_rb_prepare(&c,target,&record,33,&refused,&e)&&!refused,"slot-limit");
 bad=record;bad.target[47]=bad.target[47]=='0'?'1':'0';
 ck(!lm_rb_prepare(&c,target,&bad,2,&refused,&e)&&!refused,"full-target-tail");
 bad=record;bad.payload_sha[63]=bad.payload_sha[63]=='0'?'1':'0';
 ck(!lm_rb_prepare(&c,target,&bad,2,&refused,&e)&&!refused,"payload-hash");
 before=c.entries;
 if(!lm_rb_prepare(&c,target,&record,2,&bridge,&e)){fprintf(stderr,"prepare %s\n",e.reason);return 5;}
 ck(c.entries==before+2,"reservation-entry-accounting");
 ck(c.written>=2*LM_WR_RECORD_MAX+sizeof(payload)-1,"reservation-byte-accounting");
 ck(!lm_rb_prepare(&c,target,&record,2,&refused,&e)&&!refused,"slot-collision");
 ck(!lm_rb_write_once(bridge,0,&record,&result,&e)&&!result.write_attempted,"unattached-refusal");
 if(!lm_wp_custody_prepare(&c,&custody,&e))return 6;
 swprintf(other_path,WR_PATH,L"%ls-other",root);
 if(!wr_prepare(&other,other_path,1,&e)||!lm_wp_custody_prepare(&other,&other_custody,&e))return 7;
 ck(!lm_rb_attach(bridge,other_custody,&e),"wrong-custody");
 lm_wp_custody_close(other_custody);wr_close(&other);
 ck(lm_wp_custody_identity(custody,&root_id,&parent_id,&e)&&
    wr_identity_equal(&root_id,&c.root)&&wr_identity_equal(&parent_id,&c.identities[c.count-2]),"identity-only-accessor");
 ck(!lm_wp_custody_identity(custody,&root_id,&root_id,&e),"aliased-accessor-output");
 if(!lm_rb_attach(bridge,custody,&e))return 8;
 ck(!lm_rb_attach(bridge,custody,&e),"duplicate-attach");
 wr_close(&c);
 cut(argv[2],"before");
 bad=record;bad.run[31]='b';
 ck(!lm_rb_write_once(bridge,0,&bad,&result,&e)&&!result.write_attempted,"wrong-session");
 bad=record;bad.root[47]=bad.root[47]=='0'?'1':'0';
 ck(!lm_rb_write_once(bridge,0,&bad,&result,&e)&&!result.write_attempted,"wrong-root-tail");
 bad=record;bad.phase=9;
 ck(!lm_rb_write_once(bridge,0,&bad,&result,&e)&&!result.write_attempted,"invalid-phase-format");
 ck(!lm_rb_write_once(bridge,1,&record,&result,&e)&&!result.write_attempted,"out-of-order");
 h=CreateFileW(slot_path,GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_EXISTING,0,NULL);
 ck(h==INVALID_HANDLE_VALUE,"retained-record-write-excluded");if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);
 swprintf(move_path,WR_PATH,L"%ls-moved",root);
 ck(!MoveFileExW(root,move_path,0),"root-rename-excluded");
 swprintf(move_path,WR_PATH,L"%ls\\other.rec",root);
 ck(!MoveFileExW(slot_path,move_path,0),"slot-rename-excluded");
 if(!lm_rb_write_once(bridge,0,&record,&first,&e)){fprintf(stderr,"first %s\n",e.reason);return 9;}
 ck(first.write_attempted&&first.flushed&&first.verified,"record-before-publication");
 ck(!lm_rb_write_once(bridge,0,&record,&result,&e)&&!result.write_attempted,"write-once");
 cut(argv[2],"record");
 ok=lm_wp_publish_prepared(custody,target,L"target.bin",L"published.bin",&id,sha,&publication,&e);
 ck(ok&&publication.published&&publication.verified,"publish-with-retained-records");
 if(!ok){fprintf(stderr,"publish %s\n",e.reason);return 10;}
 cut(argv[2],"published");
 next=record;next.ordinal=1;next.phase=1;
 wr_identity_text(&first.identity,next.previous_id);memcpy(next.previous_sha,first.sha,65);
 bad=next;bad.previous_id[47]=bad.previous_id[47]=='0'?'1':'0';
 ck(!lm_rb_write_once(bridge,1,&bad,&result,&e)&&!result.write_attempted,"predecessor-tail");
 bad=next;bad.previous_sha[63]=bad.previous_sha[63]=='0'?'1':'0';
 ck(!lm_rb_write_once(bridge,1,&bad,&result,&e)&&!result.write_attempted,"predecessor-sha");
 if(!lm_rb_write_once(bridge,1,&next,&result,&e)){fprintf(stderr,"second %s\n",e.reason);return 11;}
 ck(result.flushed&&result.verified,"record-after-publication");
 cut(argv[2],"after");
 ck(lm_wp_custody_check(custody,&e),"custody-still-live");
 printf("{\"source\":\"%s\",\"checks\":%u,\"failed\":%u,\"passed\":%s,\"sdk_open_attempts\":0,\"commit_acknowledged\":false,\"recovery_admission\":false}\n",SOURCE_SHA,checks,failed,failed?"false":"true");
 lm_rb_close(bridge);CloseHandle(target);lm_wp_custody_close(custody);return failed?1:0;
}
