/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include "exr/pdf.h"
#include "graphics_internal.h"
#include <miniz.h>

typedef struct { char *name,*id; mz_uint index; uint32_t frame,width,height; } comic_page;
typedef struct {
  mz_zip_archive zip; exr_source source; unsigned char *data;
  comic_page *pages; size_t count;
  exr_metadata_entry *metadata; size_t metadata_count;
  const exr_control *control; exr_error io_error; int borrowed;
} comic;
static unsigned lower(unsigned c) { return c>='A' && c<='Z' ? c+32 : c; }
static int equal(const char *a,const char *b) {
  while(*a && lower((unsigned char)*a)==lower((unsigned char)*b)) { a++;b++; }
  return !*a && !*b;
}
/* Candidate pages are selected by extension only; the decoder sniffs the
   actual bytes. A supported extension with unsupported/corrupt content is an
   explicit error, not a silently skipped page. */
static int image_kind(const char *name) {
  const char *ext=strrchr(name,'.'); if(!ext) return 0;
  return equal(ext,".png") || equal(ext,".jpg") || equal(ext,".jpeg") || equal(ext,".gif") ||
         equal(ext,".webp") || equal(ext,".bmp") || equal(ext,".avif") || equal(ext,".tif") ||
         equal(ext,".tiff");
}
static int digit(unsigned c) { return c>='0' && c<='9'; }
static int compare_pages(const void *left,const void *right) {
  const comic_page *la=left,*lb=right;
  const char *a=la->name,*b=lb->name,*original_a=a,*original_b=b;
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
  { int order=strcmp(original_a,original_b);if(order) return order; }
  return la->frame < lb->frame ? -1 : la->frame > lb->frame;
}
/* A member stored as "/a.png" and one stored as "a.png" denote the same page
   once the single tolerated leading slash is removed. Neither may displace the
   other, so the pair is an explicit format error rather than an implicit choice.
   Frames of one member share key, name and archive index; an identical pair of
   member names keeps the pre-existing duplicate-path error. */
