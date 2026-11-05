/* SPDX-License-Identifier: MIT */
#define EXR_MIGRATION_TX_CANDIDATE 1
#define wmain pc02_unused_legacy_wmain
#define main pc02_unused_legacy_main
#include "../../src/lm_main.c"
#undef main
#undef wmain
#include "pc02_transform.h"
#include <sys/stat.h>

typedef struct {int64_t id;
exr_format format;
uint64_t size;
char sha[65];
}
pc02t_original;
static int pc02t_source(exr_library *library,int64_t id,uint64_t *size,char sha[65]) {
 exr_source source={0};
 exr_error error={0};
 unsigned char buffer[65536];
 uint64_t offset=0;
 lm_sha hash;
 int ok=0;
 if(exr_library_source(library,id,&source,&error)!=EXR_OK)goto done;
 if(!source.read_at||!source.release)goto done;
 lm_sha_init(&hash);
 while(offset<source.size){
  size_t n=(size_t)((source.size-offset)>sizeof(buffer)?sizeof(buffer):source.size-offset);
  if(source.read_at(source.context,offset,buffer,n)!=n)goto done;
  lm_sha_add(&hash,buffer,n);
  offset+=n;
 }
 *size=source.size;
 lm_sha_hex(&hash,sha);
 ok=1;
done:
 if(source.release)source.release(source.context);
 return ok;
}
static int pc02t_baseline(exr_library *library,pc02t_original **out,size_t *count) {
 exr_book *books=NULL;
 exr_error error={0};
 size_t n=0,k;
 pc02t_original *rows=NULL;
 int ok=0;
 *out=NULL;
 *count=0;
 if(exr_library_books(library,NULL,&books,&n,&error)!=EXR_OK||n>LM_BOOK_MAX)goto done;
 rows=calloc(n?n:1,sizeof(*rows));
 if(!rows)goto done;
 for(k=0;k<n;k++){
  rows[k].id=books[k].id;
  rows[k].format=books[k].format;
  if(!pc02t_source(library,books[k].id,&rows[k].size,rows[k].sha))goto done;
 }
 *out=rows;
 *count=n;
 rows=NULL;
 ok=1;
done:
 free(rows);
 exr_books_free(books,n);
 return ok;
}
static int pc02t_preserved(exr_library *library,const pc02t_original *rows,size_t count) {
 exr_book *books=NULL;
 exr_error error={0};
 size_t n=0,i,k;
 int ok=0;
 if(exr_library_books(library,NULL,&books,&n,&error)!=EXR_OK)goto done;
 for(i=0;i<count;i++){
  uint64_t size=0;
  char sha[65];
  for(k=0;k<n&&books[k].id!=rows[i].id;k++){}
  if(k==n||books[k].format!=rows[i].format||
     !pc02t_source(library,rows[i].id,&size,sha)||size!=rows[i].size||strcmp(sha,rows[i].sha))goto done;
 }
 ok=1;
done:
 exr_books_free(books,n);
 return ok;
}
static int pc02t_quiet(const char *path) {
 static const char *suffix[]={"-wal","-shm","-journal"};
 size_t k;
 for(k=0;k<3;k++){
  char *p=path_join(path,suffix[k]);
  int state=lm_path_state(p);
  free(p);
  if(state!=0)return 0;
 }
 return 1;
}
static void pc02t_free(ctx *c) {
 size_t k;
 if(!c)return;
 if(c->lib)exr_library_close(c->lib);
 lm_pack_close(&c->pack);
 for(k=0;k<c->ledger.book_n;k++){
  lm_book *b=&c->ledger.books[k];
  free(b->legacy);
  free(b->audio_id);
  free(b->retained);
  free(b->title);
  free(b->author);
  free(b->tags);
  exr_audio_checkpoint_free(&b->audio_expected);
 }
 for(k=0;k<c->ledger.note_n;k++){
  lm_note *n=&c->ledger.notes[k];
  free(n->legacy);
  free(n->book_legacy);
  free(n->method);
  free(n->reason);
  free(n->retained);
  free(n->text);
 }
 for(k=0;k<c->ledger.pack_n;k++)free(c->ledger.packs[k]);
 free(c->ledger.packs);
 free(c->ledger.books);
 free(c->ledger.notes);
 free(c->ledger.book_index.keys);
 free(c->ledger.book_index.vals);
 free(c->ledger.note_index.keys);
 free(c->ledger.note_index.vals);
 free(c->ledger.id_index.keys);
 free(c->ledger.id_index.vals);
 free(c->pack_books.keys);
 free(c->pack_books.vals);
 free(c->seen_a);
 free(c->seen_b);
 lm_sb_free(&c->entries);
 lm_sb_free(&c->items);
 lm_sb_free(&c->notes);
 free(c->sidecar);
 free(c->pending);
 free(c);
}
static ctx *pc02t_context(int pack_handle,const char *target,const char *pack) {
 ctx *c=calloc(1,sizeof(*c));
 lm_err error={{0},{0}};
 struct stat expected,actual;
 if(!c)return NULL;
 c->cmd="verify";
 c->target=target;
 c->pack_path=pack;
 c->cancel_at=-1;
 c->inject_at=-1;
 c->control.cancelled=cancel_cb;
 c->control.context=c;
 if(pack_handle<0||fstat(pack_handle,&expected)||!S_ISREG(expected.st_mode)||expected.st_nlink!=1||
    expected.st_uid!=geteuid()||!lm_pack_open(pack,&c->pack,&error)||
    fstat(fileno(c->pack.f),&actual)||!S_ISREG(actual.st_mode)||actual.st_nlink!=1||
    actual.st_dev!=expected.st_dev||actual.st_ino!=expected.st_ino||
    !lm_pack_verify(&c->pack,cancel_cb,c,&error)){
  fprintf(stderr,"C02 pack refused: %s: %s\n",error.code,error.message);
  pc02t_free(c);
  return NULL;
 }
 c->books_expected=(unsigned)c->pack.books->n;
 c->notes_expected=(unsigned)c->pack.notes->n;
 return c;
}
static int pc02t_mirror_equal(exr_library *library,const char *path) {
 void *data=NULL;
 size_t size=0;
 int found=0,ok=0;
 lm_err error={{0},{0}};
 exr_error sdk={0};
 lm_mirror_file mirror;
 char *bytes=NULL;
 size_t count=0;
 if(exr_library_migration_ledger_get(library,&data,&size,&found,&sdk)!=EXR_OK||!found)goto done;
 if(!lm_mirror_snapshot(path,1,LM_MIRROR_LEDGER_MAX,&mirror,&bytes,&count,&error)||
    !mirror.present||size!=count||memcmp(data,bytes,size))goto done;
 ok=1;
done:
 exr_free(data);
 free(bytes);
 return ok;
}
int pc02t_build(int pack_handle,const char *pack,const char *stage,
 const char *mirror_stage,const char *original_mirror,int allow_partial) {
 ctx *c=pc02t_context(pack_handle,stage,pack);
 pc02t_original *baseline=NULL;
 size_t n=0;
 void *ledger=NULL;
 size_t ledger_size=0;
 int found=0,ok=0;
 lm_sb text;
 char *old_bytes=NULL;
 size_t old_size=0;
 lm_mirror_file old;
 lm_err error={{0},{0}};
 FILE *mirror=NULL;
 lm_sb_init(&text);
 if(!c)return 0;
 c->cmd="migrate";
 c->allow_partial=allow_partial;
 c->stage=(char *)stage;
 if(!pc02t_quiet(stage))goto done;
 if(exr_library_migration_open(stage,&c->lib,&c->err)!=EXR_OK)goto done;
 if(!pc02t_baseline(c->lib,&baseline,&n)||
    exr_library_migration_ledger_get(c->lib,&ledger,&ledger_size,&found,&c->err)!=EXR_OK)goto done;
 if(original_mirror){
  if(!lm_mirror_snapshot(original_mirror,1,LM_MIRROR_LEDGER_MAX,&old,&old_bytes,&old_size,&error)||!old.present)goto done;
  if(found&&(ledger_size!=old_size||memcmp(ledger,old_bytes,ledger_size)))goto done;
 }
 if(found){if(!sidecar_parse(c,ledger,ledger_size))goto done;
 }
 else if(original_mirror&&!sidecar_parse(c,old_bytes,old_size))goto done;
 if(!process_pack_rows(c)||!verify_library(c,c->lib,1)||!pc02t_preserved(c->lib,baseline,n))goto done;
 sidecar_text(c,&text);
 if(text.oom||text.n>LM_MIRROR_LEDGER_MAX||
    exr_library_migration_ledger_set(c->lib,text.p,text.n,&c->err)!=EXR_OK)goto done;
 /* The native owner reserved this exact empty object before PENDING. */
 mirror=lm_fopen(mirror_stage,"r+b");
 if(!mirror||fwrite(text.p,1,text.n,mirror)!=text.n||!lm_sync(mirror))goto done;
 if(fclose(mirror)!=0){mirror=NULL;
 goto done;
 }
 mirror=NULL;
 if(exr_library_migration_finish(c->lib,1,&c->err)!=EXR_OK)goto done;
 exr_library_close(c->lib);
 c->lib=NULL;
 if(!pc02t_quiet(stage)||exr_library_open(stage,&c->lib,&c->err)!=EXR_OK||
    !pc02t_preserved(c->lib,baseline,n)||!pc02t_mirror_equal(c->lib,mirror_stage))goto done;
 exr_library_close(c->lib);
 c->lib=NULL;
 ok=pc02t_verify(pack_handle,stage,pack,mirror_stage);
done:
 if(mirror)fclose(mirror);
 if(!ok)fprintf(stderr,"C02 private transform refused: %s %s SDK=%s\n",c->code,c->message,c->err.message);
 else printf("{\"private_import\":true,\"books_created\":%u,\"notes_created\":%u,\"baseline_originals\":%llu}\n",
   c->books_created,c->notes_created,(unsigned long long)n);
 free(baseline);
 exr_free(ledger);
 free(old_bytes);
 lm_sb_free(&text);
 pc02t_free(c);
 return ok;
}
int pc02t_verify(int pack_handle,const char *target,const char *pack,const char *mirror) {
 ctx *c=pc02t_context(pack_handle,target,pack);
 int ok=0;
 if(!c)return 0;
 if(!pc02t_quiet(target))goto done;
 run_verify(c);
 if(c->out!=O_SUCCESS||!c->lib||!pc02t_mirror_equal(c->lib,mirror))goto done;
 ok=1;
done:
 if(!ok)fprintf(stderr,"C02 independent verification refused: %s %s SDK=%s\n",c->code,c->message,c->err.message);
 pc02t_free(c);
 return ok&&pc02t_quiet(target);
}

