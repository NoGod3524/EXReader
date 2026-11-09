/* SPDX-License-Identifier: MIT */
/* Misuse runs in isolated processes; the runner rejects memory crashes. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#ifdef _MSC_VER
#include <crtdbg.h>
#endif
#endif

static exr_error error;
static unsigned checks;
static const char *fixtures;
#define CHECK(x) do { checks++; if (!(x)) { \
  fprintf(stderr,"TEST_CHECK_FAILED line %d: %s (%d: %s)\n", \
    __LINE__,#x,(int)error.code,error.message); exit(1); } } while (0)
#define OK(x) CHECK((x)==EXR_OK)

static exr_document *document(void) {
  const char text[]="Lifetime alpha beta gamma. An owned document has independent text.\n";
  exr_document *doc=NULL;
  OK(exr_document_open_memory(EXR_TXT,text,sizeof(text)-1,&doc,&error));
  CHECK(doc); return doc;
}
static exr_font *font(void) {
  char path[4096]; exr_font *out=NULL;
  CHECK(snprintf(path,sizeof(path),"%s/fonts/primary.ttf",fixtures)>0);
  OK(exr_font_open(path,&out,&error)); CHECK(out); return out;
}
static exr_layout_config config(void) {
  exr_layout_config c=exr_layout_config_defaults();
  c.page=(exr_layout_options){180,160,8,16,1.2f,0}; return c;
}
static exr_pager *pager(exr_document *d,exr_font *f) {
  exr_pager *out=NULL; exr_layout_config c=config();
  OK(exr_pager_create(d,f,&c,&out,&error)); CHECK(out); return out;
}
static exr_layout *layout(exr_document *d,exr_font *f) {
  exr_layout *out=NULL; exr_layout_config c=config();
  OK(exr_layout_create_ex(d,f,&c,&out,&error)); CHECK(out); return out;
}
static exr_publication *publication(void) {
  char path[4096]; exr_publication *out=NULL;
  CHECK(snprintf(path,sizeof(path),"%s/font-book.epub",fixtures)>0);
  OK(exr_publication_open(path,&out,&error));
  CHECK(out); return out;
}
static exr_canvas *canvas(void) {
  exr_canvas_config c={0}; exr_canvas *out=NULL;
  c.width=8; c.height=8; c.channels=4; c.background=0xffffffffu;
  OK(exr_canvas_create(&c,&out,&error)); CHECK(out); return out;
}
static exr_text_index *index_create(void) {
  exr_text_index *out=NULL; CHECK(exr_text_index_available());
  OK(exr_text_index_open(":memory:",&out,&error)); CHECK(out);
  OK(exr_text_index_put(out,"source","part","banana",6,NULL,&error)); return out;
}
static exr_text_query *query_create(exr_text_index *index) {
  exr_text_query *out=NULL;
  OK(exr_text_index_query(index,"source","ana",3,NULL,&out,&error)); CHECK(out); return out;
}
static void balanced(void) {
  exr_lifetime_count counts[64]; size_t i,n=exr_debug_counts(counts,64);
  CHECK(n>0 && n<=64);
  for(i=0;i<n;i++) {
    if(counts[i].created!=counts[i].freed || counts[i].live) {
      fprintf(stderr,"UNBALANCED %s create=%zu free=%zu live=%zu\n",
        counts[i].type,counts[i].created,counts[i].freed,counts[i].live); CHECK(0);
    }
  }
  exr_debug_cleanup();
}

static void valid_document(void) {
  exr_document *d=document(); size_t n=0;
  CHECK(exr_validate(d)); CHECK(exr_document_text(d,&n) && n);
  CHECK(exr_validate(exr_document_text(d,NULL))); exr_document_free(d);
}
static void document_double_free(void) {
  exr_document *d=document(); exr_document_free(d); exr_document_free(d);
}
static void document_after_free(void) {
  exr_document *d=document(); exr_document_free(d); (void)exr_document_title(d);
}
static void validate_after_free(void) {
  exr_document *d=document(); exr_document_free(d); (void)exr_validate(d);
}
static void stale_address_after_create(void) {
  exr_document *old=document(),*replacement;
  exr_document_free(old); replacement=document(); CHECK(replacement!=old);
  (void)exr_document_text(old,NULL);
}
static void font_double_free(void) {
  exr_font *f=font(); exr_font_free(f); exr_font_free(f);
}
static void font_after_free(void) {
  exr_font *f=font(); exr_font_free(f); (void)exr_font_count(f);
}
static void pager_double_free(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  exr_pager_free(p); exr_pager_free(p);
}
static void pager_after_document_free(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  exr_layout *page=NULL; exr_document_free(d); (void)exr_pager_next(p,&page,&error);
}
static void pager_retains_font(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  exr_layout *page=NULL; exr_bitmap image={0};
  exr_font_free(f); CHECK(exr_validate(p)); OK(exr_pager_next(p,&page,&error));
  CHECK(page); OK(exr_render_page(page,NULL,0,&image,&error)); CHECK(image.pixels);
  exr_bitmap_free(&image); exr_layout_free(page); exr_pager_free(p); exr_document_free(d);
}
static void layout_font_reborrow(void) {
  exr_document *d=document(); exr_font *f=font(), *view;
  exr_layout *a=layout(d,f), *b=layout(d,f); exr_bitmap image={0};
  exr_font_free(f); view=exr_layout_font(a);
  CHECK(exr_validate(view) && exr_font_count(view)>0);
  OK(exr_render_page(a,view,0,&image,&error)); exr_bitmap_free(&image);
  exr_layout_free(a); view=exr_layout_font(b);
  CHECK(exr_validate(view) && exr_font_count(view)>0);
  exr_layout_free(b); exr_document_free(d);
}
static void borrowed_font_after_layout_free(void) {
  exr_document *d=document(); exr_font *f=font(), *view;
  exr_layout *a=layout(d,f), *b=layout(d,f);
  (void)b; exr_font_free(f); view=exr_layout_font(a); exr_layout_free(a);
  (void)exr_font_count(view);
}
static void validate_broken_parent_chain(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  exr_document_free(d); (void)exr_validate(p);
}
static void child_cleanup_after_document_free(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  exr_document_free(d); exr_pager_free(p); exr_font_free(f);
}
static void layout_double_free(void) {
  exr_document *d=document(); exr_font *f=font(); exr_layout *l=layout(d,f);
  exr_layout_free(l); exr_layout_free(l);
}
static void layout_after_free(void) {
  exr_document *d=document(); exr_font *f=font(); exr_layout *l=layout(d,f);
  exr_layout_free(l); (void)exr_layout_pages(l,NULL);
}
static void borrowed_nodes_after_document_free(void) {
  const exr_attribute attribute={"id","lifetime"};
  const exr_node_input input_nodes[]={
    {EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},
    {EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0},
    {EXR_NODE_PARAGRAPH,1,NULL,NULL,&attribute,1},
    {EXR_NODE_TEXT,2,NULL,"borrowed node",NULL,0}
  };
  const exr_chapter_input chapter={"main","main.unit",1,1};
  const exr_document_input input={"Lifetime",input_nodes,4,&chapter,1,NULL,0};
  exr_document *d=NULL; const exr_node *nodes; size_t n=0,i;
  OK(exr_document_create(&input,&d,&error));
  nodes=exr_document_nodes(d,&n); CHECK(nodes && n);
  for(i=0;i<n;i++) if(exr_node_attribute(&nodes[i],"id")) break;
  CHECK(i<n); exr_document_free(d); (void)exr_node_attribute(&nodes[i],"id");
}
static void borrowed_text_after_document_free(void) {
  exr_document *d=document(); const char *text=exr_document_text(d,NULL);
  CHECK(text); exr_document_free(d);
  /* Checked borrow access: direct C loads cannot invoke an SDK assertion. */
  CHECK(exr_validate(text)); (void)strlen(text);
}
static void borrowed_page_after_pager_free(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  const exr_layout *page=NULL; OK(exr_pager_get(p,0,&page,&error)); CHECK(page);
  exr_pager_free(p); (void)exr_layout_pages(page,NULL);
}
static void owned_page_survives_pager(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  exr_layout *page=NULL; exr_bitmap image={0}; size_t n=0;
  OK(exr_pager_next(p,&page,&error)); CHECK(page); exr_pager_free(p);
  CHECK(exr_validate(page)); CHECK(exr_layout_pages(page,&n) && n==1);
  OK(exr_render_page(page,NULL,0,&image,&error)); CHECK(image.pixels);
  exr_bitmap_free(&image); exr_layout_free(page); exr_document_free(d); exr_font_free(f);
}
static void publication_document_survives_parent(void) {
  exr_publication *p=publication(); exr_document *d=NULL; size_t n=0;
  OK(exr_publication_load(p,0,&d,&error)); CHECK(d); exr_publication_free(p);
  CHECK(exr_validate(d)); CHECK(exr_document_text(d,&n) && n); exr_document_free(d);
}
static void session_retains_publication(void) {
  exr_publication *p=publication(); exr_font *f=font(); exr_session *s=NULL;
  const exr_document *d=NULL; const exr_layout *l=NULL; exr_layout_config c=config();
  OK(exr_session_create(p,f,&c,1,&s,&error)); exr_publication_free(p);
  CHECK(exr_validate(s)); OK(exr_session_get(s,0,&d,&l,&error));
  CHECK(d && l && exr_document_text(d,NULL) && exr_layout_pages(l,NULL));
  exr_session_free(s); exr_font_free(f);
}
static void retained_publication_double_free(void) {
  exr_publication *p=publication(); exr_font *f=font(); exr_session *s=NULL;
  exr_layout_config c=config();
  OK(exr_session_create(p,f,&c,1,&s,&error));
  exr_publication_free(p); exr_publication_free(p);
}
static void retained_publication_after_free(void) {
  exr_publication *p=publication(); exr_font *f=font(); exr_session *s=NULL;
  exr_layout_config c=config();
  OK(exr_session_create(p,f,&c,1,&s,&error));
  exr_publication_free(p); (void)exr_publication_title(p);
}
static void borrowed_page_free(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  const exr_layout *page=NULL;
  OK(exr_pager_get(p,0,&page,&error)); CHECK(page);
  exr_layout_free((exr_layout *)page);
}
static void borrowed_session_layout_after_clear(void) {
  exr_publication *p=publication(); exr_font *f=font(); exr_session *s=NULL;
  const exr_document *d=NULL; const exr_layout *l=NULL; exr_layout_config c=config();
  OK(exr_session_create(p,f,&c,1,&s,&error));
  OK(exr_session_get(s,0,&d,&l,&error)); CHECK(l);
  exr_session_clear(s); (void)exr_layout_pages(l,NULL);
}
static void bidi_double_free(void) {
  exr_bidi *b=NULL; OK(exr_bidi_analyze("abc",3,EXR_DIRECTION_LTR,&b,&error));
  exr_bidi_free(b); exr_bidi_free(b);
}
static void canvas_double_free(void) {
  exr_canvas *c=canvas(); exr_canvas_free(c); exr_canvas_free(c);
}
static void borrowed_bitmap_after_canvas_free(void) {
  exr_canvas *c=canvas(); const exr_bitmap *view=exr_canvas_bitmap(c);
  CHECK(view && view->pixels); exr_canvas_free(c); (void)exr_validate(view);
}
static void canvas_take_survives_parent(void) {
  exr_canvas *c=canvas(); exr_bitmap image={0};
  OK(exr_canvas_take(c,&image,&error)); exr_canvas_free(c);
  CHECK(image.pixels && image.width==8 && image.height==8 && image.pixels[0]==255);
  exr_bitmap_free(&image); CHECK(!image.pixels);
}
static void canvas_take_transfers_existing_borrow(void) {
  exr_canvas *c=canvas(); exr_bitmap image={0}; const exr_bitmap *view=exr_canvas_bitmap(c);
  const unsigned char *pixels;
  CHECK(view && view->pixels && exr_validate(view->pixels));
  pixels=view->pixels; OK(exr_canvas_take(c,&image,&error)); CHECK(image.pixels==pixels);
  exr_canvas_free(c); CHECK(exr_validate(image.pixels));
  CHECK(image.pixels[0]==255); exr_bitmap_free(&image);
}
static void borrowed_pixels_after_canvas_free(void) {
  exr_canvas *c=canvas(); const unsigned char *pixels=exr_canvas_bitmap(c)->pixels;
  CHECK(pixels); exr_canvas_free(c); (void)exr_validate(pixels);
}
static void owned_buffer_double_free(void) {
  unsigned char *boundaries=NULL;
  OK(exr_text_analyze("abc",3,&boundaries,&error)); CHECK(boundaries);
  exr_free(boundaries); exr_free(boundaries);
}
static void owned_export_survives_document(void) {
  exr_document *d=document(); void *data=NULL; size_t size=0;
  OK(exr_document_export(d,EXR_TXT,&data,&size,&error)); CHECK(data && size);
  exr_document_free(d); CHECK(exr_validate(data));
  CHECK(!memcmp(data,"Lifetime",8)); exr_free(data);
}
static void copied_bitmap_double_free(void) {
  exr_canvas *c=canvas(); exr_bitmap first={0},alias;
  OK(exr_canvas_take(c,&first,&error)); alias=first;
  exr_bitmap_free(&first); exr_bitmap_free(&alias);
}
static void copied_bitmap_after_free_write(void) {
  exr_canvas *c=canvas(); exr_bitmap first={0},alias;
  OK(exr_canvas_take(c,&first,&error)); alias=first;
  exr_bitmap_free(&first);
  (void)exr_bitmap_write_png(&alias,"lifetime-must-not-write.png",&error);
}
static void canvas_sink_after_free(void) {
  exr_canvas *c=canvas(); exr_draw_sink sink={0};
  OK(exr_canvas_get_sink(c,&sink,&error)); CHECK(sink.state && sink.context);
  exr_canvas_free(c); (void)sink.state(sink.context,EXR_DRAW_SAVE,&error);
}
static exr_status destroy_canvas_sample(void *context,double x,double y,unsigned space,
  double components[4],double *shape,double *opacity,exr_error *e) {
  (void)x; (void)y; (void)space; (void)components; (void)shape; (void)opacity; (void)e;
  exr_canvas_free(context); return EXR_OK;
}
static void canvas_sink_destroy_active(void) {
  exr_canvas *c=canvas(); exr_draw_sink_ex sink={0}; exr_paint_source source={0};
  sink.struct_size=sizeof(sink); OK(exr_canvas_get_sink_ex(c,&sink,&error));
  CHECK(sink.paint && sink.base.context);
  source.struct_size=sizeof(source); source.sample=destroy_canvas_sample; source.context=c;
  (void)sink.paint(sink.base.context,&source,NULL,1,&error);
}
static exr_source library_source(exr_library **owner) {
  exr_source source={0}; int64_t id=0;
  OK(exr_library_open(":memory:",owner,&error));
  OK(exr_library_import(*owner,EXR_TXT,"source",6,"Lifetime source",&id,&error));
  OK(exr_library_source(*owner,id,&source,&error));
  CHECK(source.context && source.release && source.read_at && source.size==6);
  return source;
}
static void library_source_double_release(void) {
  exr_library *owner=NULL; exr_source source=library_source(&owner);
  source.release(source.context); source.release(source.context);
}
static void library_source_after_release(void) {
  exr_library *owner=NULL; exr_source source=library_source(&owner); char buffer[6];
  source.release(source.context); (void)source.read_at(source.context,0,buffer,sizeof(buffer));
}
static void library_source_survives_close(void) {
  exr_library *owner=NULL; exr_source source=library_source(&owner); char buffer[6];
  exr_library_close(owner);
  CHECK(source.read_at(source.context,0,buffer,sizeof(buffer))==sizeof(buffer));
  CHECK(!memcmp(buffer,"source",6)); source.release(source.context);
}
typedef struct { exr_library *library; unsigned char *data; size_t size; unsigned calls; } unique_reentry_state;
static size_t unique_reentry_read(void *context,uint64_t offset,void *buffer,size_t size) {
  unique_reentry_state *state=context;
  if(!state->calls++) {
    exr_error local={0}; int64_t id=42; int created=1;
    CHECK(exr_library_import_unique(state->library,EXR_TXT,"nested",6,NULL,&id,&created,&local)==EXR_ARGUMENT);
    CHECK(id==0 && created==0);
  }
  if(offset>=state->size) return 0;
  if(size>state->size-(size_t)offset) size=state->size-(size_t)offset;
  memcpy(buffer,state->data+(size_t)offset,size); return size;
}
static void library_unique_callback_reentry_rejected(void) {
  unique_reentry_state state={0}; exr_source source={0};
  char path[4096]; FILE *file; long size; int64_t id=0; int created=0;
  CHECK(snprintf(path,sizeof(path),"%s/sample.epub",fixtures)>0);
  file=fopen(path,"rb"); CHECK(file && !fseek(file,0,SEEK_END));
  size=ftell(file); CHECK(size>0); rewind(file);
  state.size=(size_t)size; state.data=malloc(state.size); CHECK(state.data);
  CHECK(fread(state.data,1,state.size,file)==state.size); fclose(file);
  OK(exr_library_open(":memory:",&state.library,&error));
  source.size=state.size; source.read_at=unique_reentry_read; source.context=&state;
  OK(exr_library_import_source_unique(state.library,EXR_EPUB,&source,NULL,&id,&created,&error));
  CHECK(state.calls>0 && id>0 && created==1);
  exr_library_close(state.library); free(state.data);
}
typedef struct { exr_audio_player *player; unsigned closes,releases; } audio_observer;
static exr_status observe_audio(void *context,const exr_audio_command *command,exr_error *e) {
  audio_observer *observer=context; exr_audio_playback state={0}; exr_error observed={0};
  (void)e;
  OK(exr_audio_player_get(observer->player,&state,&observed));
  CHECK(exr_audio_player_seek(observer->player,0,&observed)==EXR_ARGUMENT);
  if(command->kind==EXR_AUDIO_CLOSE) observer->closes++;
  return EXR_OK;
}
static void release_audio_observer(void *context) { ((audio_observer *)context)->releases++; }
static void audio_destructor_observer(void) {
  exr_audio_track track={"one","host:one","audio/custom",1000};
  exr_audio_input input={0}; exr_audio *a=NULL; exr_audio_backend backend={0};
  audio_observer observer={0};
  input.struct_size=sizeof(input); input.tracks=&track; input.track_count=1;
  OK(exr_audio_create(&input,NULL,&a,&error));
  backend.struct_size=sizeof(backend); backend.command=observe_audio;
  backend.release=release_audio_observer; backend.context=&observer;
  OK(exr_audio_player_create(a,&backend,&observer.player,&error)); exr_audio_free(a);
  OK(exr_audio_player_play(observer.player,&error)); exr_audio_player_free(observer.player);
  CHECK(observer.closes==1 && observer.releases==1);
}
static void index_double_close(void) {
  exr_text_index *index=index_create(); exr_text_index_close(index); exr_text_index_close(index);
}
static void query_double_free(void) {
  exr_text_index *index=index_create(); exr_text_query *q=query_create(index);
  exr_text_query_free(q); exr_text_query_free(q);
}
static void query_retains_index(void) {
  exr_text_index *index=index_create(); exr_text_query *q=query_create(index);
  exr_text_hit hit={0}; int found=0;
  exr_text_index_close(index); CHECK(exr_validate(q));
  OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(found && hit.start==1 && hit.end==4);
  OK(exr_text_query_next(q,&hit,&found,&error)); CHECK(found && hit.start==3 && hit.end==6);
  exr_text_query_free(q);
}
static void cfi_double_free(void) {
  exr_cfi *c=NULL; OK(exr_cfi_parse("epubcfi(/6/2!/4/2/1:0)",&c,NULL,&error));
  exr_cfi_free(c); exr_cfi_free(c);
}
static void fixed_text_survives_input(void) {
  char input[]="fixed"; exr_fixed_text *t=NULL; size_t n=0;
  OK(exr_fixed_text_create(input,5,NULL,0,NULL,&t,&error)); memset(input,'x',5);
  CHECK(exr_validate(t)); CHECK(!memcmp(exr_fixed_text_string(t,&n),"fixed",5) && n==5);
  exr_fixed_text_free(t);
}

