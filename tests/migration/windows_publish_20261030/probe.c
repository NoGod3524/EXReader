/* SPDX-License-Identifier: MIT */
#include <lm_win_publish.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
static unsigned checks,failed;
static void ck(int ok,const char *name){checks++;if(!ok){failed++;fprintf(stderr,"FAIL %s native=%lu\n",name,(unsigned long)GetLastError());}}
int main(int argc,char **argv) {
 wr_context c;wr_error e={0};wr_identity id,wrong;HANDLE src=INVALID_HANDLE_VALUE,h;
 WCHAR root[WR_PATH],public_path[WR_PATH],collision[WR_PATH],moved[WR_PATH],source_path[WR_PATH];
 char sha[65],badsha[65],identity[49];lm_wp_result r;const char body[]="private-to-public complete bytes\n";
 int ok;DWORD n;void *bytes=NULL;size_t length=0;
 if(argc!=3||!wr_utf8(argv[1],root,&e))return 2;
 if(!wr_prepare(&c,root,1,&e)){fprintf(stderr,"prepare %s native=%lu\n",e.reason,(unsigned long)e.native);return 3;}
 if(!wr_write_new(&c,L"source.bin",body,sizeof(body)-1,1,&src,&e)||!wr_identity_get(src,0,&id,&e))return 4;
 lm_sha_bytes(body,sizeof(body)-1,sha);wr_identity_text(&id,identity);
 swprintf(public_path,WR_PATH,L"%ls\\published.bin",c.paths[c.count-2]);
 swprintf(collision,WR_PATH,L"%ls\\collision.bin",c.paths[c.count-2]);
 swprintf(moved,WR_PATH,L"%ls-moved",root);
 wr_join(&c,L"source.bin",source_path,&e);
 if(!strcmp(argv[2],"before")){puts("ready-before");fflush(stdout);Sleep(INFINITE);return 8;}
 if(!strcmp(argv[2],"after")){
   ok=lm_wp_publish(&c,src,L"source.bin",L"published.bin",&id,sha,&r,&e);
   if(!ok){fprintf(stderr,"publish %s native=%lu nt=%ld io=%ld\n",e.reason,(unsigned long)e.native,(long)r.ntstatus,(long)r.io_status);return 5;}
   puts("ready-after");fflush(stdout);Sleep(INFINITE);return 8;
 }
 ck(strlen(identity)==48,"full-native-identity");
 memcpy(badsha,sha,65);badsha[63]=badsha[63]=='0'?'1':'0';
 ck(!lm_wp_publish(&c,src,L"source.bin",L"published.bin",&id,badsha,&r,&e)&&!r.rename_attempted,"wrong-hash");
 wrong=id;wrong.file[15]^=1;
 ck(!lm_wp_publish(&c,src,L"source.bin",L"published.bin",&wrong,sha,&r,&e)&&!r.rename_attempted,"tail-id");
 ck(!lm_wp_publish(&c,src,L"source.bin",L"..",&id,sha,&r,&e)&&!r.rename_attempted,"dotdot");
 ck(!lm_wp_publish(&c,src,L"source.bin",L"C:\\outside",&id,sha,&r,&e)&&!r.rename_attempted,"absolute");
 ck(!lm_wp_publish(&c,src,L"missing.bin",L"published.bin",&id,sha,&r,&e)&&!r.rename_attempted,"missing-source");
 h=CreateFileW(collision,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
 ck(h!=INVALID_HANDLE_VALUE,"create-collision");
 if(h!=INVALID_HANDLE_VALUE){ck(WriteFile(h,"retain",6,&n,NULL)&&n==6,"collision-bytes");CloseHandle(h);}
 ck(!lm_wp_publish(&c,src,L"source.bin",L"collision.bin",&id,sha,&r,&e)&&!r.rename_attempted,"existing-file-refusal");
 swprintf(collision,WR_PATH,L"%ls\\collision-dir",c.paths[c.count-2]);ck(CreateDirectoryW(collision,NULL)!=0,"collision-directory-create");
 ck(!lm_wp_publish(&c,src,L"source.bin",L"collision-dir",&id,sha,&r,&e)&&!r.rename_attempted,"existing-dir-refusal");
 swprintf(collision,WR_PATH,L"%ls\\collision-link",c.paths[c.count-2]);
 ok=CreateSymbolicLinkW(collision,source_path,2)!=0;
 if(!ok)ok=CreateSymbolicLinkW(collision,source_path,0)!=0;
 ck(ok,"reparse-create");
 ck(!lm_wp_publish(&c,src,L"source.bin",L"collision-link",&id,sha,&r,&e)&&!r.rename_attempted,"reparse-refusal");
 ck((GetFileAttributesW(collision)&FILE_ATTRIBUTE_REPARSE_POINT)!=0,"reparse-retained");
 ck(!MoveFileExW(root,moved,0),"pinned-root-rename-refusal");
 swprintf(moved,WR_PATH,L"%ls\\moved.bin",root);
 ck(!MoveFileExW(source_path,moved,0),"retained-source-rename-refusal");
 ck(wr_read(src,&bytes,&length,WR_RECORD_MAX,&e)&&length==sizeof(body)-1&&!memcmp(bytes,body,length),"refusals-preserve-source");free(bytes);bytes=NULL;
 ok=lm_wp_publish(&c,src,L"source.bin",L"published.bin",&id,sha,&r,&e);
 if(!ok)fprintf(stderr,"publish %s native=%lu nt=%ld io=%ld\n",e.reason,(unsigned long)e.native,(long)r.ntstatus,(long)r.io_status);
 ck(ok&&r.rename_attempted&&r.published&&r.verified,"cross-directory-publish");
 ck(ok&&wr_identity_equal(&r.identity,&id)&&!strcmp(r.sha,sha),"full-id-and-hash");
 ck(GetFileAttributesW(source_path)==INVALID_FILE_ATTRIBUTES&&GetLastError()==ERROR_FILE_NOT_FOUND,"source-absent");
 ck(GetFileAttributesW(public_path)!=INVALID_FILE_ATTRIBUTES,"destination-present");
 ck(wr_read(src,&bytes,&length,WR_RECORD_MAX,&e)&&length==sizeof(body)-1&&!memcmp(bytes,body,length),"retained-handle-bytes");free(bytes);
 ck(!lm_wp_publish(&c,src,L"source.bin",L"published-again.bin",&id,sha,&r,&e)&&!r.rename_attempted,"no-double-publish");
 ck(wr_recheck(&c,&e),"pins-remain-live");
 printf("{\"source\":\"%s\",\"checks\":%u,\"failed\":%u,\"passed\":%s,\"identity\":\"%s\",\"sha256\":\"%s\",\"sdk_open_attempts\":0,\"recovery_admission\":false,\"full_p0_acceptance\":false}\n",SOURCE_SHA,checks,failed,failed?"false":"true",identity,sha);
 CloseHandle(src);wr_close(&c);return failed?1:0;
}
