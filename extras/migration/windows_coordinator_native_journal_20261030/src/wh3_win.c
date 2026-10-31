/* SPDX-License-Identifier: MIT */
#include <exr_wh3_win.h>
#include <stdint.h>
#include <stdio.h>
#include <limits.h>
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
 CRITICAL_SECTION lock; int locked_init,poisoned,domain_retained;
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
/* Observational read only. The complete native pair is revalidated under the
   same storage lock; no newer tip is substituted into a caller's transaction. */
int wh3w_read(wh3w_store *s,char (*lines)[EXR_WH_LINE_MAX],size_t capacity,
 size_t *count,wh3_tip *tip) {
 journal *j=NULL;uint64_t seq;char seal[65];LONGLONG bytes;int ok=0;
 if(count)*count=0;if(tip)memset(tip,0,sizeof(*tip));
 if(!s||!lines||!count||!tip||capacity>EXR_WH_MAX_JOURNAL)return 0;
 EnterCriticalSection(&s->lock);j=malloc(sizeof(*j));
 if(j&&!s->poisoned&&identities(s)&&loadjournal(s,s->j,j)&&j->n<=capacity&&
    intents(s->i,j,&seq,seal,&bytes)&&identities(s)){
  size_t k;memset(lines,0,j->n*sizeof(j->lines[0]));
  for(k=0;k<j->n;k++)memcpy(lines[k],j->lines[k],strlen(j->lines[k])+1);
  *count=j->n;tipof(s,j,tip);ok=1;
 }
 free(j);LeaveCriticalSection(&s->lock);return ok;
}
static void phase(wh3w_store *s,unsigned n) {if(s->c.phase)s->c.phase(s->c.context,n);}
void wh3w_close(wh3w_store *s) {
 unsigned k;if(!s)return;
 if(s->j!=INVALID_HANDLE_VALUE)CloseHandle(s->j);
 if(s->i!=INVALID_HANDLE_VALUE)CloseHandle(s->i);
 for(k=0;k<s->np;k++)CloseHandle(s->pins[k]);
 if(s->locked_init)DeleteCriticalSection(&s->lock);
 if(s->domain_retained)s->d.release(s->d.context);
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
 if(!!d->retain!=!!d->release)goto fail;
 if(d->retain){if(!d->retain(d->context))goto fail;s->domain_retained=1;}
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


/* Persistent, append-only admission gate. It deliberately uses a separate
   object from the frozen C01 lease: C01 header drift cannot erase this intent. */
#define GREC 344u
#define GSEAL 280u
#define GMAX 256u
struct wh3wg_gate {
 HANDLE file,pins[MAX_PINS];unsigned np,mode,borrows,clients;int initialized,active,poisoned;
 wchar_t paths[MAX_PINS][MAX_PATH],leaf[MAX_PATH];
 wh3w_identity ids[2],pinids[MAX_PINS];
 char domain[49],manifest[65],seal[65],previous_clean[65];uint64_t sequence,generation;
 wh3wg_grant trusted;
 unsigned char state;LONGLONG bytes;wh_binding binding;
 wh3w_controls controls;CRITICAL_SECTION lock;
};
static int ghx(const char *p,size_t n) {
 size_t k;if(!p)return 0;
 for(k=0;k<n;k++)if(!((p[k]>='0'&&p[k]<='9')||(p[k]>='a'&&p[k]<='f')))return 0;
 return p[n]==0;
}
static int gidentity(wh3wg_gate *g) {
 unsigned k;wh3w_identity id;
 for(k=0;k<g->np;k++){
  HANDLE h;int same;
  if(!idof(g->pins[k],&id,1)||!eqid(&id,&g->pinids[k]))return 0;
  h=CreateFileW(g->paths[k],FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE,
     NULL,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)return 0;
  same=idof(h,&id,1)&&eqid(&id,&g->pinids[k]);CloseHandle(h);
  if(!same)return 0;
 }
 return idof(g->file,&id,0)&&eqid(&id,&g->ids[1]);
}
static int gload(wh3wg_gate *g,int adopt) {
 unsigned char r[GREC],last_state=0,zero[64]={0};char previous[65],hash[65],manifest[65],before_begin[65]={0};
 uint64_t seq=0,gen=0,count=0;LONGLONG size,pos;
 memset(previous,'0',64);previous[64]=0;memset(manifest,'0',64);manifest[64]=0;
 if(!gidentity(g)||!sizeis(g->file,&size)||!size||size%(LONGLONG)GREC
    ||size>(LONGLONG)(GREC*GMAX)||!seekto(g->file,0))return 0;
 for(pos=0;pos<size;pos+=GREC){
  uint64_t next;
  if(!rd(g->file,r,GREC)||memcmp(r,"WH3GATE1",8)||memcmp(r+9,zero,7)
     ||get64(r+16)!=seq+1||memcmp(r+32,g->domain,48)||memcmp(r+216,previous,64))return 0;
  wh_sha256_hex(r,GSEAL,hash);if(memcmp(hash,r+GSEAL,64))return 0;
  next=get64(r+24);
  if(!seq){
   if(r[8]!='I'||next||get64(r+144)||memcmp(r+80,manifest,64)||memcmp(r+152,previous,64))return 0;
  }else if(r[8]=='B'){
   if(last_state=='B'||gen==UINT64_MAX||next!=gen+1||get64(r+144)>EXR_WH_MAX_JOURNAL)return 0;
   memcpy(before_begin,previous,65);
   memcpy(manifest,r+80,64);manifest[64]=0;
   if(!ghx(manifest,64))return 0;
   count=get64(r+144);
  }else if(r[8]=='C'){
   if(last_state!='B'||next!=gen||memcmp(r+80,manifest,64)||get64(r+144)<count||get64(r+144)>EXR_WH_MAX_JOURNAL)return 0;
  }else return 0;
  {char tip[65];memcpy(tip,r+152,64);tip[64]=0;if(!ghx(tip,64))return 0;}
  seq++;gen=next;last_state=r[8];memcpy(previous,hash,65);
 }
 if(!gidentity(g))return 0;
 if(adopt){
  g->sequence=seq;g->generation=gen;g->state=last_state;g->bytes=size;
  memcpy(g->seal,previous,65);memcpy(g->manifest,manifest,65);
  memcpy(g->previous_clean,before_begin,65);return 1;
 }
 return seq==g->sequence&&gen==g->generation&&last_state==g->state&&size==g->bytes
   &&!memcmp(previous,g->seal,65)&&!memcmp(manifest,g->manifest,65);
}
static void gphase(wh3wg_gate *g,unsigned at) {
 if(g->controls.phase)g->controls.phase(g->controls.context,at);
}
static int grecord(wh3wg_gate *g,unsigned char state,uint64_t generation,
                   const wh3_tip *tip,unsigned at) {
 unsigned char r[GREC];char seal[65];LONGLONG size;DWORD put=0;
 if(g->poisoned||g->sequence>=GMAX||!gidentity(g)||!sizeis(g->file,&size)
    ||size!=g->bytes||!seekto(g->file,size))return 0;
 memset(r,0,sizeof(r));memcpy(r,"WH3GATE1",8);r[8]=state;
 set64(r+16,g->sequence+1);set64(r+24,generation);memcpy(r+32,g->domain,48);
 memcpy(r+80,tip->manifest_sha,64);set64(r+144,tip->line_count);
 memcpy(r+152,tip->last_line_sha,64);memcpy(r+216,g->seal,64);
 wh_sha256_hex(r,GSEAL,seal);memcpy(r+GSEAL,seal,64);
 /* Every attempted record failure poisons this holder. Old trusted generation
    remains unchanged: visible unacknowledged CLEAN cannot be auto-adopted. */
 if(g->controls.fault==WH3W_SHORT_WRITE&&g->controls.fault_phase==at){
  (void)WriteFile(g->file,r,GREC-1,&put,NULL);g->poisoned=1;return 0;
 }
 if(!wr(g->file,r,GREC)){g->poisoned=1;return 0;}
 gphase(g,at);
 if((g->controls.fault==WH3W_FLUSH_FAIL&&g->controls.fault_phase==at)
    ||!FlushFileBuffers(g->file)){g->poisoned=1;return 0;}
 if(g->controls.fault==WH3W_READBACK_FAIL&&g->controls.fault_phase==at){
  g->poisoned=1;return 0;
 }
 if(!gload(g,1)||g->state!=state||g->generation!=generation||memcmp(g->seal,seal,65)){
  g->poisoned=1;return 0;
 }
 gphase(g,at+1);return 1;
}
int wh3wg_close(wh3wg_gate *g) {
 unsigned k;if(!g)return 1;
 EnterCriticalSection(&g->lock);
 if(g->borrows||g->clients){LeaveCriticalSection(&g->lock);return 0;}
 if(g->file!=INVALID_HANDLE_VALUE)CloseHandle(g->file);
 for(k=0;k<g->np;k++)CloseHandle(g->pins[k]);
 LeaveCriticalSection(&g->lock);DeleteCriticalSection(&g->lock);free(g);return 1;
}
int wh3wg_open(const wchar_t *root,const wh3w_identity ids[2],const char domain[49],
 const wh3wg_grant *trusted,unsigned mode,const wh3w_controls *controls,wh3wg_gate **out) {
 wh3wg_gate *g;wchar_t full[MAX_PATH],part[MAX_PATH],drive[4],fs[32];
 size_t len,k;DWORD n,access;OVERLAPPED ov;LONGLONG size;
 if(out)*out=NULL;
 if(!out||!root||!ids||!ghx(domain,48)||mode<WH3WG_SHARED||mode>WH3WG_RECOVER)return 0;
 if(mode!=WH3WG_ENROLL&&(!trusted||!ghx(trusted->seal,64)))return 0;
 len=wcslen(root);
 if(len<4||len>MAX_PATH-32||root[1]!=L':'||root[2]!=L'\\'||wcschr(root+2,L':'))return 0;
 n=GetFullPathNameW(root,MAX_PATH,full,NULL);
 if(!n||n>=MAX_PATH||_wcsicmp(root,full)||full[len-1]==L'\\')return 0;
 drive[0]=full[0];drive[1]=L':';drive[2]=L'\\';drive[3]=0;
 if(GetDriveTypeW(drive)!=DRIVE_FIXED||!GetVolumeInformationW(drive,NULL,0,NULL,NULL,NULL,fs,32)||_wcsicmp(fs,L"NTFS"))return 0;
 g=calloc(1,sizeof(*g));if(!g)return 0;
 InitializeCriticalSection(&g->lock);g->file=INVALID_HANDLE_VALUE;g->mode=mode;if(trusted)g->trusted=*trusted;
 memcpy(g->ids,ids,sizeof(g->ids));memcpy(g->domain,domain,49);if(controls)g->controls=*controls;
 memset(g->seal,'0',64);g->seal[64]=0;
 for(k=3;k<=len;k++)if(k==3||k==len||full[k]==L'\\'){
  HANDLE h;if(g->np>=MAX_PINS)goto fail;
  memcpy(part,full,k*sizeof(wchar_t));part[k]=0;
  h=CreateFileW(part,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES,FILE_SHARE_READ,NULL,OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT,NULL);
  if(h==INVALID_HANDLE_VALUE)goto fail;
  g->pins[g->np]=h;wcscpy_s(g->paths[g->np],MAX_PATH,part);
  if(!idof(h,&g->pinids[g->np],1)){g->np++;goto fail;}g->np++;
 }
 if(!g->np||!eqid(&g->pinids[g->np-1],&ids[0])||ids[0].volume!=ids[1].volume)goto fail;
 swprintf_s(g->leaf,MAX_PATH,L"%ls\\admission.bin",full);
 access=GENERIC_READ|(mode==WH3WG_SHARED?0:GENERIC_WRITE);
 g->file=CreateFileW(g->leaf,access,FILE_SHARE_READ|FILE_SHARE_WRITE,NULL,OPEN_EXISTING,
   FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_WRITE_THROUGH,NULL);
 if(g->file==INVALID_HANDLE_VALUE||!gidentity(g))goto fail;
 memset(&ov,0,sizeof(ov));
 if(!LockFileEx(g->file,LOCKFILE_FAIL_IMMEDIATELY|(mode==WH3WG_SHARED?0:LOCKFILE_EXCLUSIVE_LOCK),
    0,MAXDWORD,0,&ov))goto fail;
 if(mode==WH3WG_ENROLL){
  if(trusted||!sizeis(g->file,&size)||size)goto fail;
 }else{
  if(!gload(g,1))goto fail;
  if(mode==WH3WG_RECOVER){
   int current=g->state!='B'&&g->generation==trusted->generation&&!memcmp(g->seal,trusted->seal,65);
   int pending=trusted->generation!=UINT64_MAX&&g->generation==trusted->generation+1
       &&!memcmp(g->previous_clean,trusted->seal,65);
   if(!current&&!pending)goto fail;
  }else if(g->state=='B'||g->generation!=trusted->generation||memcmp(g->seal,trusted->seal,65))goto fail;
  g->initialized=1;
 }
 *out=g;return 1;
fail:(void)wh3wg_close(g);return 0;
}
int wh3wg_enroll(wh3wg_gate *g,wh3wg_grant *grant) {
 wh3_tip zero;int ok;
 if(!g||!grant)return 0;EnterCriticalSection(&g->lock);
 memset(&zero,0,sizeof(zero));memset(zero.manifest_sha,'0',64);memset(zero.last_line_sha,'0',64);
 ok=g->mode==WH3WG_ENROLL&&!g->initialized&&!g->sequence&&grecord(g,'I',0,&zero,0);
 if(ok){g->initialized=1;g->mode=WH3WG_OWNER;
  grant->generation=0;memcpy(grant->seal,g->seal,65);g->trusted=*grant;}
 LeaveCriticalSection(&g->lock);return ok;
}
int wh3wg_check(wh3wg_gate *g) {
 int ok;if(!g)return 0;EnterCriticalSection(&g->lock);
 ok=g->initialized&&!g->poisoned&&gload(g,0);
 LeaveCriticalSection(&g->lock);return ok;
}
uint64_t wh3wg_generation(const wh3wg_gate *g) {return g?g->generation:0;}
static int gbinding(wh3wg_gate *g,const wh_binding *b,const wh_gates *gates,const wh3_tip *tip) {
 char manifest[EXR_WH_LINE_MAX],hash[65];
 if(!b||!gates||!tip||!ghx(tip->manifest_sha,64)||!ghx(tip->last_line_sha,64)
    ||tip->line_count>EXR_WH_MAX_JOURNAL||!wh_manifest(b,gates,manifest))return 0;
 wh_sha256_hex(manifest,strlen(manifest),hash);
 return !memcmp(hash,tip->manifest_sha,65)&&(!g->active||!memcmp(&g->binding,b,sizeof(*b)));
}
int wh3wg_begin(wh3wg_gate *g,const wh_binding *b,const wh_gates *gates,
 const wh3_tip *base,void **cap) {
 int ok=0;if(cap)*cap=NULL;if(!g||!cap)return 0;EnterCriticalSection(&g->lock);
 if(g->mode==WH3WG_OWNER&&!g->active&&!g->borrows&&g->generation!=UINT64_MAX
    &&g->state!='B'&&wh3wg_check(g)&&gbinding(g,b,gates,base)
    &&grecord(g,'B',g->generation+1,base,WH3WG_BEGIN_WRITTEN)){
  g->binding=*b;g->active=1;*cap=g;ok=1;
 }
 LeaveCriticalSection(&g->lock);return ok;
}
static int genter(void *context,void *cap,const wh_binding *b,void **guard) {
 wh3wg_gate *g=context;int ok=0;if(guard)*guard=NULL;
 if(!g||!guard||!b)return 0;EnterCriticalSection(&g->lock);
 if(cap==g&&g->active&&g->state=='B'&&!memcmp(b,&g->binding,sizeof(*b))
    &&g->borrows<UINT_MAX&&wh3wg_check(g)){g->borrows++;*guard=g;ok=1;}
 LeaveCriticalSection(&g->lock);return ok;
}
static int gvalid(void *context,void *guard) {
 wh3wg_gate *g=context;int ok;if(!g)return 0;EnterCriticalSection(&g->lock);
 ok=guard==g&&g->borrows&&g->active&&g->state=='B'&&wh3wg_check(g);
 LeaveCriticalSection(&g->lock);return ok;
}
static void gpoison(void *context,void *guard,const char *reason) {
 wh3wg_gate *g=context;(void)reason;if(!g)return;EnterCriticalSection(&g->lock);
 if(guard==g)g->poisoned=1;LeaveCriticalSection(&g->lock);
}
static void gleave(void *context,void *guard) {
 wh3wg_gate *g=context;if(!g)return;EnterCriticalSection(&g->lock);
 if(guard==g&&g->borrows)g->borrows--;LeaveCriticalSection(&g->lock);
}
static int gretain(void *context) {
 wh3wg_gate *g=context;int ok=0;if(!g)return 0;EnterCriticalSection(&g->lock);
 if(g->initialized&&!g->poisoned&&g->clients<UINT_MAX){g->clients++;ok=1;}
 LeaveCriticalSection(&g->lock);return ok;
}
static void grelease(void *context) {
 wh3wg_gate *g=context;if(!g)return;EnterCriticalSection(&g->lock);
 if(g->clients)g->clients--;LeaveCriticalSection(&g->lock);
}
void wh3wg_domain(wh3wg_gate *g,wh3w_domain *out) {
 if(!out)return;out->context=g;out->enter=genter;out->validate=gvalid;out->poison=gpoison;out->leave=gleave;
 out->retain=gretain;out->release=grelease;
}
static int gtip(wh3w_store *s,const wh3_tip *expected,int terminal) {
 journal *j;wh3_tip actual;uint64_t seq;char seal[65];LONGLONG bytes;int ok=0;
 if(!s||!expected||s->poisoned)return 0;
 EnterCriticalSection(&s->lock);j=malloc(sizeof(*j));
 if(j&&identities(s)&&loadjournal(s,s->j,j)&&intents(s->i,j,&seq,seal,&bytes)){
  unsigned line_seq,event;char tail;
  tipof(s,j,&actual);ok=eqtip(&actual,expected);
  if(ok&&terminal)ok=j->n>1&&sscanf(j->lines[j->n-1],"EXRWH2 %u %u %c",&line_seq,&event,&tail)==3
       &&event==12; /* validated FSM's durable RELEASE_BEGIN */
 }
 free(j);LeaveCriticalSection(&s->lock);return ok;
}
int wh3wg_resume(wh3wg_gate *g,const wh_binding *b,const wh_gates *gates,
 wh3w_store *s,const wh3_tip *exact,void **cap) {
 int ok=0;if(cap)*cap=NULL;if(!g||!s||!cap)return 0;
 EnterCriticalSection(&s->lock);EnterCriticalSection(&g->lock);
 if(g->mode==WH3WG_RECOVER&&!g->active&&!g->borrows&&g->state=='B'&&wh3wg_check(g)
    &&gbinding(g,b,gates,exact)&&!memcmp(g->manifest,exact->manifest_sha,65)
    &&s&&s->d.context==g&&gtip(s,exact,0)){
  g->binding=*b;g->active=1;*cap=g;ok=1;
 }
 LeaveCriticalSection(&g->lock);LeaveCriticalSection(&s->lock);return ok;
}
int wh3wg_finish(wh3wg_gate *g,void *cap,wh3w_store *s,const wh3_tip *exact,
 int (*prove)(void *,const wh3_tip *),void *context,wh3wg_grant *grant) {
 int ok=0;if(!g||!s||!prove||!grant)return 0;
 EnterCriticalSection(&s->lock);EnterCriticalSection(&g->lock);
 if(cap==g&&g->active&&!g->borrows&&g->state=='B'&&wh3wg_check(g)
    &&s&&s->d.context==g&&gtip(s,exact,1)&&!memcmp(g->manifest,exact->manifest_sha,65)
    &&prove(context,exact)&&wh3wg_check(g)&&gtip(s,exact,1)
    &&grecord(g,'C',g->generation,exact,WH3WG_CLEAN_WRITTEN)){
  g->active=0;grant->generation=g->generation;memcpy(grant->seal,g->seal,65);ok=1;
 }
 if(!ok&&cap==g&&g->active)g->poisoned=1;
 LeaveCriticalSection(&g->lock);LeaveCriticalSection(&s->lock);return ok;
}

int wh3wg_reconcile(wh3wg_gate *g,wh3w_store *s,const wh3_tip *exact,
 int (*prove)(void *,const wh3_tip *),void *context,wh3wg_grant *grant) {
 int ok=0;if(!g||!s||!prove||!grant)return 0;
 EnterCriticalSection(&s->lock);EnterCriticalSection(&g->lock);
 if(g->mode==WH3WG_RECOVER&&!g->active&&!g->borrows&&g->state=='C'&&wh3wg_check(g)
    &&s->d.context==g&&gtip(s,exact,1)&&!memcmp(g->manifest,exact->manifest_sha,65)
    &&prove(context,exact)&&wh3wg_check(g)&&gtip(s,exact,1)){
  grant->generation=g->generation;memcpy(grant->seal,g->seal,65);ok=1;
 }
 LeaveCriticalSection(&g->lock);LeaveCriticalSection(&s->lock);return ok;
}

/* Observes an exact, currently valid CLEAN grant without advancing it. */
int wh3wg_clean(wh3wg_gate *g,wh3wg_grant *grant) {
 int ok=0;if(!g||!grant)return 0;EnterCriticalSection(&g->lock);
 if(!g->active&&(g->state=='I'||g->state=='C')&&wh3wg_check(g)){
  grant->generation=g->generation;memcpy(grant->seal,g->seal,65);ok=1;
 }
 LeaveCriticalSection(&g->lock);return ok;
}
