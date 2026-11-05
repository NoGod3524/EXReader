/* SPDX-License-Identifier: MIT */
#ifndef LM_WE_BOUNDARY_H
#define LM_WE_BOUNDARY_H
/* Engine-private process-lifetime ownership. No release/reset after quarantine.
 * The caller may close its handles: duplicated root pins remain owned here. */
typedef struct {
 HANDLE root[WR_PINS],ancestors[WR_PINS];
 unsigned roots,parents;
 HANDLE retained[9];
 WCHAR worker[WR_PATH];
} lm_we_custody;
static volatile LONG lm_we_gate;
static lm_we_custody *lm_we_quarantine;
static int lm_we_expired(ULONGLONG deadline,wr_error *e){
 if(GetTickCount64()>=deadline){SetLastError(ERROR_TIMEOUT);fail(e,"observer-final-deadline");return 1;}return 0;
}
static void lm_we_custody_close(lm_we_custody *c){
 unsigned i;if(!c)return;
 for(i=0;i<c->roots;i++)CloseHandle(c->root[i]);
 for(i=0;i<c->parents;i++)CloseHandle(c->ancestors[i]);
 free(c);
}
static int lm_we_pin_worker(lm_we_custody *c,wr_context *root,HANDLE image,wr_error *e){
 DWORD n;unsigned i;size_t start,len;WCHAR prefix[WR_PATH];HANDLE check;wr_identity a,b;
 for(i=0;i<root->count;i++){
  if(!DuplicateHandle(GetCurrentProcess(),root->pins[i],GetCurrentProcess(),&c->root[c->roots],0,FALSE,DUPLICATE_SAME_ACCESS))return fail(e,"observer-root-duplicate");
  c->roots++;
 }
 n=GetFinalPathNameByHandleW(image,c->worker,WR_PATH,FILE_NAME_NORMALIZED|VOLUME_NAME_GUID);
 if(!n||n>=WR_PATH||wcsncmp(c->worker,L"\\\\?\\Volume{",11))return fail(e,"observer-worker-volume-path");
 len=wcslen(c->worker);start=0;
 while(start<len&&c->worker[start]!=L'}')start++;
 if(start+1>=len||c->worker[start+1]!=L'\\')return fail(e,"observer-worker-volume-root");
 for(i=(unsigned)(start+1);i<len;i++){
  if(c->worker[i]!=L'\\')continue;
  if(c->parents==WR_PINS)return fail(e,"observer-worker-depth");
  memcpy(prefix,c->worker,(i+1)*sizeof(WCHAR));prefix[i+1]=0;if(i>start+1)prefix[i]=0;
  check=CreateFileW(prefix,FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(check==INVALID_HANDLE_VALUE)return fail(e,"observer-worker-parent-pin");
  c->ancestors[c->parents++]=check;
  if(!wr_identity_get(check,1,&a,e))return 0;
 }
 check=CreateFileW(c->worker,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(check==INVALID_HANDLE_VALUE)return fail(e,"observer-worker-bound-open");
 n=wr_identity_get(image,0,&a,e)&&wr_identity_get(check,0,&b,e)&&wr_identity_equal(&a,&b);
 CloseHandle(check);
 if(!n)return fail(e,"observer-worker-bound-identity");
 return 1;
}
#endif
