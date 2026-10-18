/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <miniz.h>

typedef struct { char *name; mz_uint index; uint32_t width,height; } comic_page;
typedef struct {
  mz_zip_archive zip; exr_source source; unsigned char *data;
  comic_page *pages; size_t count;
  exr_metadata_entry *metadata; size_t metadata_count;
  const exr_control *control; exr_error io_error;
} comic;
static unsigned lower(unsigned c) { return c>='A' && c<='Z' ? c+32 : c; }
static int equal(const char *a,const char *b) {
  while(*a && lower((unsigned char)*a)==lower((unsigned char)*b)) { a++;b++; }
  return !*a && !*b;
}
static int image_kind(const char *name) {
  const char *ext=strrchr(name,'.'); if(!ext) return 0;
  if(equal(ext,".png") || equal(ext,".jpg") || equal(ext,".jpeg")) return 1;
  return equal(ext,".gif") || equal(ext,".webp") || equal(ext,".bmp") || equal(ext,".avif") || equal(ext,".tif") || equal(ext,".tiff") ? -1 : 0;
}
static int digit(unsigned c) { return c>='0' && c<='9'; }
static int compare_pages(const void *left,const void *right) {
  const char *a=((const comic_page *)left)->name,*b=((const comic_page *)right)->name,*original_a=a,*original_b=b;
  while(*a && *b) {
    if(digit((unsigned char)*a) && digit((unsigned char)*b)) {
      const char *ae,*be; size_t an,bn; int order;
      while(*a=='0') a++;
      while(*b=='0') b++;
      ae=a;be=b;while(digit((unsigned char)*ae)) ae++;while(digit((unsigned char)*be)) be++;
      an=(size_t)(ae-a);bn=(size_t)(be-b);if(an!=bn) return an<bn ? -1 : 1;
      order=memcmp(a,b,an);if(order) return order;
      a=ae;b=be;
    } else {
      unsigned x=lower((unsigned char)*a),y=lower((unsigned char)*b);
      if(x!=y) return x<y ? -1 : 1;
      a++;b++;
    }
  }
  if(*a || *b) return *a ? 1 : -1;
  return strcmp(original_a,original_b);
}
static void release(void *context) {
  comic *d=context;size_t i;if(!d) return;
  mz_zip_reader_end(&d->zip);
  if(d->source.release) d->source.release(d->source.context);
  for(i=0;i<d->count;i++) free(d->pages[i].name);
  exr_metadata_free(d->metadata,d->metadata_count);free(d->pages);free(d->data);free(d);
}
static size_t read_source(void *context,mz_uint64 offset,void *buffer,size_t size) {
  comic *d=context;size_t n;
  if(d->io_error.code!=EXR_OK || exr_control_cancel(d->control,&d->io_error)!=EXR_OK) return 0;
  n=d->source.read_at(d->source.context,offset,buffer,size);
  if(n!=size) exr_fail(&d->io_error,EXR_IO,"Cannot read CBZ archive source");
  return n;
}
static exr_status archive_error(comic *d,exr_error *e,const char *message) {
  if(d->io_error.code!=EXR_OK) { if(e) *e=d->io_error;return d->io_error.code; }
  return exr_fail(e,EXR_FORMAT,"%s",message);
}
static exr_status header(comic *d,comic_page *page,size_t size,size_t *work,exr_error *e) {
  mz_zip_reader_extract_iter_state *iter;unsigned char *data;size_t n=0,limit=size<1048576 ? size : 1048576,capacity=limit<4096 ? limit : 4096;exr_status status=EXR_FORMAT;
  iter=mz_zip_reader_extract_iter_new(&d->zip,page->index,0);
  if(!iter) return archive_error(d,e,"Cannot open CBZ image stream");
  data=malloc(capacity);if(!data) { mz_zip_reader_extract_iter_free(iter);return exr_fail(e,EXR_MEMORY,"CBZ header allocation failed"); }
  while(n<limit) {
    size_t chunk,got;
    if(n==capacity) {
      size_t next=capacity*2;unsigned char *grown;if(next>limit) next=limit;
      grown=realloc(data,next);if(!grown) { status=exr_fail(e,EXR_MEMORY,"CBZ header growth failed");break; }
      data=grown;capacity=next;
    }
    chunk=capacity-n;if(chunk>4096) chunk=4096;
    if(chunk>(size_t)64*1024*1024-*work) { status=exr_fail(e,EXR_LIMIT,"CBZ image headers exceed 64 MiB work budget");break; }
    status=exr_control_cancel(d->control,e);if(status!=EXR_OK) break;
    got=mz_zip_reader_extract_iter_read(iter,data+n,chunk);*work+=got;n+=got;
    if(!got) { status=archive_error(d,e,"Truncated CBZ image header");break; }
    status=exr_image_dimensions(data,n,&page->width,&page->height,e);
    if(status!=EXR_FORMAT) break;
  }
  if(status==EXR_FORMAT && n==limit && limit<size) status=exr_fail(e,EXR_LIMIT,"CBZ image header exceeds 1 MiB");
  /* An incomplete iterator has not checked CRC yet; full rendering does. */
  { mz_bool valid=mz_zip_reader_extract_iter_free(iter);if(n==size && !valid && status==EXR_OK) status=archive_error(d,e,"Invalid CBZ image CRC"); }
  free(data);return status;
}
static exr_status member(comic *d,mz_uint index,size_t maximum,void **out,size_t *size,exr_error *e) {
  mz_zip_archive_file_stat st;*out=NULL;*size=0;
  if(!mz_zip_reader_file_stat(&d->zip,index,&st) || !mz_zip_reader_is_file_supported(&d->zip,index)) return archive_error(d,e,"Unsupported CBZ member");
  if(!st.m_uncomp_size || st.m_uncomp_size>maximum) return exr_fail(e,EXR_LIMIT,"CBZ member exceeds byte limit");
  if(exr_control_cancel(d->control,e)!=EXR_OK) return EXR_CANCELLED;
  *out=mz_zip_reader_extract_to_heap(&d->zip,index,size,0);
  if(!*out) return archive_error(d,e,"Invalid CBZ member data or CRC");
  if(exr_control_cancel(d->control,e)!=EXR_OK) { mz_free(*out);*out=NULL;*size=0;return EXR_CANCELLED; }
  return EXR_OK;
}
static exr_status metadata_entry(comic *d,const char *key,const char *value,size_t size,exr_error *e) {
  char *k,*v;exr_metadata_entry *entries;
  if(!size) return EXR_OK;
  if(size>65536 || d->metadata_count==128) return exr_fail(e,EXR_LIMIT,"CBZ metadata exceeds field budget");
  k=exr_copy(key,strlen(key));v=exr_copy(value,size);
  if(!k || !v) { free(k);free(v);return exr_fail(e,EXR_MEMORY,"CBZ metadata allocation failed"); }
  entries=realloc(d->metadata,(d->metadata_count+1)*sizeof(*entries));
  if(!entries) { free(k);free(v);return exr_fail(e,EXR_MEMORY,"CBZ metadata directory allocation failed"); }
  d->metadata=entries;d->metadata[d->metadata_count++]=(exr_metadata_entry){k,v};return EXR_OK;
}
static exr_status comic_info(comic *d,mz_uint index,exr_error *e) {
  void *data=NULL;size_t size=0,i;exr_document *tree=NULL;exr_status status=member(d,index,1048576,&data,&size,e);
  if(status==EXR_OK) status=exr_xml_memory_tree(data,size,"ComicInfo",&tree,e);
  mz_free(data);if(status!=EXR_OK) return status;
  for(i=0;i<tree->node_count && status==EXR_OK;i++) {
    const exr_node *node=tree->nodes+i;const char *key=NULL;char custom[256];size_t child;exr_buffer text={0};
    if(!node->name || node->parent>=tree->node_count || !tree->nodes[node->parent].name || strcmp(tree->nodes[node->parent].name,"ComicInfo")) continue;
    if(!strcmp(node->name,"Title")) key="http://purl.org/dc/terms/title";
    else if(!strcmp(node->name,"Writer")) key="http://purl.org/dc/terms/creator";
    else if(!strcmp(node->name,"Summary")) key="http://purl.org/dc/terms/description";
    else if(!strcmp(node->name,"LanguageISO")) key="http://purl.org/dc/terms/language";
    else if(!strcmp(node->name,"Publisher")) key="http://purl.org/dc/terms/publisher";
    else {
      if(strlen(node->name)>sizeof(custom)-15) { status=exr_fail(e,EXR_LIMIT,"ComicInfo property name exceeds limit");break; }
      snprintf(custom,sizeof(custom),"urn:comicinfo:%s",node->name);key=custom;
    }
    for(child=node->first_child;child!=SIZE_MAX;child=tree->nodes[child].next_sibling) {
      const char *value=tree->nodes[child].text;
      if(value && !exr_append(&text,value,strlen(value))) { status=exr_fail(e,EXR_MEMORY,"ComicInfo text allocation failed");break; }
    }
    if(status==EXR_OK) status=metadata_entry(d,key,text.data ? text.data : "",text.size,e);
    free(text.data);
  }
  exr_document_free(tree);return status;
}
static exr_status draw(void *context,size_t page,const double m[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  comic *d=context;void *data=NULL;size_t size=0;exr_status status;exr_image_layer image={0};double transform[6];comic_page *p=d->pages+page;
  if(!sink->image) return EXR_OK;
  d->control=control;memset(&d->io_error,0,sizeof(d->io_error));
  status=member(d,p->index,(size_t)32*1024*1024,&data,&size,e);
  if(status==EXR_OK) status=exr_image_decode(data,size,&image.bitmap,e);
  mz_free(data);
  if(status==EXR_OK && (image.bitmap.width!=p->width || image.bitmap.height!=p->height)) status=exr_fail(e,EXR_FORMAT,"CBZ page dimensions changed");
  if(status==EXR_OK) status=exr_control_cancel(control,e);
  if(status==EXR_OK) {
    transform[0]=m[0]*p->width;transform[1]=m[1]*p->width;transform[2]=m[2]*p->height;transform[3]=m[3]*p->height;transform[4]=m[4];transform[5]=m[5];
    /* Preserve original pixels for integral, unit-scale page transforms. */
    image.interpolate=!(fabs(m[0])+fabs(m[1])==1 && fabs(m[2])+fabs(m[3])==1 && m[0]*m[2]+m[1]*m[3]==0 &&
      m[0]*m[1]==0 && m[2]*m[3]==0 && floor(m[4])==m[4] && floor(m[5])==m[5]);
    status=sink->image(sink->context,&image,transform,1,e);
  }
  exr_bitmap_free(&image.bitmap);d->control=NULL;return status;
}
static exr_status text(void *context,size_t page,const exr_control *control,exr_fixed_text **out,exr_error *e) {
  (void)context;(void)page;return exr_fixed_text_create("",0,NULL,0,control,out,e);
}
static exr_status metadata(void *context,const exr_control *control,const exr_metadata_entry **out,size_t *count,exr_error *e) {
  comic *d=context;*out=d->metadata;*count=d->metadata_count;return exr_control_cancel(control,e);
}
static exr_status open_comic(comic *d,const char *title,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
  mz_uint i,total,info=UINT_MAX;size_t work=0;exr_fixed_page *pages=NULL;exr_fixed_input input={0};exr_status status=EXR_OK;
  d->control=&options->control;
  if(exr_control_cancel(d->control,e)!=EXR_OK) { status=EXR_CANCELLED;goto done; }
  if(d->data) { if(!mz_zip_reader_init_mem(&d->zip,d->data,(size_t)d->source.size,0)) { status=archive_error(d,e,"Invalid CBZ ZIP archive");goto done; } }
  else { d->zip.m_pRead=read_source;d->zip.m_pIO_opaque=d;if(!mz_zip_reader_init(&d->zip,d->source.size,0)) { status=archive_error(d,e,"Invalid CBZ ZIP source");goto done; } }
  total=mz_zip_reader_get_num_files(&d->zip);
  if(total>10000) { status=exr_fail(e,EXR_LIMIT,"CBZ exceeds 10000 archive members");goto done; }
  d->pages=calloc(total ? total : 1,sizeof(*d->pages));if(!d->pages) { status=exr_fail(e,EXR_MEMORY,"CBZ page directory allocation failed");goto done; }
  for(i=0;i<total;i++) {
    mz_zip_archive_file_stat st;char name[2049];mz_uint length;int kind;size_t at=0;uint32_t cp;
    status=exr_control_poll(d->control,EXR_STAGE_READ,i,total,e);if(status!=EXR_OK) goto done;
    if(!mz_zip_reader_file_stat(&d->zip,i,&st)) { status=archive_error(d,e,"Invalid CBZ member directory");goto done; }
    if(st.m_is_directory) continue;
    length=mz_zip_reader_get_filename(&d->zip,i,name,sizeof(name));
    if(!length || length>sizeof(name)) { status=exr_fail(e,EXR_LIMIT,"CBZ member name exceeds 2048 bytes");goto done; }
    if(strlen(name)!=length-1) { status=exr_fail(e,EXR_FORMAT,"CBZ member name contains NUL");goto done; }
    if(!strncmp(name,"__MACOSX/",9) || name[0]=='.' || strstr(name,"/.")!=NULL) continue;
    kind=image_kind(name);
    if(!kind && !equal(name,"ComicInfo.xml")) continue;
    if(!exr_canonical_path(name)) { status=exr_fail(e,EXR_FORMAT,"Unsafe CBZ member path");goto done; }
    while(at<length-1) if(!exr_next(name,length-1,&at,&cp)) { status=exr_fail(e,EXR_ENCODING,"CBZ member name is not UTF-8");goto done; }
    if(kind<0) { status=exr_fail(e,EXR_FORMAT,"CBZ contains unsupported image format; PNG/JPEG required");goto done; }
    if(!mz_zip_reader_is_file_supported(&d->zip,i)) { status=exr_fail(e,EXR_FORMAT,"Encrypted or unsupported CBZ compression");goto done; }
    if(!kind) { if(info!=UINT_MAX) { status=exr_fail(e,EXR_FORMAT,"Duplicate ComicInfo.xml");goto done; }info=i;continue; }
    if(!st.m_uncomp_size || st.m_uncomp_size>(size_t)32*1024*1024) { status=exr_fail(e,EXR_LIMIT,"CBZ encoded page exceeds 32 MiB");goto done; }
    d->pages[d->count].name=exr_copy(name,length-1);if(!d->pages[d->count].name) { status=exr_fail(e,EXR_MEMORY,"CBZ member name allocation failed");goto done; }
    d->pages[d->count].index=i;d->count++;
    status=header(d,d->pages+d->count-1,(size_t)st.m_uncomp_size,&work,e);if(status!=EXR_OK) goto done;
  }
  if(!d->count) { status=exr_fail(e,EXR_FORMAT,"CBZ contains no PNG/JPEG pages");goto done; }
  qsort(d->pages,d->count,sizeof(*d->pages),compare_pages);
  for(i=1;i<d->count;i++) if(!strcmp(d->pages[i-1].name,d->pages[i].name)) { status=exr_fail(e,EXR_FORMAT,"Duplicate CBZ page path");goto done; }
  if(info!=UINT_MAX) { status=comic_info(d,info,e);if(status!=EXR_OK) goto done; }
  for(i=0;i<d->metadata_count;i++) if(!strcmp(d->metadata[i].key,"http://purl.org/dc/terms/title")) { title=d->metadata[i].value;break; }
  pages=calloc(d->count,sizeof(*pages));if(!pages) { status=exr_fail(e,EXR_MEMORY,"CBZ fixed pages allocation failed");goto done; }
  for(i=0;i<d->count;i++) { pages[i].id=pages[i].label=d->pages[i].name;pages[i].geometry.bounds[2]=d->pages[i].width;pages[i].geometry.bounds[3]=d->pages[i].height;pages[i].geometry.unit_scale=1;pages[i].geometry.y_down=1; }
  input.struct_size=sizeof(input);input.title=title;input.pages=pages;input.page_count=d->count;input.context=d;input.release=release;input.draw=draw;input.text=text;input.metadata=metadata;
  status=exr_control_poll(d->control,EXR_STAGE_READ,total,total,e);
  if(status==EXR_OK) status=exr_fixed_create(&input,out,e);
done:
  d->control=NULL;free(pages);if(status!=EXR_OK) release(d);return status;
}
exr_status exr_cbz_open_owned(unsigned char *data,size_t size,const char *title,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
  comic *d=calloc(1,sizeof(*d));if(!d) { free(data);return exr_fail(e,EXR_MEMORY,"CBZ allocation failed"); }
  d->data=data;d->source.size=size;return open_comic(d,title,options,out,e);
}
exr_status exr_cbz_open_file(const char *path,const char *title,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
  comic *d=calloc(1,sizeof(*d));exr_status status;if(!d) return exr_fail(e,EXR_MEMORY,"CBZ allocation failed");
  status=exr_file_source_limit(path,UINT64_C(2147483648),&d->source,e);
  if(status!=EXR_OK) { release(d);return status; }
  return open_comic(d,title,options,out,e);
}