typedef struct { const char *name,*key; mz_uint index; } page_identity;
static const char *page_key(const char *name) { return name[0]=='/' ? name+1 : name; }
static int compare_identities(const void *left,const void *right) {
  const page_identity *la=left,*lb=right;int order=strcmp(la->key,lb->key);
  if(order) return order;
  return la->index<lb->index ? -1 : la->index>lb->index;
}
static exr_status check_normalized_paths(const comic_page *pages,size_t count,exr_error *e) {
  page_identity *identities;size_t i;
  if(count<2) return EXR_OK;
  identities=malloc(count*sizeof(*identities));
  if(!identities) return exr_fail(e,EXR_MEMORY,"CBZ page identity allocation failed");
  for(i=0;i<count;i++) {
    identities[i].name=pages[i].name;
    identities[i].key=page_key(pages[i].name);
    identities[i].index=pages[i].index;
  }
  qsort(identities,count,sizeof(*identities),compare_identities);
  for(i=1;i<count;i++)
    if(identities[i-1].index!=identities[i].index && !strcmp(identities[i-1].key,identities[i].key)) {
      const char *message=strcmp(identities[i-1].name,identities[i].name)
        ? "Duplicate CBZ member path after leading-slash normalization"
        : "Duplicate CBZ page path or frame id";
      free(identities);
      return exr_fail(e,EXR_FORMAT,"%s",message);
    }
  free(identities);
  return EXR_OK;
}
static void release(void *context) {
  comic *d=context;size_t i;if(!d) return;
  mz_zip_reader_end(&d->zip);
  if(!d->borrowed && d->source.release) d->source.release(d->source.context);
  for(i=0;i<d->count;i++) { free(d->pages[i].name); free(d->pages[i].id); }
  exr_metadata_free(d->metadata,d->metadata_count);free(d->pages);free(d->data);free(d);
}
static size_t read_source(void *context,mz_uint64 offset,void *buffer,size_t size) {
  comic *d=context;size_t done=0;
  if(d->io_error.code!=EXR_OK) return 0;
  if(offset>d->source.size || (uint64_t)size>d->source.size-offset) {
    exr_fail(&d->io_error,EXR_IO,"CBZ source read exceeds its extent");return 0;
  }
  while(done<size) {
    size_t n;
    if(exr_control_cancel(d->control,&d->io_error)!=EXR_OK) return 0;
    n=d->source.read_at(d->source.context,offset+done,(unsigned char *)buffer+done,size-done);
    if(!n || n>size-done) { exr_fail(&d->io_error,EXR_IO,"Cannot read CBZ archive source");return 0; }
    done+=n;
  }
  return done;
}
static exr_status archive_error(comic *d,exr_error *e,const char *message) {
  if(d->io_error.code!=EXR_OK) { if(e) *e=d->io_error;return d->io_error.code; }
  return exr_fail(e,EXR_FORMAT,"%s",message);
}
static unsigned get16(const unsigned char *p) { return (unsigned)p[0]|((unsigned)p[1]<<8); }
static uint32_t get32(const unsigned char *p) { return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static int read_at(comic *d,uint64_t offset,void *buffer,size_t size) {
  if(offset>d->source.size || (uint64_t)size>d->source.size-offset) {
    exr_fail(&d->io_error,EXR_FORMAT,"CBZ member exceeds archive bounds");return 0;
  }
  if(!size) return 1;
  if(d->data) { memcpy(buffer,d->data+(size_t)offset,size);return 1; }
  return read_source(d,offset,buffer,size)==size;
}
/* The local header describes the bytes that follow it; the central directory is
   only an index. Using the central sizes for extraction lets a corrupted index
   truncate the stream, and miniz's iterator can then fail to make progress. */
typedef struct { uint64_t data_ofs;uint32_t csize,usize,crc;unsigned method; } member_layout;
static exr_status member_layout_of(comic *d,const mz_zip_archive_file_stat *st,member_layout *m,exr_error *e) {
  unsigned char lh[30];unsigned flags;
  memset(m,0,sizeof(*m));
  if(st->m_local_header_ofs>d->source.size || d->source.size-st->m_local_header_ofs<sizeof(lh))
    return exr_fail(e,EXR_FORMAT,"CBZ local header exceeds archive bounds");
  if(!read_at(d,st->m_local_header_ofs,lh,sizeof(lh))) return archive_error(d,e,"Cannot read CBZ local header");
  if(get32(lh)!=0x04034b50u) return exr_fail(e,EXR_FORMAT,"Invalid CBZ local header signature");
  flags=get16(lh+6);m->method=get16(lh+8);m->crc=get32(lh+14);m->csize=get32(lh+18);m->usize=get32(lh+22);
  m->data_ofs=st->m_local_header_ofs+sizeof(lh)+get16(lh+26)+get16(lh+28);
  if(flags&8u) {
    /* A data descriptor leaves the local sizes zero; the central directory has them. */
    if(st->m_comp_size>0xffffffffu || st->m_uncomp_size>0xffffffffu)
      return exr_fail(e,EXR_LIMIT,"CBZ member metadata exceeds 32-bit limits");
    m->csize=(uint32_t)st->m_comp_size;m->usize=(uint32_t)st->m_uncomp_size;m->crc=st->m_crc32;
  } else {
    if(m->csize==0xffffffffu || m->usize==0xffffffffu) {
      if(st->m_comp_size>0xffffffffu || st->m_uncomp_size>0xffffffffu)
        return exr_fail(e,EXR_LIMIT,"CBZ member metadata exceeds 32-bit limits");
      m->csize=(uint32_t)st->m_comp_size;m->usize=(uint32_t)st->m_uncomp_size;
    }
    if(!m->csize && st->m_comp_size) m->csize=(uint32_t)st->m_comp_size;
    if(!m->usize && st->m_uncomp_size) m->usize=(uint32_t)st->m_uncomp_size;
  }
  if(m->method!=st->m_method) return exr_fail(e,EXR_FORMAT,"CBZ member method disagrees with the central directory");
  if(m->data_ofs>d->source.size || (uint64_t)m->csize>d->source.size-m->data_ofs)
    return exr_fail(e,EXR_FORMAT,"CBZ member data exceeds archive bounds");
  return EXR_OK;
}
static exr_status member_bytes(comic *d,const mz_zip_archive_file_stat *st,size_t cap,int complete,
                               unsigned char **out,size_t *size,size_t *work,exr_error *e) {
  member_layout m;unsigned char *src=NULL,*dst=NULL;size_t limit,produced=0;exr_status status;
  *out=NULL;*size=0;
  status=member_layout_of(d,st,&m,e);if(status!=EXR_OK) return status;
  if(!m.usize) return exr_fail(e,EXR_FORMAT,"Empty CBZ member");
  limit=m.usize<cap?m.usize:cap;
  if(!limit) return exr_fail(e,EXR_FORMAT,"Empty CBZ member");
  dst=malloc(limit);if(!dst) return exr_fail(e,EXR_MEMORY,"CBZ member allocation failed");
  if(m.method==0) {
    if(m.csize<m.usize) { free(dst);return exr_fail(e,EXR_FORMAT,"Truncated CBZ stored member"); }
    if(!read_at(d,m.data_ofs,dst,limit)) { free(dst);return archive_error(d,e,"Cannot read CBZ member data"); }
    produced=limit;
  } else if(m.method==8) {
    tinfl_decompressor dec;size_t in_pos=0;
    if(m.csize>(uint32_t)64*1024*1024) { free(dst);return exr_fail(e,EXR_LIMIT,"CBZ compressed member exceeds 64 MiB"); }
    src=malloc(m.csize?m.csize:1);if(!src) { free(dst);return exr_fail(e,EXR_MEMORY,"CBZ member allocation failed"); }
    if(!read_at(d,m.data_ofs,src,m.csize)) { free(src);free(dst);return archive_error(d,e,"Cannot read CBZ member data"); }
    tinfl_init(&dec);
    for(;;) {
      size_t in_avail=(size_t)m.csize-in_pos,out_avail=limit-produced;
      size_t consumed,made;
      tinfl_status ts=tinfl_decompress(&dec,src+in_pos,&in_avail,dst,dst+produced,&out_avail,
        TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF|((in_pos<m.csize)?TINFL_FLAG_HAS_MORE_INPUT:0));
      consumed=in_avail;made=out_avail;
      in_pos+=consumed;produced+=made;if(work) *work+=made;
      if(ts==TINFL_STATUS_DONE) break;
      if(produced==limit) break;
      if(ts==TINFL_STATUS_FAILED || ts==TINFL_STATUS_FAILED_CANNOT_MAKE_PROGRESS) {
        status=exr_fail(e,EXR_FORMAT,"Invalid or truncated CBZ image stream");break;
      }
      if(!consumed && !made) { status=exr_fail(e,EXR_FORMAT,"Truncated CBZ image stream");break; }
    }
    free(src);
    if(status==EXR_OK && complete && produced!=m.usize) status=exr_fail(e,EXR_FORMAT,"CBZ member size mismatch");
  } else {
    free(dst);return exr_fail(e,EXR_FORMAT,"Unsupported CBZ member compression");
  }
  if(status==EXR_OK && complete && mz_crc32(0,dst,(size_t)produced)!=(mz_uint32)m.crc) {
    free(dst);return archive_error(d,e,"Invalid CBZ member CRC");
  }
  if(status!=EXR_OK) { free(dst);return status; }
  *out=dst;*size=produced;return EXR_OK;
}
static int full_header(const char *name) {
  const char *ext=strrchr(name,'.'); if(!ext) return 0;
  return equal(ext,".gif") || equal(ext,".webp") || equal(ext,".tif") || equal(ext,".tiff") || equal(ext,".avif");
}
/* Expands one archive member into its source-order pages. A multi-frame GIF,
   animated WebP/AVIF or multi-directory TIFF contributes frame 0..N-1; no
   frame is skipped. Page 0 keeps the member name as its ID. Later frames use
   "<name>#<n>" so existing single-page CBZ IDs remain stable. */
static exr_status member_pages(comic *d,mz_uint index,const mz_zip_archive_file_stat *st,const char *name,size_t size,size_t *work,comic_page **out,size_t *count,exr_error *e) {
  unsigned char *data=NULL;size_t n=0,limit,page_count=0,i;exr_status status;
  *out=NULL;*count=0;
  limit=full_header(name) ? size : (size<1048576 ? size : 1048576);
  status=member_bytes(d,st,limit,0,&data,&n,work,e);
  if(status==EXR_OK && work && *work>(size_t)96*1024*1024) status=exr_fail(e,EXR_LIMIT,"CBZ image headers exceed 96 MiB work budget");
  if(status==EXR_OK) {
    status=exr_image_page_count(data,n,&page_count,e);
    if(status==EXR_FORMAT && n==limit && limit<size) status=exr_fail(e,EXR_LIMIT,"CBZ image header exceeds 1 MiB");
  }
  if(status==EXR_OK && (!page_count || page_count>(size_t)4096)) status=exr_fail(e,EXR_LIMIT,"CBZ image exceeds 4096 frames");
  if(status==EXR_OK) {
    *out=calloc(page_count,sizeof(**out));
    if(!*out) status=exr_fail(e,EXR_MEMORY,"CBZ page directory allocation failed");
  }
  for(i=0;status==EXR_OK && i<page_count;i++) {
    comic_page *p=&(*out)[i];char suffix[32];
    p->index=index; p->frame=(uint32_t)i;
    status=exr_image_page_dimensions(data,n,i,&p->width,&p->height,e);
    if(status==EXR_OK) {
      p->name=exr_copy(name,strlen(name));
      if(!p->name) status=exr_fail(e,EXR_MEMORY,"CBZ page name allocation failed");
    }
    if(status==EXR_OK) {
      if(page_count==1) p->id=exr_copy(name,strlen(name));
      else if(!i) { size_t len=strlen(name)+24; p->id=malloc(len); if(p->id) snprintf(p->id,len,"%s",name); }
      else { size_t len=strlen(name)+24; snprintf(suffix,sizeof(suffix),"#%zu",i); p->id=malloc(len); if(p->id) snprintf(p->id,len,"%s%s",name,suffix); }
      if(!p->id) status=exr_fail(e,EXR_MEMORY,"CBZ page id allocation failed");
    }
    if(status==EXR_OK) status=exr_control_poll(d->control,EXR_STAGE_READ,i,page_count,e);
  }
  free(data);
  if(status!=EXR_OK) {
    if(*out) for(i=0;i<page_count;i++) { free((*out)[i].name); free((*out)[i].id); }
    free(*out); *out=NULL; return status;
  }
  *count=page_count; return EXR_OK;
}
static exr_status member(comic *d,mz_uint index,size_t maximum,void **out,size_t *size,exr_error *e) {
  mz_zip_archive_file_stat st;size_t work=0;exr_status status;unsigned char *data=NULL;size_t n=0;
  *out=NULL;*size=0;
  if(!mz_zip_reader_file_stat(&d->zip,index,&st) || !mz_zip_reader_is_file_supported(&d->zip,index)) return archive_error(d,e,"Unsupported CBZ member");
  if(!st.m_uncomp_size || st.m_uncomp_size>maximum) return exr_fail(e,EXR_LIMIT,"CBZ member exceeds byte limit");
  if(exr_control_cancel(d->control,e)!=EXR_OK) return EXR_CANCELLED;
  status=member_bytes(d,&st,(size_t)st.m_uncomp_size,1,&data,&n,&work,e);
  if(status!=EXR_OK) return status;
  if(exr_control_cancel(d->control,e)!=EXR_OK) { free(data);return EXR_CANCELLED; }
  *out=data;*size=n;return EXR_OK;
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
  if(status==EXR_OK) status=exr_image_decode_page_control(data,size,p->frame,control,&image.bitmap,e);
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
  mz_uint i,total,info=UINT_MAX;size_t work=0,capacity;exr_fixed_page *pages=NULL;exr_fixed_input input={0};exr_status status=EXR_OK;
  d->control=&options->control;
  if(exr_control_cancel(d->control,e)!=EXR_OK) { status=EXR_CANCELLED;goto done; }
  if(d->data) { if(!mz_zip_reader_init_mem(&d->zip,d->data,(size_t)d->source.size,0)) { status=archive_error(d,e,"Invalid CBZ ZIP archive");goto done; } }
  else { d->zip.m_pRead=read_source;d->zip.m_pIO_opaque=d;if(!mz_zip_reader_init(&d->zip,d->source.size,0)) { status=archive_error(d,e,"Invalid CBZ ZIP source");goto done; } }
  total=mz_zip_reader_get_num_files(&d->zip);
  if(total>10000) { status=exr_fail(e,EXR_LIMIT,"CBZ exceeds 10000 archive members");goto done; }
  capacity=total ? total : 1;d->pages=calloc(capacity,sizeof(*d->pages));if(!d->pages) { status=exr_fail(e,EXR_MEMORY,"CBZ page directory allocation failed");goto done; }
  for(i=0;i<total;i++) {
    mz_zip_archive_file_stat st;char name[2049];const char *member;mz_uint length;int kind;size_t at=0;uint32_t cp;
    status=exr_control_poll(d->control,EXR_STAGE_READ,i,total,e);if(status!=EXR_OK) goto done;
    if(!mz_zip_reader_file_stat(&d->zip,i,&st)) { status=archive_error(d,e,"Invalid CBZ member directory");goto done; }
    if(st.m_is_directory) continue;
    length=mz_zip_reader_get_filename(&d->zip,i,name,sizeof(name));
    if(!length || length>sizeof(name)) { status=exr_fail(e,EXR_LIMIT,"CBZ member name exceeds 2048 bytes");goto done; }
    if(strlen(name)!=length-1) { status=exr_fail(e,EXR_FORMAT,"CBZ member name contains NUL");goto done; }
    /* Publisher exports (the two fixed Pepper&Carrot episodes) store every member
       under exactly one leading '/'. That single, unambiguous prefix is tolerated
       for validation and classification only: the archive bytes and the page ID
       keep the name exactly as stored, so a page ID is always a real ZIP member
       name. '//', "..", drive/UNC, backslash, NUL and normalized collisions still
       fail on the name below. */
    member=name;
    if(name[0]=='/') { memmove(name,name+1,length-1);length--; }
    if(!strncmp(name,"__MACOSX/",9) || name[0]=='.' || strstr(name,"/.")!=NULL) continue;
    kind=image_kind(name);
    if(!kind && !equal(name,"ComicInfo.xml")) continue;
    if(!exr_canonical_path(name)) { status=exr_fail(e,EXR_FORMAT,"Unsafe CBZ member path");goto done; }
    while(at<length-1) if(!exr_next(name,length-1,&at,&cp)) { status=exr_fail(e,EXR_ENCODING,"CBZ member name is not UTF-8");goto done; }
    if(!mz_zip_reader_is_file_supported(&d->zip,i)) { status=exr_fail(e,EXR_FORMAT,"Encrypted or unsupported CBZ compression");goto done; }
    if(!kind) { if(info!=UINT_MAX) { status=exr_fail(e,EXR_FORMAT,"Duplicate ComicInfo.xml");goto done; }info=i;continue; }
    if(!st.m_uncomp_size || st.m_uncomp_size>(size_t)32*1024*1024) { status=exr_fail(e,EXR_LIMIT,"CBZ encoded page exceeds 32 MiB");goto done; }
    { comic_page *expanded=NULL;size_t expanded_count=0;
      status=member_pages(d,i,&st,member,(size_t)st.m_uncomp_size,&work,&expanded,&expanded_count,e);
      if(status!=EXR_OK) goto done;
      if(d->count>(size_t)10000-expanded_count) { free(expanded);status=exr_fail(e,EXR_LIMIT,"CBZ exceeds 10000 pages after frame expansion");goto done; }
      if(d->count+expanded_count>capacity) {
        comic_page *grown=realloc(d->pages,(d->count+expanded_count)*sizeof(*grown));
        if(!grown) { free(expanded);status=exr_fail(e,EXR_MEMORY,"CBZ page directory allocation failed");goto done; }
        d->pages=grown;capacity=d->count+expanded_count;
      }
      memcpy(d->pages+d->count,expanded,expanded_count*sizeof(*expanded));free(expanded);d->count+=expanded_count;
    }
  }
  if(!d->count) { status=exr_fail(e,EXR_FORMAT,"CBZ contains no supported image pages");goto done; }
  qsort(d->pages,d->count,sizeof(*d->pages),compare_pages);
  status=check_normalized_paths(d->pages,d->count,e);if(status!=EXR_OK) goto done;
  for(i=1;i<d->count;i++) if(!strcmp(d->pages[i-1].id,d->pages[i].id)) { status=exr_fail(e,EXR_FORMAT,"Duplicate CBZ page path or frame id");goto done; }
  if(info!=UINT_MAX) { status=comic_info(d,info,e);if(status!=EXR_OK) goto done; }
  for(i=0;i<d->metadata_count;i++) if(!strcmp(d->metadata[i].key,"http://purl.org/dc/terms/title")) { title=d->metadata[i].value;break; }
  pages=calloc(d->count,sizeof(*pages));if(!pages) { status=exr_fail(e,EXR_MEMORY,"CBZ fixed pages allocation failed");goto done; }
  for(i=0;i<d->count;i++) { pages[i].id=pages[i].label=d->pages[i].id;pages[i].geometry.bounds[2]=d->pages[i].width;pages[i].geometry.bounds[3]=d->pages[i].height;pages[i].geometry.unit_scale=1;pages[i].geometry.y_down=1; }
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
/* Borrows the seekable source for the lifetime of the fixed document unless
   take_ownership is set; the CBZ reader never copies the whole archive. */
exr_status exr_cbz_open_source(const exr_source *source,const char *title,const exr_fixed_open_options *options,
                               int take_ownership,exr_fixed_document **out,exr_error *e) {
  comic *d;
  if(out) *out=NULL;
  if(!source || !source->read_at || !source->size) return exr_fail(e,EXR_ARGUMENT,"Invalid CBZ source");
  d=calloc(1,sizeof(*d));
  if(!d) { if(take_ownership && source->release) source->release(source->context);return exr_fail(e,EXR_MEMORY,"CBZ allocation failed"); }
  d->source=*source;d->borrowed=!take_ownership;
  return open_comic(d,title,options,out,e);
}
