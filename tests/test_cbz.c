/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message);exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void *read_file(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb");long n;void *data;CHECK(f && !fseek(f,0,SEEK_END));n=ftell(f);CHECK(n>=0);rewind(f);
  *size=(size_t)n;data=malloc(*size ? *size : 1);CHECK(data && fread(data,1,*size,f)==*size && !fclose(f));return data;
}
static void write_file(const char *path,const void *data,size_t size) { FILE *f=fopen(path,"wb");CHECK(f && fwrite(data,1,size,f)==size && !fclose(f)); }
static void *finish(mz_zip_archive *zip,size_t *size) { void *out=NULL;CHECK(mz_zip_writer_finalize_heap_archive(zip,&out,size));CHECK(mz_zip_writer_end(zip));return out; }
static void begin(mz_zip_archive *zip) { memset(zip,0,sizeof(*zip));CHECK(mz_zip_writer_init_heap(zip,0,0)); }
static void put(mz_zip_archive *zip,const char *name,const void *data,size_t size) { CHECK(mz_zip_writer_add_mem(zip,name,data,size,MZ_NO_COMPRESSION)); }
static int cancelled(void *context) { (void)context;return 1; }
static void pixels(exr_fixed_document *d,size_t page,const exr_bitmap *original) {
  exr_bitmap image={0};unsigned y,x,k;OK(exr_fixed_render(d,page,1,NULL,&image,&error));
  CHECK(image.width==original->width && image.height==original->height && image.channels==4);
  for(y=0;y<image.height;y++) for(x=0;x<image.width;x++) for(k=0;k<3;k++)
    CHECK(image.pixels[(size_t)y*image.stride+x*4+k]==original->pixels[(size_t)y*original->stride+x*4+k]);
  exr_bitmap_free(&image);
}
static void invalid(const char *name,const void *data,size_t size,exr_status expected) {
  mz_zip_archive zip;void *archive;size_t length;exr_fixed_document *d=(void *)1;
  begin(&zip);put(&zip,name,data,size);archive=finish(&zip,&length);
  CHECK(exr_fixed_open_memory(EXR_CBZ,archive,length,NULL,&d,&error)==expected && !d);mz_free(archive);
}
int main(int argc,char **argv) {
  char path[4096],filename[4096],backup[4096];void *png,*jpeg,*archive;size_t png_size,jpeg_size,size,count,i;uint32_t random=7;
  unsigned char rgba[64*64*4];exr_bitmap original={64,64,64*4,rgba,4},jpg={0},image={0};
  mz_zip_archive zip;exr_fixed_document *d=NULL;const exr_fixed_page *pages;exr_fixed_text *text=NULL;exr_metadata_entry *meta=NULL;
  exr_fixed_open_options options={0};exr_library *library=NULL,*restored=NULL;int64_t id,duplicate,note_id;int created;exr_book *books=NULL;exr_fixed_note note={0},*notes=NULL;
  const char *info="<ComicInfo><Title>Comic &amp; \xe4\xb8\xad\xe6\x96\x87</Title><Writer>Writer</Writer><Summary>Example</Summary></ComicInfo>";
  CHECK(argc==3);
  snprintf(path,sizeof(path),"%s/comic.cbz",argv[1]);OK(exr_fixed_open(path,NULL,&d,&error));
  pages=exr_fixed_pages(d,&count);CHECK(count==4 && !strcmp(pages[0].id,"pages/1.PNG") && !strcmp(pages[2].id,"pages/10.png"));
  CHECK(!strcmp(exr_fixed_title(d),"SDK Comic"));OK(exr_fixed_render(d,0,1,NULL,&image,&error));CHECK(image.width==2 && image.height==2);
  CHECK(image.pixels[0]==255 && image.pixels[1]==0 && image.pixels[2]==0 && image.pixels[3]==255 && image.pixels[4]==0 && image.pixels[5]==255);
  exr_bitmap_free(&image);exr_fixed_free(d);d=NULL;
  for(i=0;i<sizeof(rgba);i++) { random=random*1664525u+1013904223u;rgba[i]=i%4==3 ? 255 : (unsigned char)(random>>24); }
  snprintf(path,sizeof(path),"%s/comic-test.png",argv[2]);OK(exr_bitmap_write_png(&original,path,&error));png=read_file(path,&png_size);CHECK(png_size>4096);
  snprintf(path,sizeof(path),"%s/pdf-images/baseline.jpg",argv[1]);jpeg=read_file(path,&jpeg_size);OK(exr_image_decode(jpeg,jpeg_size,&jpg,&error));
  begin(&zip);put(&zip,"Chapter/10.png",png,png_size);put(&zip,"Chapter/2.png",png,png_size);put(&zip,"Chapter/1.png",png,png_size);put(&zip,"Chapter/01.PNG",png,png_size);
  put(&zip,"cover.JPEG",jpeg,jpeg_size);put(&zip,"__MACOSX/._page.png","junk",4);put(&zip,"notes.txt","text",4);put(&zip,"ComicInfo.xml",info,strlen(info));archive=finish(&zip,&size);
  OK(exr_fixed_open_memory(EXR_CBZ,archive,size,NULL,&d,&error));CHECK(!strcmp(exr_fixed_title(d),"Comic & \xe4\xb8\xad\xe6\x96\x87"));
  pages=exr_fixed_pages(d,&count);CHECK(count==5 && !strcmp(pages[0].id,"Chapter/01.PNG") && !strcmp(pages[1].id,"Chapter/1.png") && !strcmp(pages[2].id,"Chapter/2.png") && !strcmp(pages[3].id,"Chapter/10.png"));
  CHECK(pages[0].geometry.y_down==1 && pages[0].geometry.bounds[2]==64 && pages[4].geometry.bounds[2]==jpg.width);
  pixels(d,0,&original);pixels(d,4,&jpg);
  OK(exr_fixed_render(d,1,.5,NULL,&image,&error));CHECK(image.width==32 && image.height==32);exr_bitmap_free(&image);
  OK(exr_fixed_load_text(d,0,NULL,&text,&error));CHECK(exr_fixed_text_string(text,&count) && !count);exr_fixed_text_free(text);
  OK(exr_fixed_load_metadata(d,NULL,&meta,&count,&error));CHECK(count==3 && !strcmp(meta[1].value,"Writer"));exr_metadata_free(meta,count);exr_fixed_free(d);d=NULL;
  snprintf(filename,sizeof(filename),"%s/comic-file.CbZ",argv[2]);write_file(filename,archive,size);
  OK(exr_fixed_open(filename,NULL,&d,&error));pixels(d,2,&original);exr_fixed_free(d);d=NULL;
  options.struct_size=sizeof(options);options.control.cancelled=cancelled;
  CHECK(exr_fixed_open_memory(EXR_CBZ,archive,size,&options,&d,&error)==EXR_CANCELLED && !d);
  CHECK(exr_fixed_open(filename,&options,&d,&error)==EXR_CANCELLED && !d);
  { exr_fixed_render_options render_options={0};render_options.control.cancelled=cancelled;
    OK(exr_fixed_open(filename,NULL,&d,&error));CHECK(exr_fixed_render(d,0,1,&render_options,&image,&error)==EXR_CANCELLED && !image.pixels);
    pixels(d,0,&original);exr_fixed_free(d);d=NULL;
  }
  snprintf(path,sizeof(path),"%s/comic-library.sqlite",argv[2]);snprintf(backup,sizeof(backup),"%s/comic-backup.sqlite",argv[2]);remove(path);remove(backup);OK(exr_library_open(path,&library,&error));
  OK(exr_library_import_unique(library,EXR_CBZ,archive,size,NULL,&id,&created,&error));CHECK(id>0 && created);
  OK(exr_library_import_unique(library,EXR_CBZ,archive,size,NULL,&duplicate,&created,&error));CHECK(duplicate==id && !created);
  OK(exr_library_books(library,NULL,&books,&count,&error));CHECK(count==1 && books[0].format==EXR_CBZ && !strcmp(books[0].author,"Writer"));
  books[0].position=3;books[0].favorite=1;OK(exr_library_update(library,books,&error));exr_books_free(books,count);
  note.book_id=id;note.page=2;note.text="Page bookmark";OK(exr_library_fixed_note(library,&note,NULL,&note_id,&error));
  OK(exr_library_fixed_notes(library,id,&notes,&count,&error));CHECK(count==1 && notes[0].page==2 && !strcmp(notes[0].anchor.page_id,"Chapter/2.png"));exr_fixed_notes_free(notes,count);
  { exr_anchor anchor={0};anchor.exact=anchor.prefix=anchor.suffix="";CHECK(exr_library_progress(library,id,&anchor,&error)==EXR_FORMAT); }
  OK(exr_library_fixed(library,id,NULL,&d,&error));pixels(d,3,&original);exr_fixed_free(d);d=NULL;
  OK(exr_library_backup(library,backup,&error));exr_library_close(library);OK(exr_library_open(backup,&restored,&error));
  OK(exr_library_books(restored,NULL,&books,&count,&error));CHECK(count==1 && books[0].position==3 && books[0].favorite);exr_books_free(books,count);exr_library_close(restored);
  invalid("empty.txt","",0,EXR_FORMAT);invalid("page.webp",png,png_size,EXR_FORMAT);invalid("folder\\page.png",png,png_size,EXR_FORMAT);invalid("page.png","bad",3,EXR_FORMAT);
  invalid("page\xff.png",png,png_size,EXR_ENCODING);
  { unsigned char *extended=calloc(1,jpeg_size+8194);void *large;size_t n;CHECK(extended && jpeg_size>2);
    memcpy(extended,"\xff\xd8\xff\xe1\x20\x00",6);memcpy(extended+8196,(unsigned char *)jpeg+2,jpeg_size-2);
    begin(&zip);put(&zip,"page.jpg",extended,jpeg_size+8194);large=finish(&zip,&n);free(extended);
    OK(exr_fixed_open_memory(EXR_CBZ,large,n,NULL,&d,&error));pixels(d,0,&jpg);exr_fixed_free(d);d=NULL;mz_free(large);
  }
  { const char *invalid_info[]={"<ComicInfo>","<!DOCTYPE ComicInfo [<!ENTITY e SYSTEM 'file:///never-read'>]><ComicInfo><Title>&e;</Title></ComicInfo>","<Wrong/>"};
    for(i=0;i<sizeof(invalid_info)/sizeof(*invalid_info);i++) { void *bad;size_t n;begin(&zip);put(&zip,"page.png",png,png_size);put(&zip,"ComicInfo.xml",invalid_info[i],strlen(invalid_info[i]));bad=finish(&zip,&n);
      CHECK(exr_fixed_open_memory(EXR_CBZ,bad,n,NULL,&d,&error)==EXR_FORMAT && !d);mz_free(bad);
    }
  }
  begin(&zip);put(&zip,"page.png",png,png_size);put(&zip,"page.png",png,png_size);{ void *bad;size_t n;bad=finish(&zip,&n);CHECK(exr_fixed_open_memory(EXR_CBZ,bad,n,NULL,&d,&error)==EXR_FORMAT && !d);mz_free(bad); }
  /* Header-only open succeeds; CRC and image data are validated when painted. */
  { unsigned char *bad=malloc(size);mz_zip_archive reader={0};mz_zip_archive_file_stat st;size_t offset;CHECK(bad);memcpy(bad,archive,size);
    CHECK(mz_zip_reader_init_mem(&reader,bad,size,0) && mz_zip_reader_file_stat(&reader,0,&st));
    offset=(size_t)st.m_local_header_ofs;offset+=30+bad[offset+26]+((size_t)bad[offset+27]<<8)+bad[offset+28]+((size_t)bad[offset+29]<<8);
    CHECK(st.m_uncomp_size>4096);bad[offset+(size_t)st.m_uncomp_size-1]^=1;mz_zip_reader_end(&reader);
    OK(exr_fixed_open_memory(EXR_CBZ,bad,size,NULL,&d,&error));free(bad);
    CHECK(exr_fixed_render(d,3,1,NULL,&image,&error)==EXR_FORMAT && !image.pixels);pixels(d,0,&original);exr_fixed_free(d);d=NULL;
  }
  mz_free(archive);free(png);free(jpeg);exr_bitmap_free(&jpg);printf("%u native CBZ checks passed\n",checks);return 0;
}