int pc02t_original_verify(const char *target,const char *mirror) {
 ctx *c=calloc(1,sizeof(*c));
 pc02t_original *baseline=NULL;
 size_t count=0;
 void *ledger=NULL;
 size_t bytes=0;
 int found=0,ok=0;
 char *old=NULL;
 size_t old_bytes=0;
 lm_mirror_file snapshot;
 lm_err error={{0},{0}};
 if(!c)return 0;
 c->target=target;
 c->cmd="repair-original-proof";
 if(!pc02t_quiet(target)||exr_library_open(target,&c->lib,&c->err)!=EXR_OK||
    !pc02t_baseline(c->lib,&baseline,&count)||
    exr_library_migration_ledger_get(c->lib,&ledger,&bytes,&found,&c->err)!=EXR_OK)goto done;
 if(found&&!sidecar_parse(c,ledger,bytes))goto done;
 if(mirror){
  if(!lm_mirror_snapshot(mirror,1,LM_MIRROR_LEDGER_MAX,&snapshot,&old,&old_bytes,&error)||!snapshot.present||
     (found&&(bytes!=old_bytes||memcmp(ledger,old,bytes)))||(!found&&!sidecar_parse(c,old,old_bytes)))goto done;
 }
 exr_library_close(c->lib);
 c->lib=NULL;
 /* Frozen SDK dump independently enumerates original blobs/covers, every
    reflow/fixed annotation, progress, and all ledger audio bookmarks/resume. */
 dump_library(c);
 if(!c->lib||c->out!=O_NONE||!pc02t_preserved(c->lib,baseline,count))goto done;
 printf("{\"repair_original_actual_sdk\":true,\"original_books\":%llu}\n",(unsigned long long)count);
 ok=1;
done:
 free(baseline);
 exr_free(ledger);
 free(old);
 pc02t_free(c);
 return ok&&pc02t_quiet(target);
}