typedef struct { exr_pager *pager; unsigned calls; int mode; } callback_state;
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) {
  callback_state *s=context; exr_error local={0};
  (void)stage; (void)completed; (void)total; s->calls++;
  if(s->mode==1) {
    CHECK(exr_pager_set_control(s->pager,NULL,&local)==EXR_ARGUMENT);
  } else if(s->mode==2) {
    exr_document *other=document();
    CHECK(exr_version() && exr_validate(other)); exr_document_free(other);
  } else {
    exr_pager_free(s->pager);
  }
}
static void callback_case(int mode) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  exr_layout *page=NULL; callback_state s={p,0,mode}; exr_control ctl={NULL,progress,&s};
  OK(exr_pager_set_control(p,&ctl,&error)); OK(exr_pager_next(p,&page,&error));
  CHECK(s.calls>0 && page);
  exr_layout_free(page); exr_pager_free(p); exr_document_free(d); exr_font_free(f);
}
static void callback_reentry_rejected(void) { callback_case(1); }
static void callback_independent_allowed(void) { callback_case(2); }
static void callback_destroy_active(void) { callback_case(3); }
static void render_callback_free_cache_owner(void) {
  exr_document *d=document(); exr_font *f=font(); exr_pager *p=pager(d,f);
  const exr_layout *page=NULL; exr_bitmap image={0}; callback_state s={p,0,3};
  exr_control ctl={NULL,progress,&s};
  OK(exr_pager_get(p,0,&page,&error)); CHECK(page);
  (void)exr_render_page_ex(page,NULL,0,4,&ctl,&image,&error);
}
static void null_free(void) {
  exr_document_free(NULL); exr_font_free(NULL); exr_pager_free(NULL);
  exr_layout_free(NULL); exr_publication_free(NULL); exr_session_free(NULL);
  exr_bidi_free(NULL); exr_canvas_free(NULL); exr_cfi_free(NULL);
  exr_text_index_close(NULL); exr_text_query_free(NULL); exr_fixed_text_free(NULL);
  exr_bitmap_free(NULL); exr_free(NULL);
}

