/* SPDX-License-Identifier: MIT
 * Actions-only public-API fixture/state/lifetime consumer. No recovery policy. */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef _WIN32
#include <time.h>
#endif
static exr_error error;
static int failed;
static int ok(exr_status status,const char *what){if(status!=EXR_OK){fprintf(stderr,"%s status=%d %s\n",what,(int)status,error.message);failed=1;return 0;}return 1;}
static void *read_file(const char *path,size_t *size){FILE *f=fopen(path,"rb");long n;void *p;if(!f)return NULL;if(fseek(f,0,SEEK_END)||(n=ftell(f))<0||n>64*1024*1024||fseek(f,0,SEEK_SET)){fclose(f);return NULL;}p=malloc((size_t)n+1);if(!p||fread(p,1,(size_t)n,f)!=(size_t)n){free(p);fclose(f);return NULL;}if(fclose(f)){free(p);return NULL;}*size=(size_t)n;return p;}
static int bounded(exr_library *lib,const char *epub,const char *fontpath){exr_font *font=NULL;exr_publication *publication=NULL;exr_pager *pager=NULL;exr_source source={0};const exr_part *parts;size_t n=0;int64_t id=0,noteid=0;exr_epub_location point={0};exr_epub_note note={0};exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();
  if(!ok(exr_library_import_file(lib,EXR_EPUB,epub,"bounded-original",&id,&error),"bounded-import")||!ok(exr_library_source(lib,id,&source,&error),"bounded-source")||!ok(exr_publication_open_source(&source,&publication,&error),"bounded-publication"))goto done;memset(&source,0,sizeof(source));parts=exr_publication_parts(publication,&n);if(!parts||n<2){failed=1;goto done;}
  if(!ok(exr_font_open(fontpath,&font,&error),"font")||!ok(exr_publication_pager_create(publication,1,font,&config,&options,&pager,&error),"bounded-pager"))goto done;
  point.part=1;point.path=malloc(strlen(parts[1].path)+1);if(!point.path){failed=1;goto done;}strcpy(point.path,parts[1].path);
  if(!ok(exr_pager_anchor_create(pager,5,5,NULL,&point.selector,&error),"bounded-point")||!ok(exr_library_epub_progress(lib,id,&point,&error),"bounded-progress"))goto done;
  note.book_id=id;note.location.part=1;note.location.path=point.path;note.text="bounded-comment";
  if(!ok(exr_pager_anchor_create(pager,5,9,NULL,&note.location.selector,&error),"bounded-quote")||!ok(exr_library_epub_note(lib,&note,&noteid,&error),"bounded-note"))goto done;
  printf("{\"bounded_book\":%lld,\"bounded_note\":%lld,\"part\":1,\"point\":5,\"range\":[5,9]}\n",(long long)id,(long long)noteid);
 done:exr_anchor_free(&note.location.selector);exr_epub_location_free(&point);if(pager)exr_pager_free(pager);if(publication)exr_publication_free(publication);if(source.context)source.release(source.context);if(font)exr_font_free(font);return !failed;
}
static int edit_all(exr_library *lib){exr_book *books=NULL;size_t count=0,i;exr_audio_checkpoint audio={"later-track",(UINT64_C(1)<<53)+31,1.25};exr_audio_bookmark mark={0};int64_t markid=0;
  if(!ok(exr_library_books(lib,NULL,&books,&count,&error),"books"))return 0;
  for(i=0;i<count&&!failed;i++){
    exr_book changed=books[i];exr_library_epub_info info={0};int isbounded=0;changed.title="later writer title";changed.author="later author";changed.tags="later,kept";changed.favorite=1;
    if(!ok(exr_library_update(lib,&changed,&error),"metadata"))break;
    if(books[i].format==EXR_EPUB){exr_epub_note *notes=NULL;size_t n=0,j;info.struct_size=sizeof(info);if(!ok(exr_library_epub_info_get(lib,books[i].id,&info,&error),"epub-mode"))break;isbounded=info.bounded_storage;
      if(!ok(exr_library_epub_notes(lib,books[i].id,&notes,&n,&error),"epub-notes"))break;for(j=0;j<n&&!failed;j++){exr_epub_note edited=notes[j];int64_t id=edited.id;edited.text="later bounded comment";edited.location.selector.exact=NULL;ok(exr_library_epub_note(lib,&edited,&id,&error),"epub-note-text");}exr_epub_notes_free(notes,n);
      if(isbounded){exr_epub_location p={0};int found=0;if(ok(exr_library_epub_progress_get(lib,books[i].id,&p,&found,&error),"epub-progress")&&found){p.selector.start=p.selector.end=6;ok(exr_library_epub_progress(lib,books[i].id,&p,&error),"epub-progress-write");}exr_epub_location_free(&p);}
    }
    if(!isbounded){exr_note *notes=NULL;size_t n=0,j;if(!ok(exr_library_notes(lib,books[i].id,&notes,&n,&error),"notes"))break;for(j=0;j<n&&!failed;j++)ok(exr_library_note_text(lib,notes[j].id,"later reflow comment",&error),"note-text");exr_notes_free(notes,n);}
    if(books[i].format>=EXR_TXT&&books[i].format<=EXR_MOBI&&!isbounded){exr_document *doc=NULL;exr_anchor point={0};if(ok(exr_library_document(lib,books[i].id,&doc,&error),"document")&&ok(exr_anchor_create(doc,1,1,&point,&error),"progress-anchor"))ok(exr_library_progress(lib,books[i].id,&point,&error),"progress-write");exr_anchor_free(&point);if(doc)exr_document_free(doc);}
    if(books[i].format==EXR_PDF||books[i].format==EXR_CBZ){exr_fixed_note *notes=NULL;size_t n=0,j;if(!ok(exr_library_fixed_notes(lib,books[i].id,&notes,&n,&error),"fixed-notes"))break;for(j=0;j<n&&!failed;j++){exr_fixed_note edited=notes[j];int64_t id=edited.id;edited.text="later fixed comment";ok(exr_library_fixed_note(lib,&edited,NULL,&id,&error),"fixed-text");}exr_fixed_notes_free(notes,n);}
  }
  if(!failed){ok(exr_library_audio_resume(lib,"later-independent-audio",&audio,&error),"audio-resume");mark.label="later audio label";mark.position=audio;ok(exr_library_audio_bookmark(lib,"later-independent-audio",&mark,&markid,&error),"audio-mark");}
  exr_books_free(books,count);return !failed;
}
int main(int argc,char **argv){exr_library *lib=NULL;int result=2;if(!getenv("GITHUB_ACTIONS")||strcmp(getenv("GITHUB_ACTIONS"),"true")||argc<3)return 2;
  if(!ok(exr_library_open(argv[2],&lib,&error),"open"))goto done;
  if(!strcmp(argv[1],"import")&&argc==6){size_t n=0;void *data=read_file(argv[4],&n);int64_t id=0;if(!data){failed=1;goto done;}ok(exr_library_import(lib,(exr_format)atoi(argv[3]),data,n,argv[5],&id,&error),"import");free(data);printf("{\"id\":%lld,\"format\":%d}\n",(long long)id,atoi(argv[3]));}
  else if(!strcmp(argv[1],"bounded")&&argc==5)bounded(lib,argv[3],argv[4]);
  else if(!strcmp(argv[1],"edit-all"))edit_all(lib);
  else if(!strcmp(argv[1],"hold-source")&&argc==4){exr_book *books=NULL;size_t n=0;exr_source source={0};char marker[4096];FILE *f;unsigned k;unsigned char byte;
    if(!ok(exr_library_books(lib,NULL,&books,&n,&error),"source-books")||!n||!ok(exr_library_source(lib,books[n-1].id,&source,&error),"live-source")){exr_books_free(books,n);goto done;}exr_books_free(books,n);exr_library_close(lib);lib=NULL;
    snprintf(marker,sizeof(marker),"%s.ready",argv[3]);f=fopen(marker,"wbx");if(!f){source.release(source.context);goto done;}fputs("source owner retained after public close\n",f);fclose(f);
    for(k=0;k<3000;k++){snprintf(marker,sizeof(marker),"%s.go",argv[3]);f=fopen(marker,"rb");if(f){fclose(f);break;}
#ifndef _WIN32
      {struct timespec delay={0,10000000};nanosleep(&delay,NULL);}
#endif
    }
    if(k==3000||!source.size||source.read_at(source.context,0,&byte,1)!=1)failed=1;source.release(source.context);
  }else {failed=1;}
  result=failed?3:0;
 done:if(lib)exr_library_close(lib);return result;
}
