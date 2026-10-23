/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "reading.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/types.h>
#include <math.h>
#ifdef EXR_READER_PRODUCT_CATALOG
#include "catalog_sdk.h"
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

#define PAGE_TEXT_LIMIT (1024u*1024u)
#define LEGACY_INPUT_LIMIT (8u*1024u*1024u)
#define PAGE_LIMIT 20000u
typedef struct {
  exr_document *document;
  exr_publication *publication;
  exr_pager *pager;
  exr_fixed_document *fixed_document;
  exr_book *fixed_book;
  int64_t id;
  int bounded,font,hold_progress;
  int zoom;
  size_t part,page,start,end,position;
} reader_session;
struct linux_reader {
  exr_library *library;
  exr_font *font;
  exr_control control;
  reader_session current;
  reader_session pending;
  int has_pending,pending_owns_session,pending_new_pager;
#ifdef EXR_READER_PRODUCT_CATALOG
  reader_catalog *catalog;
  char *catalog_path;
  int catalog_lock;
#endif
};
static void session_free(reader_session *session) {
  exr_pager_free(session->pager);exr_publication_free(session->publication);
  exr_document_free(session->document);exr_fixed_free(session->fixed_document);
  exr_books_free(session->fixed_book,session->fixed_book ? 1:0);memset(session,0,sizeof(*session));
}
static void pending_discard(linux_reader *reader) {
  if(reader->pending_owns_session) session_free(&reader->pending);
  else if(reader->pending_new_pager) exr_pager_free(reader->pending.pager);
  memset(&reader->pending,0,sizeof(reader->pending));
  reader->has_pending=reader->pending_owns_session=reader->pending_new_pager=0;
}
void reader_result_free(reader_result *result) {
  size_t i;free(result->pixels);free(result->text);
  exr_books_free(result->books,result->book_count);
  for(i=0;i<result->note_count;i++) free(result->notes[i].text);
  free(result->notes);memset(result,0,sizeof(*result));
}
exr_status linux_reader_open(const char *database,const char *font,const exr_control *control,
                            linux_reader **out,exr_error *error) {
  linux_reader *reader=calloc(1,sizeof(*reader));exr_status status;
  *out=NULL;if(!reader) return EXR_MEMORY;
#ifdef EXR_READER_PRODUCT_CATALOG
  reader->catalog_lock=-1;
  size_t path_size=strlen(database)+32;
  reader->catalog_path=malloc(path_size);
  char *lock_path=malloc(path_size);
  if(!reader->catalog_path || !lock_path) { free(lock_path);linux_reader_close(reader);return EXR_MEMORY; }
  snprintf(reader->catalog_path,path_size,"%s.product.sqlite",database);
  snprintf(lock_path,path_size,"%s.product.lock",database);
  reader->catalog_lock=open(lock_path,O_CREAT|O_RDWR|O_CLOEXEC,0600);free(lock_path);
  if(reader->catalog_lock<0 || flock(reader->catalog_lock,LOCK_EX|LOCK_NB)) {
    if(error) { error->code=EXR_IO;snprintf(error->message,sizeof(error->message),"This local library is already in use or cannot be locked"); }
    linux_reader_close(reader);return EXR_IO;
  }
#endif
  if(control) reader->control=*control;
  status=exr_library_open(database,&reader->library,error);
  if(status==EXR_OK) status=exr_font_open(font,&reader->font,error);
  if(status!=EXR_OK) { linux_reader_close(reader);return status; }
  *out=reader;return EXR_OK;
}
void linux_reader_close(linux_reader *reader) {
  if(reader) {
    pending_discard(reader);
    session_free(&reader->current);exr_font_free(reader->font);
    exr_library_close(reader->library);
#ifdef EXR_READER_PRODUCT_CATALOG
    reader_catalog_close(&reader->catalog,NULL);
    free(reader->catalog_path);
    if(reader->catalog_lock>=0) close(reader->catalog_lock);
#endif
    free(reader);
  }
}
static exr_status cancel(linux_reader *reader) {
  return reader->control.cancelled && reader->control.cancelled(reader->control.context) ? EXR_CANCELLED:EXR_OK;
}
#ifdef EXR_READER_PRODUCT_CATALOG
static void product_refresh(linux_reader *reader,reader_result *result) {
  reader_catalog_error product_error={0};exr_error error={0};size_t failed=0;
  if(!reader->catalog && reader_catalog_open(reader->catalog_path,&reader->catalog,&product_error)!=0) {
    snprintf(result->message,sizeof(result->message),"Books saved locally; catalog unavailable, retry by reopening a book");
    fprintf(stderr,"Product catalog open: %s\n",product_error.message);return;
  }
  exr_status status=reader_catalog_sdk_repair(reader->catalog,reader->library,result->books,
    result->book_count,&reader->control,&failed,&error);
  if(status!=EXR_OK) {
    snprintf(result->message,sizeof(result->message),"Books saved locally; catalog repair pending");
    fprintf(stderr,"Product catalog repair: code=%d failures=%zu %s\n",(int)status,failed,error.message);
  }
}
#endif
static size_t extent(reader_session *session) {
  size_t size=0;
  if(session->bounded) return exr_pager_chapter_statistics(session->pager).projection_bytes;
  exr_document_text(session->document,&size);return size;
}
static const char *route(reader_session *session,size_t part) {
  if(!session->publication) return NULL;
  size_t count=0;const exr_part *parts=exr_publication_parts(session->publication,&count);
  return part<count && parts[part].in_reading_order ? parts[part].path:NULL;
}
static exr_status pager_create(linux_reader *reader,reader_session *session,size_t part,int size,
                               exr_pager **out,exr_error *error) {
  exr_layout_config config=exr_layout_config_defaults();exr_status status;
  config.page=(exr_layout_options){520,640,28,(float)size,1.5f,8};config.control=reader->control;
  if(session->bounded) {
    exr_chapter_options options=exr_chapter_options_defaults();options.window_bytes=16384;
    status=exr_publication_pager_create(session->publication,part,reader->font,&config,&options,out,error);
  } else status=exr_pager_create(session->document,reader->font,&config,out,error);
  if(status==EXR_OK) status=exr_pager_set_cache(*out,3,8u*1024u*1024u,error);
  return status;
}
typedef struct { char *bytes;size_t size,capacity; } text_copy;
static exr_status append_text(void *context,const char *text,size_t size,exr_error *error) {
  text_copy *copy=context;(void)error;
  if(size>copy->capacity-copy->size) return EXR_LIMIT;
  memcpy(copy->bytes+copy->size,text,size);copy->size+=size;return EXR_OK;
}
static exr_status render_fixed(linux_reader *reader,reader_session *session,size_t index,
                               reader_result *result,exr_error *error) {
  size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(session->fixed_document,&count);
  exr_viewport viewport={0};exr_bitmap bitmap={0};exr_fixed_text *text=NULL;
  exr_fixed_render_options options={0};exr_status status;
  if(!pages || index>=count) return EXR_ARGUMENT;
  status=exr_viewport_create(&pages[index].geometry,1,&viewport,error);
  if(status!=EXR_OK) return status;
  double dimension=fmax(viewport.width,viewport.height);
  if(!(dimension>0) || !isfinite(dimension)) return EXR_FORMAT;
  double scale=fmin(1.0,1080.0/dimension)*(double)session->zoom/100.0;
  if(!(scale>0) || !isfinite(scale) || viewport.width*scale>2048 || viewport.height*scale>2048) {
    snprintf(result->message,sizeof(result->message),"Zoom exceeds this host's 2048-pixel page limit; previous page retained");
    return EXR_LIMIT;
  }
  options.channels=4;options.background=0xffffffffu;options.mask_budget=16u*1024u*1024u;
  options.control=reader->control;
  status=exr_fixed_render(session->fixed_document,index,scale,&options,&bitmap,error);
  if(status!=EXR_OK) return status;
  if(bitmap.channels!=4 || !bitmap.width || !bitmap.height || bitmap.width>2048 || bitmap.height>2048) {
    exr_bitmap_free(&bitmap);return EXR_LIMIT;
  }
  status=exr_fixed_load_text(session->fixed_document,index,&reader->control,&text,error);
  const char *bytes="";size_t size=0;
  if(status==EXR_OK) bytes=exr_fixed_text_string(text,&size);
  else if(status==EXR_UNSUPPORTED) { status=EXR_OK;if(error) memset(error,0,sizeof(*error)); }
  if(status!=EXR_OK || size>PAGE_TEXT_LIMIT || (!bytes && size)) {
    exr_fixed_text_free(text);exr_bitmap_free(&bitmap);return status!=EXR_OK ? status:EXR_LIMIT;
  }
  result->text=malloc(size+1);result->stride=(size_t)bitmap.width*4;
  result->pixels=malloc(result->stride*(size_t)bitmap.height);
  if(!result->text || !result->pixels) {
    exr_fixed_text_free(text);exr_bitmap_free(&bitmap);return EXR_MEMORY;
  }
  if(size) memcpy(result->text,bytes,size);
  result->text[size]=0;result->text_size=size;
  for(size_t y=0;y<bitmap.height;y++) memcpy(result->pixels+y*result->stride,
    bitmap.pixels+y*bitmap.stride,result->stride);
  result->width=bitmap.width;result->height=bitmap.height;
  exr_fixed_text_free(text);exr_bitmap_free(&bitmap);
  result->book=session->id;result->font=session->font;result->fixed=1;result->zoom=session->zoom;
  result->page=index;result->page_count=count;result->start=0;result->end=size;result->has_frame=1;
  session->page=index;session->position=index;
  if(!size) snprintf(result->message,sizeof(result->message),"Page rendered; no selectable text is supplied for this page");
  return EXR_OK;
}
static exr_status render(linux_reader *reader,reader_session *session,size_t index,int seek,size_t offset,
                          reader_result *result,exr_error *error) {
  exr_status status;const exr_layout *layout=NULL;exr_bitmap bitmap={0};
  size_t total=extent(session),i;exr_page page={0};
  for(i=index;i<PAGE_LIMIT;i++) {
    status=cancel(reader);if(status!=EXR_OK) return status;
    status=exr_pager_get(session->pager,i,&layout,error);if(status!=EXR_OK) return status;
    const exr_page *pages=exr_layout_pages(layout,NULL);
    if(!pages || pages[0].start>pages[0].end || pages[0].end>total) return EXR_FORMAT;
    page=pages[0];
    if(!seek || page.end>offset || page.end==total) break;
  }
  if(i==PAGE_LIMIT) return EXR_LIMIT;
  if(page.end-page.start>PAGE_TEXT_LIMIT) return EXR_LIMIT;
  status=exr_render_page_ex(layout,exr_layout_font(layout),0,4,&reader->control,&bitmap,error);
  if(status!=EXR_OK) return status;
  if(bitmap.channels!=4 || !bitmap.width || !bitmap.height || bitmap.width>4096 || bitmap.height>4096) {
    exr_bitmap_free(&bitmap);return EXR_LIMIT;
  }
  result->stride=(size_t)bitmap.width*4;result->width=bitmap.width;result->height=bitmap.height;
  result->pixels=malloc(result->stride*result->height);
  if(!result->pixels) { exr_bitmap_free(&bitmap);return EXR_MEMORY; }
  for(size_t y=0;y<result->height;y++)
    memcpy(result->pixels+y*result->stride,bitmap.pixels+y*bitmap.stride,result->stride);
  exr_bitmap_free(&bitmap);
  result->text_size=page.end-page.start;result->text=malloc(result->text_size+1);
  if(!result->text) return EXR_MEMORY;
  if(session->bounded) {
    text_copy copy={result->text,0,result->text_size};
    status=exr_pager_read_text(session->pager,page.start,page.end,append_text,&copy,&reader->control,error);
    if(status!=EXR_OK) return status;
    if(copy.size!=result->text_size) return EXR_FORMAT;
  } else memcpy(result->text,exr_document_text(session->document,NULL)+page.start,result->text_size);
  result->text[result->text_size]=0;
  result->book=session->id;result->bounded=session->bounded;result->font=session->font;
  result->part=session->part;result->page=i;result->start=page.start;result->end=page.end;
  result->has_frame=1;
  if(session->bounded) result->chapter=exr_pager_chapter_statistics(session->pager);
  return EXR_OK;
}
static exr_status capture(linux_reader *reader,reader_session *session,size_t start,size_t end,
                           exr_anchor *anchor,exr_error *error) {
  return session->bounded ? exr_pager_anchor_create(session->pager,start,end,&reader->control,anchor,error):
    exr_anchor_create(session->document,start,end,anchor,error);
}
static exr_status persist(linux_reader *reader,reader_session *session,size_t position,exr_error *error) {
  exr_epub_location point={0};exr_status status;
  if(session->fixed_document) {
    exr_book update=*session->fixed_book;update.position=session->page;
    return exr_library_update(reader->library,&update,error);
  }
  if(session->hold_progress) return EXR_OK;
  status=capture(reader,session,position,position,&point.selector,error);
  if(status==EXR_OK) {
    if(session->bounded) {
      point.part=session->part;point.path=(char *)route(session,session->part);
      status=point.path ? exr_library_epub_progress(reader->library,session->id,&point,error):EXR_FORMAT;
    } else status=exr_library_progress(reader->library,session->id,&point.selector,error);
  }
  exr_anchor_free(&point.selector);return status;
}
static exr_status note_list(linux_reader *reader,reader_session *session,reader_result *result,exr_error *error) {
  exr_epub_note *bounded=NULL;exr_note *legacy=NULL;exr_fixed_note *fixed=NULL;size_t count=0,i;exr_status status;
  if(session->fixed_document) status=exr_library_fixed_notes(reader->library,session->id,&fixed,&count,error);
  else if(session->bounded) status=exr_library_epub_notes(reader->library,session->id,&bounded,&count,error);
  else status=exr_library_notes(reader->library,session->id,&legacy,&count,error);
  if(status!=EXR_OK) return status;
  if(count>4096) { status=EXR_LIMIT;goto done; }
  result->notes=calloc(count ? count:1,sizeof(*result->notes));
  if(!result->notes) { status=EXR_MEMORY;goto done; }
  for(i=0;i<count;i++) {
    reader_note *note=&result->notes[i];const char *text;
    if(session->fixed_document) {
      note->id=fixed[i].id;note->part=fixed[i].page;
      note->start=fixed[i].start;note->end=fixed[i].end;text=fixed[i].text;
    } else if(session->bounded) {
      note->id=bounded[i].id;note->part=bounded[i].location.part;
      note->start=bounded[i].location.selector.start;note->end=bounded[i].location.selector.end;text=bounded[i].text;
    } else { note->id=legacy[i].id;note->start=legacy[i].start;note->end=legacy[i].end;text=legacy[i].text; }
    note->text=strdup(text ? text:"");result->note_count=i+1;
    if(!note->text) { status=EXR_MEMORY;break; }
  }
done:
  exr_fixed_notes_free(fixed,fixed ? count:0);
  exr_epub_notes_free(bounded,bounded ? count:0);exr_notes_free(legacy,legacy ? count:0);
  return status;
}
static exr_status open_book(linux_reader *reader,int64_t id,int size,int zoom,reader_session *session,
                             reader_result *result,exr_error *error) {
  exr_book *books=NULL;size_t count=0,i;exr_status status;exr_epub_location point={0};int present=0;
  exr_anchor legacy={0};exr_anchor_state legacy_state=EXR_ANCHOR_MISSING;size_t offset=0;
  memset(session,0,sizeof(*session));session->id=id;session->font=size;
  status=exr_library_books(reader->library,"",&books,&count,error);if(status!=EXR_OK) return status;
  for(i=0;i<count && books[i].id!=id;i++) {}
  if(i==count) status=EXR_ARGUMENT;
  else if(books[i].format==EXR_PDF || books[i].format==EXR_CBZ) {
    session->zoom=zoom ? zoom:100;
    if(session->zoom<25 || session->zoom>400) status=EXR_ARGUMENT;
    else {
      session->fixed_book=malloc(sizeof(*session->fixed_book));
      if(!session->fixed_book) status=EXR_MEMORY;
      else { *session->fixed_book=books[i];memset(&books[i],0,sizeof(books[i])); }
    }
  } else if(books[i].format==EXR_EPUB) {
    exr_library_epub_info info={0};info.struct_size=sizeof(info);
    status=exr_library_epub_info_get(reader->library,id,&info,error);session->bounded=info.bounded_storage;
  }
  exr_books_free(books,count);if(status!=EXR_OK) return status;
  if(session->fixed_book) {
    exr_fixed_open_options options={0};options.struct_size=sizeof(options);
    options.fallback_font=reader->font;options.control=reader->control;
    status=exr_library_fixed_source(reader->library,id,&options,&session->fixed_document,error);
    if(status!=EXR_OK) return status;
    size_t pages=0;exr_fixed_pages(session->fixed_document,&pages);
    if(!pages || session->fixed_book->position>=pages) return EXR_FORMAT;
    return render_fixed(reader,session,session->fixed_book->position,result,error);
  }
  if(session->bounded) {
    exr_source source={0};status=exr_library_source(reader->library,id,&source,error);
    if(status==EXR_OK) {
      source.control=reader->control;status=exr_publication_open_source(&source,&session->publication,error);
      if(status!=EXR_OK && source.release) source.release(source.context);
    }
    if(status!=EXR_OK) return status;
    status=exr_library_epub_progress_get(reader->library,id,&point,&present,error);
    if(status!=EXR_OK) goto done;
    if(present) {
      const char *path=route(session,point.part);
      if(!path || !point.path || strcmp(path,point.path)) { status=EXR_FORMAT;goto done; }
      session->part=point.part;
    } else {
      size_t parts=0;const exr_part *routes=exr_publication_parts(session->publication,&parts);
      for(session->part=0;session->part<parts && !routes[session->part].in_reading_order;session->part++) {}
      if(session->part==parts) { status=EXR_FORMAT;goto done; }
    }
  } else {
    status=exr_library_document(reader->library,id,&session->document,error);
    if(status==EXR_OK) status=exr_library_progress_get(reader->library,id,&legacy,&legacy_state,error);
    if(status!=EXR_OK) goto done;
    if(legacy.start!=SIZE_MAX) offset=legacy.start;
  }
  status=pager_create(reader,session,session->part,size,&session->pager,error);
  if(status!=EXR_OK) goto done;
  if(session->bounded && present) {
    exr_anchor_match match;
    status=exr_pager_anchor_resolve(session->pager,&point.selector,&reader->control,&match,error);
    if(status!=EXR_OK) goto done;
    if(match.state==EXR_ANCHOR_FOUND) offset=match.start;
    else {
      exr_anchor verified={0};
      status=exr_pager_anchor_create(session->pager,point.selector.start,point.selector.start,
                                     &reader->control,&verified,error);
      exr_anchor_free(&verified);if(status!=EXR_OK) goto done;
      offset=point.selector.start;
      session->hold_progress=1;
      strcpy(result->message,"Position not unique; saved chapter offset shown, original point retained");
    }
  }
  status=render(reader,session,0,1,offset,result,error);
  if(status==EXR_OK) session->position=offset;
done:
  exr_epub_location_free(&point);exr_anchor_free(&legacy);return status;
}
static size_t file_read(void *context,size_t offset,void *bytes,size_t size) {
  FILE *file=context;if(fseeko(file,(off_t)offset,SEEK_SET)) return 0;return fread(bytes,1,size,file);
}
static exr_format file_format(const char *path) {
  const char *ext=strrchr(path,'.');if(!ext) return EXR_CUSTOM;
  const char *names[]={".epub",".txt",".html",".xhtml",".fb2",".rtf",".docx",".mobi",".pdf",".cbz"};
  const exr_format formats[]={EXR_EPUB,EXR_TXT,EXR_HTML,EXR_HTML,EXR_FB2,EXR_RTF,EXR_DOCX,EXR_MOBI,EXR_PDF,EXR_CBZ};
  for(size_t i=0;i<sizeof(formats)/sizeof(formats[0]);i++) if(!strcasecmp(ext,names[i])) return formats[i];
  return EXR_CUSTOM;
}
static exr_status import_pdf(linux_reader *reader,FILE *input,size_t size,const char *title,
                             int64_t *id,int *created,exr_error *error) {
  /* The public PDF file API reopens its path. Snapshot the chooser's mutable
     file into an unlinked private file and keep its descriptor alive throughout. */
  if(size>32u*1024u*1024u) return EXR_LIMIT;
  exr_status status=cancel(reader);if(status!=EXR_OK) return status;
  FILE *copy=tmpfile();if(!copy) return EXR_IO;
  if(fseeko(input,0,SEEK_SET)) { fclose(copy);return EXR_IO; }
  unsigned char bytes[65536];size_t offset=0;
  while(offset<size) {
    size_t count=size-offset;if(count>sizeof(bytes)) count=sizeof(bytes);
    status=cancel(reader);if(status!=EXR_OK) break;
    if(fread(bytes,1,count,input)!=count || fwrite(bytes,1,count,copy)!=count) { status=EXR_IO;break; }
    offset+=count;
  }
  if(status==EXR_OK && fflush(copy)) status=EXR_IO;
  if(status==EXR_OK) status=cancel(reader);
  if(status==EXR_OK) {
    char stable[64];snprintf(stable,sizeof(stable),"/proc/self/fd/%d",fileno(copy));
    status=exr_library_import_file_unique(reader->library,EXR_PDF,stable,title,id,created,error);
  }
  fclose(copy);return status;
}
static exr_status import_book(linux_reader *reader,const char *path,int64_t *id,exr_error *error) {
  exr_format format=file_format(path);exr_status status;FILE *file;off_t length;int created=0;
  if(format==EXR_CUSTOM) return EXR_UNSUPPORTED;
  file=fopen(path,"rb");if(!file) return EXR_IO;
  if(fseeko(file,0,SEEK_END) || (length=ftello(file))<=0) { fclose(file);return EXR_IO; }
  const char *title=strrchr(path,'/');title=title ? title+1:path;
  if(format==EXR_EPUB || format==EXR_CBZ) {
    exr_source source={0};source.size=(size_t)length;source.context=file;source.read_at=file_read;
    source.control=reader->control;
    status=exr_library_import_source_unique(reader->library,format,&source,title,id,&created,error);
  } else if(format==EXR_PDF) {
    status=import_pdf(reader,file,(size_t)length,title,id,&created,error);
  } else if(length>LEGACY_INPUT_LIMIT) status=EXR_LIMIT;
  else {
    size_t size=(size_t)length;unsigned char *bytes=malloc(size);
    if(!bytes) status=EXR_MEMORY;
    else {
      status=file_read(file,0,bytes,size)==size ? cancel(reader):EXR_IO;
      if(status==EXR_OK) status=exr_library_import_unique(reader->library,format,bytes,size,title,id,&created,error);
      free(bytes);
    }
  }
  fclose(file);
  if(status==EXR_OK && cancel(reader)!=EXR_OK) {
    status=created ? exr_library_delete(reader->library,*id,error):EXR_OK;
    if(status==EXR_OK) status=EXR_CANCELLED;
  }
  return status;
}
static exr_status move_part(linux_reader *reader,reader_session *session,int direction,exr_error *error) {
  size_t count=0;const exr_part *parts=exr_publication_parts(session->publication,&count);size_t part=session->part;
  for(;;) {
    if(direction>0) { if(part+1>=count) return EXR_ARGUMENT;part++; }
    else { if(!part) return EXR_ARGUMENT;part--; }
    if(parts[part].in_reading_order) break;
  }
  session->pager=NULL;
  exr_status status=pager_create(reader,session,part,session->font,&session->pager,error);
  if(status==EXR_OK) session->part=part;
  return status;
}
static exr_status jump_note(linux_reader *reader,reader_session *session,int64_t id,reader_result *result,exr_error *error) {
  exr_epub_note *bounded=NULL;exr_note *legacy=NULL;exr_fixed_note *fixed=NULL;
  exr_fixed_text *text=NULL;size_t count=0,i;exr_status status;
  const exr_anchor *anchor=NULL;exr_anchor_match match;
  if(session->fixed_document) {
    status=exr_library_fixed_notes(reader->library,session->id,&fixed,&count,error);
    if(status!=EXR_OK) return status;
    for(i=0;i<count && fixed[i].id!=id;i++) {}
    if(i==count) { status=EXR_ARGUMENT;goto done; }
    size_t pages_count=0;
    const exr_fixed_page *pages=exr_fixed_pages(session->fixed_document,&pages_count);
    if(!pages || fixed[i].page>=pages_count) { status=EXR_ARGUMENT;goto done; }
    status=exr_fixed_load_text(session->fixed_document,fixed[i].page,&reader->control,&text,error);
    if(status==EXR_OK) status=exr_fixed_anchor_resolve(pages[fixed[i].page].id,text,
      &fixed[i].anchor,&reader->control,&match,error);
    if(status==EXR_OK && match.state!=EXR_ANCHOR_FOUND) {
      strcpy(result->message,"Note quote is missing or ambiguous; location unchanged");status=EXR_ARGUMENT;
    }
    if(status==EXR_OK) {
      status=render_fixed(reader,session,fixed[i].page,result,error);
      if(status==EXR_OK) {
        result->select_range=1;result->selected_start=match.start;result->selected_end=match.end;
      }
    }
    goto done;
  } else if(session->bounded) {
    status=exr_library_epub_notes(reader->library,session->id,&bounded,&count,error);
    if(status!=EXR_OK) return status;
    for(i=0;i<count && bounded[i].id!=id;i++) {}
    if(i==count) { status=EXR_ARGUMENT;goto done; }
    const char *path=route(session,bounded[i].location.part);
    if(!path || strcmp(path,bounded[i].location.path)) { status=EXR_FORMAT;goto done; }
    session->part=bounded[i].location.part;session->pager=NULL;
    status=pager_create(reader,session,session->part,session->font,&session->pager,error);
    if(status!=EXR_OK) goto done;
    anchor=&bounded[i].location.selector;
    status=exr_pager_anchor_resolve(session->pager,anchor,&reader->control,&match,error);
  } else {
    status=exr_library_notes(reader->library,session->id,&legacy,&count,error);
    if(status!=EXR_OK) return status;
    for(i=0;i<count && legacy[i].id!=id;i++) {}
    if(i==count) { status=EXR_ARGUMENT;goto done; }
    anchor=&legacy[i].anchor;status=exr_anchor_resolve_ex(session->document,anchor,&reader->control,&match,error);
  }
  if(status==EXR_OK && match.state!=EXR_ANCHOR_FOUND) {
    strcpy(result->message,"Note quote is missing or ambiguous; location unchanged");status=EXR_ARGUMENT;
  }
  if(status==EXR_OK) {
    status=render(reader,session,0,1,match.start,result,error);
    if(status==EXR_OK) session->position=match.start;
    result->select_range=1;result->selected_start=match.start;result->selected_end=match.end;
  }
done:
  exr_fixed_text_free(text);exr_fixed_notes_free(fixed,fixed ? count:0);
  exr_epub_notes_free(bounded,bounded ? count:0);exr_notes_free(legacy,legacy ? count:0);
  return status;
}
void linux_reader_execute(linux_reader *reader,const reader_command *command,reader_result *result) {
  reader_session next=reader->current;exr_error error={0};exr_status status=cancel(reader);
  int owned_session=0,new_pager=0;int64_t id=command->book;size_t target=0;
  int wants_shelf=command->action==READER_SHELF || command->action==READER_OPEN || command->action==READER_IMPORT;
  memset(result,0,sizeof(*result));
  if(command->action==READER_COMMIT) {
    /* The GTK acceptance callback queues this before subsequent operations.
       A stale result never queues it; close waits for its outcome. */
    reader_session *pending=&reader->pending;
    status=reader->has_pending && pending->id==command->book && pending->part==command->part &&
      pending->start==command->start && (!pending->fixed_document || pending->page==command->page) ?
      persist(reader,pending,pending->position,&error):EXR_ARGUMENT;
    if(status==EXR_OK) {
      if(reader->pending_owns_session) session_free(&reader->current);
      else if(reader->pending_new_pager) exr_pager_free(reader->current.pager);
      reader->current=*pending;memset(pending,0,sizeof(*pending));
      reader->has_pending=reader->pending_owns_session=reader->pending_new_pager=0;
    }
    goto done;
  }
  pending_discard(reader);
  if(status!=EXR_OK) goto done;
  if(command->action==READER_SHELF) goto done;
  if(command->action==READER_IMPORT || command->action==READER_OPEN) {
    if(command->action==READER_IMPORT) status=import_book(reader,command->path,&id,&error);
    if(status!=EXR_OK) goto done;
    owned_session=1;memset(&next,0,sizeof(next));
    status=open_book(reader,id,command->font,command->zoom,&next,result,&error);
  } else if((!next.pager && !next.fixed_document) || next.id!=command->book ||
            (next.bounded && next.part!=command->part) ||
            (next.fixed_document && next.page!=command->page)) status=EXR_ARGUMENT;
  else if(command->action==READER_NOTE_ADD) {
    exr_epub_note note={0};exr_note old={0};int64_t saved=0;
    if(command->start<next.start || command->end>next.end || command->start>=command->end) status=EXR_ARGUMENT;
    else {
      note.book_id=next.id;note.text=(char *)command->comment;note.location.part=next.part;
      if(next.fixed_document) {
        exr_fixed_note fixed={0};fixed.book_id=next.id;fixed.page=next.page;
        fixed.start=command->start;fixed.end=command->end;fixed.text=(char *)command->comment;
        status=exr_library_fixed_note(reader->library,&fixed,&reader->control,&saved,&error);
      } else {
        note.location.path=(char *)route(&next,next.part);
        status=capture(reader,&next,command->start,command->end,&note.location.selector,&error);
      }
      if(status==EXR_OK && !next.fixed_document) {
        if(next.bounded) status=exr_library_epub_note(reader->library,&note,&saved,&error);
        else {
          old.book_id=next.id;old.start=command->start;old.end=command->end;
          old.text=note.text;old.anchor=note.location.selector;status=exr_library_note(reader->library,&old,&saved,&error);
        }
      }
      exr_anchor_free(&note.location.selector);
      result->selected_start=command->start;result->selected_end=command->end;
    }
  } else if(command->action==READER_NOTE_REMOVE) {
    /* Commands carry the selected current-book ID; recheck ownership on worker. */
    reader_result entries={0};status=note_list(reader,&next,&entries,&error);
    if(status==EXR_OK) {
      size_t i;for(i=0;i<entries.note_count && entries.notes[i].id!=command->note;i++) {}
      if(i==entries.note_count) status=EXR_ARGUMENT;
      else status=next.fixed_document ? exr_library_remove_fixed_note(reader->library,command->note,&error):
        next.bounded ? exr_library_remove_epub_note(reader->library,command->note,&error):
        exr_library_remove_note(reader->library,command->note,&error);
    }
    reader_result_free(&entries);
  } else if(command->action==READER_NOTE_JUMP) {
    status=jump_note(reader,&next,command->note,result,&error);new_pager=next.pager!=reader->current.pager;
  } else if(command->action==READER_ZOOM) {
    if(!next.fixed_document || command->zoom<25 || command->zoom>400) status=EXR_ARGUMENT;
    else { next.zoom=command->zoom;status=render_fixed(reader,&next,next.page,result,&error); }
  } else if(command->action==READER_FONT && next.fixed_document) status=EXR_ARGUMENT;
  else if(command->action==READER_FONT) {
    exr_anchor point={0};exr_anchor_match match;size_t position=next.position;
    if(command->font<12 || command->font>48) status=EXR_ARGUMENT;
    else status=capture(reader,&next,position,position,&point,&error);
    if(status==EXR_OK) {
      next.pager=NULL;new_pager=1;status=pager_create(reader,&next,next.part,command->font,&next.pager,&error);
    }
    if(status==EXR_OK) {
      status=next.bounded ? exr_pager_anchor_resolve(next.pager,&point,&reader->control,&match,&error):
        exr_anchor_resolve_ex(next.document,&point,&reader->control,&match,&error);
      if(status==EXR_OK && match.state==EXR_ANCHOR_FOUND) position=match.start;
      else if(status==EXR_OK) {
        next.hold_progress=1;strcpy(result->message,"Position not unique; retained chapter offset, stored point unchanged");
      }
    }
    if(status==EXR_OK && position>extent(&next)) status=EXR_ARGUMENT;
    if(status==EXR_OK) {
      next.font=command->font;status=render(reader,&next,0,1,position,result,&error);next.position=position;
    }
    exr_anchor_free(&point);
  } else if((command->action==READER_NEXT || command->action==READER_PREVIOUS) && next.fixed_document) {
    size_t count=0;exr_fixed_pages(next.fixed_document,&count);
    int previous=command->action==READER_PREVIOUS;
    if((previous && !next.page) || (!previous && next.page+1>=count)) status=EXR_ARGUMENT;
    else status=render_fixed(reader,&next,previous ? next.page-1:next.page+1,result,&error);
  } else if(command->action==READER_NEXT || command->action==READER_PREVIOUS) {
    int previous=command->action==READER_PREVIOUS;
    next.hold_progress=0;
    if((previous && !next.page) || (!previous && next.end==extent(&next))) {
      if(!next.bounded) status=EXR_ARGUMENT;
      else {
        status=move_part(reader,&next,previous ? -1:1,&error);new_pager=next.pager!=reader->current.pager;
        if(status==EXR_OK) status=render(reader,&next,0,previous,previous ? extent(&next):0,result,&error);
      }
    } else {
      target=previous ? next.page-1:next.page+1;status=render(reader,&next,target,0,0,result,&error);
    }
    if(status==EXR_OK) next.position=result->start;
  } else status=EXR_ARGUMENT;
  if(status==EXR_OK) status=note_list(reader,&next,result,&error);
  if(status==EXR_OK && wants_shelf) {
    status=exr_library_books(reader->library,"",&result->books,&result->book_count,&error);
    result->has_shelf=status==EXR_OK;
  }
  if(status==EXR_OK) status=cancel(reader);
  if(status==EXR_OK && result->has_frame) {
    next.page=result->page;next.start=result->start;next.end=result->end;
    result->position=next.position;reader->pending=next;reader->has_pending=1;
    reader->pending_owns_session=owned_session;reader->pending_new_pager=new_pager;
    owned_session=new_pager=0;
  }
done:
  if(owned_session) session_free(&next);
  else if(new_pager) exr_pager_free(next.pager);
  if(status!=EXR_OK) result->has_frame=0;
  result->status=status;
  if(!result->message[0]) strcpy(result->message,status==EXR_OK ? "Ready":"Reading operation failed; accepted page retained");
  /* A committed import remains visible even when its first chapter is bad. */
  exr_status listing=EXR_OK;
  if(wants_shelf && !result->has_shelf) {
    listing=exr_library_books(reader->library,"",&result->books,&result->book_count,&error);
    result->has_shelf=listing==EXR_OK;
  }
  if(listing!=EXR_OK && result->status==EXR_OK) { result->status=listing;result->has_frame=0; }
#ifdef EXR_READER_PRODUCT_CATALOG
  /* Publication/compensation has completed. Reuse this shelf snapshot on the
     existing owner worker; metadata failure never deletes a committed book. */
  if(result->has_shelf) product_refresh(reader,result);
#endif
}
