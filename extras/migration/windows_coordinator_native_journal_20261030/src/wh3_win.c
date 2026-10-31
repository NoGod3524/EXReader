/* SPDX-License-Identifier: MIT */
#include <exr_wh3_win.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#define REC 424u
#define SEAL 360u
#define MAX_PINS 64u
typedef struct { char lines[EXR_WH_MAX_JOURNAL][EXR_WH_LINE_MAX]; size_t n; } journal;
struct wh3w_store {
 HANDLE pins[MAX_PINS],j,i; unsigned np;
 wh3w_identity ids[3],pinids[MAX_PINS];
 wh_binding b; wh_gates g; wh3w_domain d; wh3w_controls c;
 CRITICAL_SECTION lock; int locked_init,poisoned;
};
static int idof(HANDLE h,wh3w_identity *id,int directory) {
 FILE_ID_INFO f; BY_HANDLE_FILE_INFORMATION b;
 if(!GetFileInformationByHandleEx(h,FileIdInfo,&f,sizeof(f)) ||
    !GetFileInformationByHandle(h,&b))return 0;
 if((b.dwFileAttributes&FILE_ATTRIBUTE_REPARSE_POINT) ||
    !!(b.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY)!=!!directory ||
    (!directory && b.nNumberOfLinks!=1))return 0;
 id->volume=f.VolumeSerialNumber; id->file=f.FileId; return 1;
}
static int eqid(const wh3w_identity *a,const wh3w_identity *b) {
 return a->volume==b->volume && !memcmp(&a->file,&b->file,sizeof(a->file));
}
static int identities(wh3w_store *s) {
 wh3w_identity id; unsigned k;
 for(k=0;k<s->np;k++)if(!idof(s->pins[k],&id,1)||!eqid(&id,&s->pinids[k]))return 0;
 return idof(s->j,&id,0)&&eqid(&id,&s->ids[1]) &&
        idof(s->i,&id,0)&&eqid(&id,&s->ids[2]);
}
static int seekto(HANDLE h,LONGLONG n) {
 LARGE_INTEGER v; v.QuadPart=n; return SetFilePointerEx(h,v,NULL,FILE_BEGIN)!=0;
}
static int sizeis(HANDLE h,LONGLONG *n) {
 LARGE_INTEGER z; if(!GetFileSizeEx(h,&z)||z.QuadPart<0)return 0;
 *n=z.QuadPart; return 1;
}
static int rd(HANDLE h,void *p,DWORD n) {
 DWORD got=0; return ReadFile(h,p,n,&got,NULL)&&got==n;
}
static int wr(HANDLE h,const void *p,DWORD n) {
 DWORD put=0; return WriteFile(h,p,n,&put,NULL)&&put==n;
}
static void set64(unsigned char *p,uint64_t v) {
 unsigned k; for(k=0;k<8;k++){p[k]=(unsigned char)(v&255u);v>>=8;}
}
static uint64_t get64(const unsigned char *p) {
 unsigned k; uint64_t n=0; for(k=0;k<8;k++)n|=((uint64_t)p[k])<<(k*8);return n;
}
static int loadjournal(wh3w_store *s,journal *j) {
 LONGLONG z,pos=0; unsigned char len[4]; const char *p[EXR_WH_MAX_JOURNAL];
 if(!sizeis(s->j,&z)||!seekto(s->j,0))return 0;
 j->n=0;
 while(pos<z) {
  DWORD n;
  if(j->n>=EXR_WH_MAX_JOURNAL||z-pos<4||!rd(s->j,len,4))return 0;
  n=(DWORD)len[0]|((DWORD)len[1]<<8)|((DWORD)len[2]<<16)|((DWORD)len[3]<<24);
  if(!n||n>=EXR_WH_LINE_MAX||z-pos-4<(LONGLONG)n||!rd(s->j,j->lines[j->n],n))return 0;
  if(memchr(j->lines[j->n],0,n))return 0;
  j->lines[j->n][n]=0;p[j->n]=j->lines[j->n];j->n++;pos+=4+n;
 }
 return !j->n||wh_journal_check(&s->b,&s->g,p,j->n);
}
static void tipof(wh3w_store *s,const journal *j,wh3_tip *t) {
 char m[EXR_WH_LINE_MAX];
 memset(t,0,sizeof(*t));t->line_count=j->n;
 if(j->n) {
  wh_sha256_hex(j->lines[0],strlen(j->lines[0]),t->manifest_sha);
  wh_sha256_hex(j->lines[j->n-1],strlen(j->lines[j->n-1]),t->last_line_sha);
 } else {
  (void)wh_manifest(&s->b,&s->g,m);wh_sha256_hex(m,strlen(m),t->manifest_sha);
  memset(t->last_line_sha,'0',64);
 }
}
static int eqtip(const wh3_tip *a,const wh3_tip *b) {
 return a->line_count==b->line_count && !memcmp(a->manifest_sha,b->manifest_sha,65)
   && !memcmp(a->last_line_sha,b->last_line_sha,65);
}
/* Intent is an append-only canonical binary hash chain. ACK repeats BEGIN
   fields and binds its hash. Torn records and dangling BEGIN fail closed. */
