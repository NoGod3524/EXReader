/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_raster_internal.h"
#include "layout_internal.h"
typedef struct {
  unsigned char *data; size_t size,count; exr_pdf_file *file; exr_pdf_page_info *pages; exr_font *font;
} pdf_document;
static void discard_reader(pdf_document *d) { free(d->pages); d->pages=NULL; exr_pdf_close(d->file); d->file=NULL; }
static void release(void *context) {
  pdf_document *d=context; if(!d) return; discard_reader(d); exr_font_free(d->font); free(d->data); free(d);
}
static exr_status reader(pdf_document *d,exr_error *e) {
  exr_status status; size_t count=0;
  if(d->file) return EXR_OK;
  status=exr_pdf_open(d->data,d->size,&d->file,e);
  if(status==EXR_OK) status=exr_pdf_pages(d->file,&d->pages,&count,e);
  if(status==EXR_OK && (!count || (d->count && count!=d->count))) status=exr_fail(e,EXR_FORMAT,"Invalid or changed PDF page directory");
  if(status!=EXR_OK) { discard_reader(d); return status==EXR_ARGUMENT ? exr_fail(e,EXR_FORMAT,"Invalid PDF bytes") : status; }
  d->count=count; return EXR_OK;
}
static exr_status program(void *context,const exr_pdf_font_info *info,exr_font_input *out,exr_error *e) {
  pdf_document *d=context; const char *name=info->base_name ? info->base_name : ""; size_t i,selected=SIZE_MAX; unsigned flags=0,best=8;
  if(!d->font) return exr_fail(e,EXR_FORMAT,"PDF font is not embedded; supply fallback_font");
  if(strlen(name)>7 && name[6]=='+') name+=7;
  if(strstr(name,"Bold") || (info->flags&262144)) flags|=1;
  if(strstr(name,"Italic") || strstr(name,"Oblique") || (info->flags&64)) flags|=2;
  for(i=0;i<d->font->base_count;i++) {
    unsigned score=((flags^d->font->faces[i].style_flags)&3)+(exr_family_equal(name,d->font->faces[i].family) ? 0 : 4);
    if(score<best) { best=score; selected=i; }
  }
  if(selected==SIZE_MAX) return exr_fail(e,EXR_FORMAT,"No usable PDF fallback font face");
  return exr_font_source(d->font,selected,out,e);
}
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  pdf_document *d=context; exr_buffer content={0}; exr_status status=reader(d,e);
  if(status!=EXR_OK) return status;
  if(page>=d->count) return exr_fail(e,EXR_ARGUMENT,"PDF page is out of range");
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_pdf_content(d->file,d->pages[page].contents,&content,e);
  if(status==EXR_OK) status=exr_pdf_paint_content(d->file,d->pages[page].resources,content.data,content.size,matrix,sink,program,d,NULL,control,e);
  free(content.data);
  /* Failed lazy resolution/decoding can leave a sticky parser error. Rebuild
     the reader on the next request, so another page remains independently usable. */
  if(status!=EXR_OK) discard_reader(d);
  return status;
}
static exr_status open_options(const exr_fixed_open_options *input,exr_fixed_open_options *out,exr_error *e) {
  size_t i,minimum=offsetof(exr_fixed_open_options,control)+sizeof(out->control); memset(out,0,sizeof(*out));
  if(!input) return EXR_OK;
  if(input->struct_size<minimum || input->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed open options size");
  for(i=sizeof(*out);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported fixed open options extension");
  memcpy(out,input,input->struct_size<sizeof(*out) ? input->struct_size : sizeof(*out)); return EXR_OK;
}
/* Takes bytes on every path; no second whole-file copy for file-based opens. */
static exr_status open_owned(unsigned char *data,size_t size,const char *title,const exr_fixed_open_options *options,exr_fixed_document **out,exr_error *e) {
  pdf_document *d=NULL; exr_fixed_page *pages=NULL; exr_fixed_input input={0}; exr_status status; size_t i;
  if(exr_control_cancel(&options->control,e)!=EXR_OK) { free(data); return EXR_CANCELLED; }
  d=calloc(1,sizeof(*d)); if(!d) { free(data); return exr_fail(e,EXR_MEMORY,"PDF document allocation failed"); }
  d->data=data; d->size=size; d->font=options->fallback_font; exr_font_ref(d->font);
  status=reader(d,e); if(status!=EXR_OK) goto done;
  pages=calloc(d->count,sizeof(*pages)); if(!pages) { status=exr_fail(e,EXR_MEMORY,"PDF fixed directory allocation failed"); goto done; }
  for(i=0;i<d->count;i++) {
    size_t k; exr_pdf_page_info *p=&d->pages[i];
    status=exr_control_poll(&options->control,EXR_STAGE_READ,i,d->count,e); if(status!=EXR_OK) goto done;
    for(k=0;k<2;k++) { pages[i].geometry.bounds[k]=fmax(p->crop[k],p->media[k]); pages[i].geometry.bounds[k+2]=fmin(p->crop[k+2],p->media[k+2]); }
    if(pages[i].geometry.bounds[0]>=pages[i].geometry.bounds[2] || pages[i].geometry.bounds[1]>=pages[i].geometry.bounds[3]) { status=exr_fail(e,EXR_FORMAT,"PDF page crop has no MediaBox intersection"); goto done; }
    pages[i].geometry.unit_scale=p->user_unit; pages[i].geometry.rotation=p->rotation;
  }
  input.struct_size=sizeof(input); input.title=title; input.pages=pages; input.page_count=d->count; input.draw=draw; input.context=d; input.release=release;
  status=exr_control_poll(&options->control,EXR_STAGE_READ,d->count,d->count,e);
  if(status==EXR_OK) status=exr_fixed_create(&input,out,e);
done:
  free(pages); if(status!=EXR_OK) release(d); return status;
}
exr_status exr_fixed_open_memory(exr_format format,const void *data,size_t size,const exr_fixed_open_options *input,exr_fixed_document **out,exr_error *e) {
  exr_fixed_open_options options; unsigned char *copy; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing fixed document output");
  *out=NULL;
  if(!data || !size || size>EXR_MAX_INPUT) return exr_fail(e,size>EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT,"Invalid fixed document bytes");
  if(format!=EXR_PDF) return exr_fail(e,EXR_FORMAT,"No built-in fixed reader for this format");
  status=open_options(input,&options,e); if(status!=EXR_OK) return status;
  if(exr_control_cancel(&options.control,e)!=EXR_OK) return EXR_CANCELLED;
  copy=malloc(size); if(!copy) return exr_fail(e,EXR_MEMORY,"PDF input copy allocation failed"); memcpy(copy,data,size);
  return open_owned(copy,size,"",&options,out,e);
}
exr_status exr_fixed_open(const char *path,const exr_fixed_open_options *input,exr_fixed_document **out,exr_error *e) {
  exr_fixed_open_options options; unsigned char *data=NULL; size_t size=0; exr_status status; const char *title,*at;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing fixed document output");
  *out=NULL; if(!path) return exr_fail(e,EXR_ARGUMENT,"Missing fixed document path");
  status=open_options(input,&options,e); if(status!=EXR_OK) return status;
  if(exr_control_cancel(&options.control,e)!=EXR_OK) return EXR_CANCELLED;
  status=exr_read(path,&data,&size,e); if(status!=EXR_OK) return status;
  title=path; for(at=path;*at;at++) if(*at=='/' || *at=='\\') title=at+1;
  return open_owned(data,size,title,&options,out,e);
}
