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
 wchar_t paths[MAX_PINS][MAX_PATH];
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
 for(k=0;k<s->np;k++) {
  HANDLE h; int same;
  if(!idof(s->pins[k],&id,1)||!eqid(&id,&s->pinids[k]))return 0;
  /* Recheck the original input prefix, not a path derived from the handle. */
  h=CreateFileW(s->paths[k],FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,
     NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)return 0;
  same=idof(h,&id,1)&&eqid(&id,&s->pinids[k]);CloseHandle(h);
  if(!same)return 0;
 }
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
static int loadjournal(wh3w_store *s,HANDLE h,journal *j) {
 LONGLONG z,pos=0; unsigned char len[4]; const char *p[EXR_WH_MAX_JOURNAL];
 if(!sizeis(h,&z)||!seekto(h,0))return 0;
 j->n=0;
 while(pos<z) {
  DWORD n;
  if(j->n>=EXR_WH_MAX_JOURNAL||z-pos<4||!rd(h,len,4))return 0;
  n=(DWORD)len[0]|((DWORD)len[1]<<8)|((DWORD)len[2]<<16)|((DWORD)len[3]<<24);
  if(!n||n>=EXR_WH_LINE_MAX||z-pos-4<(LONGLONG)n||!rd(h,j->lines[j->n],n))return 0;
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
static int intents(HANDLE h,const journal *j,uint64_t *seq,char last[65],LONGLONG *end) {
 unsigned char r[REC],begin[REC],zero[64]={0}; char hash[65],bh[65],tail[65],linehash[65];
 LONGLONG z,pos=0; int pending=0; uint64_t count=0,old=0;
 memset(last,'0',64);last[64]=0; *seq=0;
 if(!sizeis(h,&z)||z%(LONGLONG)REC||z>(LONGLONG)(REC*2u*EXR_WH_MAX_JOURNAL)||!seekto(h,0))return 0;
 memset(begin,0,sizeof(begin));memset(bh,0,sizeof(bh));
 while(pos<z) {
  if(!rd(h,r,REC)||memcmp(r,"WH3INT01",8)||memcmp(r+9,zero,7)||memcmp(r+296,last,64))return 0;
  wh_sha256_hex(r,SEAL,hash);
  if(memcmp(r+SEAL,hash,64))return 0;
  if(r[8]=='B') {
   if(pending||get64(r+16)!=*seq+1||memcmp(r+232,zero,64))return 0;
   old=get64(r+24);
   if(old!=count||old>=j->n||old>=EXR_WH_MAX_JOURNAL||get64(r+32)!=strlen(j->lines[(size_t)old]))return 0;
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
 if(pending||count!=j->n)return 0;
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
 size_t len,k; DWORD n; char manifest[EXR_WH_LINE_MAX],last[65];
 journal *j=NULL; uint64_t seq; LONGLONG end;
 if(out)*out=NULL;
 if(!out||!root||!ids||!b||!g||!d||!d->enter||!d->validate||!d->poison||!d->leave)return 0;
 if(!wh_manifest(b,g,manifest))return 0;
 len=wcslen(root);if(len<4||len>MAX_PATH-32||root[1]!=L':'||root[2]!=L'\\'||wcschr(root+2,L':'))return 0;
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
  /* FILE_LIST_DIRECTORY participates in share checks; attributes alone do not. */
  h=CreateFileW(part,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)goto fail;
  s->pins[s->np]=h;wcscpy_s(s->paths[s->np],MAX_PATH,part);
  if(!idof(h,&s->pinids[s->np],1)){s->np++;goto fail;}s->np++;
  phase(s,WH3W_PINNED_BASE+s->np);
 }
 if(!s->np||!eqid(&s->pinids[s->np-1],&ids[0])||eqid(&ids[1],&ids[2])
    ||ids[0].volume!=ids[1].volume||ids[0].volume!=ids[2].volume)goto fail;
 swprintf_s(leaf,MAX_PATH,L"%ls\\journal.bin",full);
 s->j=CreateFileW(leaf,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
 swprintf_s(leaf,MAX_PATH,L"%ls\\intent.bin",full);
 s->i=CreateFileW(leaf,GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
 if(s->j==INVALID_HANDLE_VALUE||s->i==INVALID_HANDLE_VALUE||!identities(s))goto fail;
 j=malloc(sizeof(*j));
 if(!j||!loadjournal(s,s->j,j)||!intents(s->i,j,&seq,last,&end)||!identities(s))goto fail;
 free(j);*out=s;return 1;
fail:free(j);wh3w_close(s);return 0;
}
/* The readback uses a separately opened handle and verifies its file identity. */
static HANDLE readback_handle(wh3w_store *s,unsigned which) {
 wchar_t path[MAX_PATH]; HANDLE h; wh3w_identity id;
 swprintf_s(path,MAX_PATH,L"%ls\\%ls",s->paths[s->np-1],which==1?L"journal.bin":L"intent.bin");
 h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
               FILE_FLAG_OPEN_REPARSE_POINT,NULL);
 if(h!=INVALID_HANDLE_VALUE&&(!idof(h,&id,0)||!eqid(&id,&s->ids[which]))) {
  CloseHandle(h);h=INVALID_HANDLE_VALUE;
 }
 return h;
}
static int write_part(wh3w_store *s,HANDLE h,const void *p,DWORD n,unsigned at) {
 if(s->c.fault==WH3W_SHORT_WRITE&&(!s->c.fault_phase||s->c.fault_phase==at)) {
  if(n>1)(void)wr(h,p,n-1);
  return 0;
 }
 return wr(h,p,n);
}
static int flush_at(wh3w_store *s,HANDLE h,unsigned at) {
 if(s->c.fault==WH3W_FLUSH_FAIL&&(!s->c.fault_phase||s->c.fault_phase==at))return 0;
 return FlushFileBuffers(h)!=0;
}
static int live(wh3w_store *s,void *guard) {
 return s->d.validate(s->d.context,guard)&&identities(s);
}
static void poison(wh3w_store *s,void *guard) {
 LONGLONG end; const unsigned char marker=0xff;
 s->poisoned=1;
 /* Best effort sticky malformed suffix. An I/O failure cannot promise this
    write is durable: the domain must already hold a persistent pending gate. */
 if(sizeis(s->i,&end)&&seekto(s->i,end)&&wr(s->i,&marker,1))
  (void)FlushFileBuffers(s->i);
 s->d.poison(s->d.context,guard,"native-journal-uncertain");
}
wh3_tx_status wh3w_append(void *ctx,void *cap,const wh3_tip *expected,const char *line,wh3_tip *after) {
 wh3w_store *s=ctx; journal *j=NULL,*verify=NULL; wh3_tip tip;
 void *guard=NULL; const char *p[EXR_WH_MAX_JOURNAL];
 unsigned char rec[REC],frame[EXR_WH_LINE_MAX+4];char last[65],hash[65],beginhash[65];
 size_t n,k;uint64_t seq;LONGLONG end,jend;wh3_tx_status result=WH3_TX_MISMATCH;int entered=0;
 if(!s||!cap||!expected||!line||!after)return result;
 EnterCriticalSection(&s->lock);
 if(s->poisoned){result=WH3_TX_UNCERTAIN;goto done;}
 if(!s->d.enter(s->d.context,cap,&s->b,&guard))goto done;
 entered=1;
 if(!guard||!live(s,guard))goto done;
 j=malloc(sizeof(*j));verify=malloc(sizeof(*verify));
 if(!j||!verify){result=WH3_TX_UNCERTAIN;goto done;}
 if(!loadjournal(s,s->j,j)||!intents(s->i,j,&seq,last,&end))goto done;
 tipof(s,j,&tip);
 if(!eqtip(expected,&tip)||j->n>=EXR_WH_MAX_JOURNAL)goto done;
 for(n=0;n<EXR_WH_LINE_MAX&&line[n];n++){}
 if(!n||n>=EXR_WH_LINE_MAX)goto done;
 for(k=0;k<j->n;k++)p[k]=j->lines[k];
 p[j->n]=line;
 if(!wh_journal_check(&s->b,&s->g,p,j->n+1)||!sizeis(s->j,&jend))goto done;
 phase(s,WH3W_PRE_BEGIN);
 if(!live(s,guard))goto done;
 memset(rec,0,sizeof(rec));memcpy(rec,"WH3INT01",8);rec[8]='B';
 set64(rec+16,seq+1);set64(rec+24,j->n);set64(rec+32,n);
 memcpy(rec+40,tip.manifest_sha,64);memcpy(rec+104,tip.last_line_sha,64);
 wh_sha256_hex(line,n,hash);memcpy(rec+168,hash,64);
 memcpy(rec+296,last,64);wh_sha256_hex(rec,SEAL,beginhash);memcpy(rec+SEAL,beginhash,64);
 result=WH3_TX_UNCERTAIN;
 /* From this point every failure retains uncertainty, including a zero-byte
    failed write. No return of MISMATCH can follow an attempted BEGIN. */
 if(!seekto(s->i,end)||!seekto(s->j,jend))goto uncertain;
 if(!write_part(s,s->i,rec,REC/2,WH3W_BEGIN_PARTIAL))goto uncertain;
 phase(s,WH3W_BEGIN_PARTIAL);
 if(!live(s,guard)||!wr(s->i,rec+REC/2,REC-REC/2)
    ||!flush_at(s,s->i,WH3W_BEGIN_FLUSHED))goto uncertain;
 phase(s,WH3W_BEGIN_FLUSHED);
 if(!live(s,guard))goto uncertain;
 frame[0]=(unsigned char)n;frame[1]=(unsigned char)(n>>8);
 frame[2]=(unsigned char)(n>>16);frame[3]=(unsigned char)(n>>24);
 memcpy(frame+4,line,n);
 if(!write_part(s,s->j,frame,2,WH3W_JOURNAL_HEADER_PARTIAL))goto uncertain;
 phase(s,WH3W_JOURNAL_HEADER_PARTIAL);
 if(!live(s,guard)||!wr(s->j,frame+2,2))goto uncertain;
 k=n/2;
 if(!write_part(s,s->j,frame+4,(DWORD)k,WH3W_JOURNAL_BODY_PARTIAL))goto uncertain;
 phase(s,WH3W_JOURNAL_BODY_PARTIAL);
 if(!live(s,guard)||!wr(s->j,frame+4+k,(DWORD)(n-k)))goto uncertain;
 phase(s,WH3W_JOURNAL_WRITTEN);
 if(!live(s,guard)||!flush_at(s,s->j,WH3W_JOURNAL_FLUSHED))goto uncertain;
 phase(s,WH3W_JOURNAL_FLUSHED);
 if(!live(s,guard)||s->c.fault==WH3W_READBACK_FAIL)goto uncertain;
 {
  HANDLE h=readback_handle(s,1);int ok;
  if(h==INVALID_HANDLE_VALUE)goto uncertain;
  ok=loadjournal(s,h,verify);CloseHandle(h);
  if(!ok||verify->n!=j->n+1)goto uncertain;
 }
 for(k=0;k<j->n;k++)if(strcmp(j->lines[k],verify->lines[k]))goto uncertain;
 if(strcmp(line,verify->lines[j->n]))goto uncertain;
 tipof(s,verify,&tip);
 rec[8]='A';memcpy(rec+232,beginhash,64);memcpy(rec+296,beginhash,64);
 wh_sha256_hex(rec,SEAL,hash);memcpy(rec+SEAL,hash,64);
 if(!live(s,guard)||!write_part(s,s->i,rec,REC/2,WH3W_ACK_PARTIAL))goto uncertain;
 phase(s,WH3W_ACK_PARTIAL);
 if(!live(s,guard)||!wr(s->i,rec+REC/2,REC-REC/2))goto uncertain;
 phase(s,WH3W_ACK_WRITTEN);
 if(!live(s,guard)||!flush_at(s,s->i,WH3W_ACK_FLUSHED))goto uncertain;
 {
  HANDLE h=readback_handle(s,2);uint64_t checked;LONGLONG bytes;int ok;
  if(h==INVALID_HANDLE_VALUE)goto uncertain;
  ok=intents(h,verify,&checked,last,&bytes);CloseHandle(h);
  if(!ok||checked!=seq+1||bytes!=end+2*REC||memcmp(last,hash,65))goto uncertain;
 }
 if(!live(s,guard))goto uncertain;
 phase(s,WH3W_ACK_FLUSHED);
 if(!live(s,guard))goto uncertain;
 *after=tip;result=WH3_TX_OK;goto done;
uncertain:poison(s,guard);
done:
 free(j);free(verify);
 if(entered)s->d.leave(s->d.context,guard);
 LeaveCriticalSection(&s->lock);
 return result;
}