static int intents(wh3w_store *s,const journal *j,uint64_t *seq,char last[65],LONGLONG *end) {
 unsigned char r[REC],begin[REC]; char hash[65],bh[65],tail[65],linehash[65];
 LONGLONG z,pos=0; int pending=0; uint64_t count=0,old=0;
 memset(last,'0',64);last[64]=0; *seq=0;
 if(!sizeis(s->i,&z)||z%(LONGLONG)REC||z>(LONGLONG)(REC*2u*EXR_WH_MAX_JOURNAL)||!seekto(s->i,0))return 0;
 memset(begin,0,sizeof(begin));memset(bh,0,sizeof(bh));
 while(pos<z) {
  if(!rd(s->i,r,REC)||memcmp(r,"WH3INT01",8)||memcmp(r+296,last,64))return 0;
  wh_sha256_hex(r,SEAL,hash);
  if(memcmp(r+SEAL,hash,64))return 0;
  if(r[8]=='B') {
   if(pending||get64(r+16)!=*seq+1)return 0;
   old=get64(r+24);
   if(old>=j->n||old>=EXR_WH_MAX_JOURNAL||get64(r+32)!=strlen(j->lines[(size_t)old]))return 0;
   wh_sha256_hex(j->lines[(size_t)old],strlen(j->lines[(size_t)old]),linehash);
   if(old)wh_sha256_hex(j->lines[(size_t)old-1],strlen(j->lines[(size_t)old-1]),tail);
   else {memset(tail,'0',64);tail[64]=0;}
   if(memcmp(r+104,tail,64)||memcmp(r+168,linehash,64))return 0;
   wh_sha256_hex(j->lines[0],strlen(j->lines[0]),linehash);
   if(memcmp(r+40,linehash,64))return 0;
   memcpy(begin,r,REC);memcpy(bh,hash,65);pending=1;
  } else if(r[8]=='A') {
   if(!pending||get64(r+16)!=get64(begin+16)||memcmp(r+24,begin+24,208)||memcmp(r+232,bh,64))return 0;
   *seq=get64(r+16);count=old+1;pending=0;
  } else return 0;
  memcpy(last,hash,65);pos+=REC;
 }
 if(pending||(z&&count!=j->n))return 0;
 *end=z;return 1;
}
static void phase(wh3w_store *s,unsigned n) {if(s->c.phase)s->c.phase(s->c.context,n);}
void wh3w_close(wh3w_store *s) {
 unsigned k;if(!s)return;
 if(s->j!=INVALID_HANDLE_VALUE)CloseHandle(s->j);
 if(s->i!=INVALID_HANDLE_VALUE)CloseHandle(s->i);
 for(k=0;k<s->np;k++)CloseHandle(s->pins[k]);
 if(s->locked_init)DeleteCriticalSection(&s->lock);
 free(s);
}
int wh3w_open(const wchar_t *root,const wh3w_identity ids[3],const wh_binding *b,
 const wh_gates *g,const wh3w_domain *d,const wh3w_controls *c,wh3w_store **out) {
 wh3w_store *s; wchar_t full[MAX_PATH],part[MAX_PATH],leaf[MAX_PATH],drive[4],fs[32];
 size_t len,k; wh3w_identity id; DWORD n; char manifest[EXR_WH_LINE_MAX];
 if(out)*out=NULL;
 if(!out||!root||!ids||!b||!g||!d||!d->enter||!d->validate||!d->poison||!d->leave)return 0;
 if(!wh_manifest(b,g,manifest))return 0;
 len=wcslen(root);if(len<3||len>MAX_PATH-32||root[1]!=L':'||root[2]!=L'\\'||wcschr(root+2,L':'))return 0;
 n=GetFullPathNameW(root,MAX_PATH,full,NULL);
 if(!n||n>=MAX_PATH||_wcsicmp(root,full)||full[len-1]==L'\\')return 0;
 drive[0]=full[0];drive[1]=L':';drive[2]=L'\\';drive[3]=0;
 if(GetDriveTypeW(drive)!=DRIVE_FIXED||!GetVolumeInformationW(drive,NULL,0,NULL,NULL,NULL,fs,32)||_wcsicmp(fs,L"NTFS"))return 0;
 s=calloc(1,sizeof(*s));if(!s)return 0;
 s->j=s->i=INVALID_HANDLE_VALUE;s->b=*b;s->g=*g;s->d=*d;if(c)s->c=*c;memcpy(s->ids,ids,sizeof(s->ids));
 InitializeCriticalSection(&s->lock);s->locked_init=1;
 for(k=3;k<=len;k++)if(k==3||k==len||full[k]==L'\\') {
  HANDLE h;
  if(s->np>=MAX_PINS)goto fail;
  memcpy(part,full,k*sizeof(wchar_t));part[k]=0;
  h=CreateFileW(part,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)goto fail;
  s->pins[s->np]=h;
  if(!idof(h,&s->pinids[s->np],1)){s->np++;goto fail;}s->np++;
 }
 if(!s->np||!eqid(&s->pinids[s->np-1],&ids[0])||eqid(&ids[1],&ids[2]))goto fail;
 swprintf_s(leaf,MAX_PATH,L"%ls\\journal.bin",full);
 s->j=CreateFileW(leaf,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 swprintf_s(leaf,MAX_PATH,L"%ls\\intent.bin",full);
 s->i=CreateFileW(leaf,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(s->j==INVALID_HANDLE_VALUE||s->i==INVALID_HANDLE_VALUE||!identities(s))goto fail;
 /* Reopen every pinned path read-only and compare after the whole chain is pinned. */
 for(k=0;k<s->np;k++) {
  DWORD z=GetFinalPathNameByHandleW(s->pins[k],part,MAX_PATH,FILE_NAME_NORMALIZED);
  HANDLE h;if(!z||z>=MAX_PATH)goto fail;
  h=CreateFileW(part,FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
       FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)goto fail;
  n=(DWORD)(idof(h,&id,1)&&eqid(&id,&s->pinids[k]));CloseHandle(h);if(!n)goto fail;
 }
 *out=s;return 1;
fail:wh3w_close(s);return 0;
}
wh3_tx_status wh3w_append(void *ctx,void *cap,const wh3_tip *expected,const char *line,wh3_tip *after) {
 wh3w_store *s=ctx; journal *j=NULL,*verify=NULL; wh3_tip tip;
 void *guard=NULL; const char *p[EXR_WH_MAX_JOURNAL];
 unsigned char rec[REC],frame[EXR_WH_LINE_MAX+4];char last[65],hash[65],beginhash[65];
 size_t n,k;uint64_t seq;LONGLONG end,jend;wh3_tx_status result=WH3_TX_MISMATCH;int entered=0;
 if(!s||!cap||!expected||!line||!after)return result;
 EnterCriticalSection(&s->lock);
 if(s