typedef struct { const char *name; void (*run)(void); int death; } test_case;
#define NORMAL(name) {#name,name,0}
#define DEATH(name) {#name,name,1}
static const test_case cases[]={
  NORMAL(valid_document), DEATH(document_double_free), DEATH(document_after_free),
  DEATH(validate_after_free), DEATH(stale_address_after_create), DEATH(font_double_free),
  DEATH(font_after_free), DEATH(pager_double_free), DEATH(pager_after_document_free),
  NORMAL(pager_retains_font), DEATH(validate_broken_parent_chain),
  NORMAL(layout_font_reborrow), DEATH(borrowed_font_after_layout_free),
  NORMAL(child_cleanup_after_document_free), DEATH(layout_double_free),
  DEATH(layout_after_free), DEATH(borrowed_nodes_after_document_free),
  DEATH(borrowed_text_after_document_free), DEATH(borrowed_page_after_pager_free),
  NORMAL(owned_page_survives_pager), NORMAL(publication_document_survives_parent),
  NORMAL(session_retains_publication), DEATH(borrowed_session_layout_after_clear),
  DEATH(retained_publication_double_free), DEATH(retained_publication_after_free),
  DEATH(borrowed_page_free), DEATH(render_callback_free_cache_owner),
  DEATH(bidi_double_free), DEATH(canvas_double_free), DEATH(borrowed_bitmap_after_canvas_free),
  NORMAL(canvas_take_survives_parent), DEATH(index_double_close), DEATH(query_double_free),
  NORMAL(canvas_take_transfers_existing_borrow), NORMAL(audio_destructor_observer),
  DEATH(borrowed_pixels_after_canvas_free), DEATH(owned_buffer_double_free),
  NORMAL(owned_export_survives_document), DEATH(copied_bitmap_double_free),
  DEATH(copied_bitmap_after_free_write),
  DEATH(canvas_sink_after_free), DEATH(canvas_sink_destroy_active),
  DEATH(library_source_double_release), DEATH(library_source_after_release),
  NORMAL(library_source_survives_close),
  NORMAL(library_unique_callback_reentry_rejected),
  NORMAL(query_retains_index), DEATH(cfi_double_free), NORMAL(fixed_text_survives_input),
  NORMAL(callback_reentry_rejected), NORMAL(callback_independent_allowed),
  DEATH(callback_destroy_active), NORMAL(null_free)
};
int main(int argc,char **argv) {
  size_t i;
#ifdef _WIN32
  SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
#ifdef _MSC_VER
  _set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
  _CrtSetReportMode(_CRT_ASSERT,_CRTDBG_MODE_FILE);
  _CrtSetReportFile(_CRT_ASSERT,_CRTDBG_FILE_STDERR);
#endif
#endif
  if(argc==2 && !strcmp(argv[1],"--list")) {
    for(i=0;i<sizeof(cases)/sizeof(cases[0]);i++)
      printf("%s %s\n",cases[i].name,cases[i].death ? "abort" : "pass");
    return 0;
  }
  CHECK(argc==3); fixtures=argv[2];
  for(i=0;i<sizeof(cases)/sizeof(cases[0]);i++) if(!strcmp(argv[1],cases[i].name)) {
    printf("BEGIN %s\n",cases[i].name); fflush(stdout); cases[i].run();
    CHECK(!cases[i].death); balanced();
    printf("PASS %s (%u checks)\n",cases[i].name,checks); return 0;
  }
  fprintf(stderr,"Unknown lifetime case: %s\n",argv[1]); return 2;
}
