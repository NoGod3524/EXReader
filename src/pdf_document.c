/* SPDX-License-Identifier: MIT */
#include "pdf_raster_internal.h"
#include "font_internal.h"
#include "pdf_crypto.h"
typedef struct {
  unsigned char *data; size_t size,count; exr_pdf_file *file; exr_pdf_page_info *pages; exr_font *font;
  exr_metadata_entry *metadata; size_t metadata_count;
  exr_page_annotation *annotations; size_t annotation_count;
  exr_pdf_crypt crypt; exr_mapping mapping; int mapped;
} pdf_document;
static void discard_reader(pdf_document *d) { free(d->pages); d->pages=NULL; exr_pdf_close(d->file); d->file=NULL; }
static void release(void *context) {
  pdf_document *d=context; if(!d) return; discard_reader(d); exr_font_free(d->font);
  exr_metadata_free(d->metadata,d->metadata_count); exr_page_annotations_free(d->annotations,d->annotation_count);
  exr_pdf_secret_clear(&d->crypt,sizeof(d->crypt));
  if(d->mapped) exr_unmap(&d->mapping); else free(d->data);
  free(d);
}
static exr_status reader(pdf_document *d,exr_error *e) {
  exr_status status; size_t count=0;
  if(d->file) return EXR_OK;
  status=exr_pdf_open_password(d->data,d->size,NULL,0,&d->crypt,NULL,&d->file,e);
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
static exr_status draw_ex(void *context,size_t page,const double matrix[6],const exr_draw_sink_ex *sink,const exr_control *control,exr_error *e) {
  pdf_document *d=context; exr_buffer content={0}; exr_status status=reader(d,e);
  if(status!=EXR_OK) return status;
  if(page>=d->count) return exr_fail(e,EXR_ARGUMENT,"PDF page is out of range");
  exr_pdf_control(d->file,control);
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_pdf_content(d->file,d->pages[page].contents,&content,e);
  if(status==EXR_OK) status=exr_pdf_paint_page_ex(d->file,&d->pages[page],content.data,content.size,matrix,sink,program,d,NULL,control,e);
  free(content.data);
  /* Failed lazy resolution/decoding can leave a sticky parser error. Rebuild
     the reader on the next request, so another page remains independently usable. */
  if(status!=EXR_OK) discard_reader(d); else exr_pdf_operation_end(d->file);
  return status;
}
static exr_status draw(void *context,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  exr_draw_sink_ex extended={0};extended.struct_size=sizeof(extended);extended.base=*sink;
  return draw_ex(context,page,matrix,&extended,control,e);
}

/* Snapshot order follows content operators, including nested Forms. No inferred
   spaces/line breaks or glyph-outline guesses are added to semantic mappings. */
typedef struct { exr_buffer bytes; exr_text_region *regions; size_t count,capacity; } text_builder;
static exr_status collect_text(void *context,const exr_pdf_text_glyph *g,exr_error *e) {
  text_builder *b=context; exr_text_region r={0}; size_t i,n=g->character.text.size;
  const exr_pdf_font_info *font=exr_pdf_font_description(g->font); double points[8];
  size_t maximum=(size_t)64*1024*1024/sizeof(r);
  if(!n) return EXR_OK;
  if(n>((size_t)32*1024*1024-1)-b->bytes.size || b->count==maximum)
    return exr_fail(e,EXR_LIMIT,"PDF text snapshot exceeds byte/region budget");
  if(b->count==b->capacity) {
    size_t next=b->capacity ? b->capacity*2 : 64; exr_text_region *copy;
    if(next>maximum) next=maximum;
    copy=realloc(b->regions,next*sizeof(r)); if(!copy) return exr_fail(e,EXR_MEMORY,"PDF text regions allocation failed");
    b->regions=copy; b->capacity=next;
  }
  r.start=b->bytes.size; r.end=r.start+n;
  if(font->kind==EXR_PDF_TYPE3) memcpy(points,font->type3_quad,sizeof(points));
  else if(font->vertical) {
    /* First edge follows vertical text advance; thickness is declared width. */
    double x=g->character.vertical_x,y=g->character.vertical_y,w=g->character.width,a=g->character.vertical_advance;
    double p[8]={x-w/2,y,x-w/2,y+a,x+w/2,y+a,x+w/2,y}; memcpy(points,p,sizeof(p)); r.flags|=EXR_REGION_VERTICAL;
  } else {
    double p[8]={0,font->descent,g->character.width,font->descent,g->character.width,font->ascent,0,font->ascent}; memcpy(points,p,sizeof(p));
  }
  if(g->rendering_mode==3 || g->rendering_mode==7) r.flags|=EXR_REGION_INVISIBLE;
  for(i=0;i<4;i++) {
    r.quad[i*2]=g->transform[0]*points[i*2]+g->transform[2]*points[i*2+1]+g->transform[4];
    r.quad[i*2+1]=g->transform[1]*points[i*2]+g->transform[3]*points[i*2+1]+g->transform[5];
    if(!isfinite(r.quad[i*2]) || !isfinite(r.quad[i*2+1]) || fabs(r.quad[i*2])>1e7 || fabs(r.quad[i*2+1])>1e7)
      return exr_fail(e,EXR_LIMIT,"PDF text quad exceeds coordinate budget");
  }
  if(!exr_append(&b->bytes,g->character.text.utf8,n)) return exr_fail(e,EXR_MEMORY,"PDF text allocation failed");
  b->regions[b->count++]=r; return EXR_OK;
}
static exr_status text(void *context,size_t page,const exr_control *control,exr_fixed_text **out,exr_error *e) {
  pdf_document *d=context; text_builder b={0}; exr_buffer content={0}; exr_status status=reader(d,e);
  *out=NULL; if(status!=EXR_OK) return status;
  if(page>=d->count) return exr_fail(e,EXR_ARGUMENT,"PDF page is out of range");
  exr_pdf_control(d->file,control);
  status=exr_control_cancel(control,e);
  if(status==EXR_OK) status=exr_pdf_content(d->file,d->pages[page].contents,&content,e);
  if(status==EXR_OK) status=exr_pdf_text_ops(d->file,d->pages[page].resources,content.data,content.size,collect_text,&b,control,e);
  if(status==EXR_OK) status=exr_fixed_text_create(b.bytes.data,b.bytes.size,b.regions,b.count,control,out,e);
  free(content.data); free(b.bytes.data); free(b.regions);
  if(status!=EXR_OK) discard_reader(d); else exr_pdf_operation_end(d->file);
  return status;
}
/* ISO 32000 text strings: PDFDocEncoding, BOM UTF-16BE and PDF 2 UTF-8.
   Do not reuse font encodings: Info text is unrelated to a page font. */
exr_status exr_pdf_metadata_string(exr_pdf_file *file,uint32_t id,char **out,exr_error *e) {
  static const uint16_t accents[]={0x02d8,0x02c7,0x02c6,0x02d9,0x02dd,0x02db,0x02da,0x02dc};
  static const uint16_t symbols[]={0x2022,0x2020,0x2021,0x2026,0x2014,0x2013,0x0192,0x2044,0x2039,0x203a,0x2212,0x2030,0x201e,0x201c,0x201d,0x2018,0x2019,0x201a,0x2122,0xfb01,0xfb02,0x0141,0x0152,0x0160,0x0178,0x017d,0x0131,0x0142,0x0153,0x0161,0x017e};
  exr_status status; const exr_pdf_value *v; const unsigned char *data; size_t size,at=0; int utf16=0,utf8=0; exr_buffer b={0};
  *out=NULL; status=exr_pdf_resolve(file,id,&id,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(file,id); if(!v || v->kind==EXR_PDF_NULL) return EXR_OK;
  if(v->kind!=EXR_PDF_STRING) return exr_fail(e,EXR_FORMAT,"PDF metadata value is not a text string");
  data=exr_pdf_bytes(file,id,&size); if(size>65536) return exr_fail(e,EXR_LIMIT,"PDF metadata value exceeds 64 KiB");
  if(size>=2 && data[0]==0xfe && data[1]==0xff) { utf16=1; at=2; }
  else if(size>=3 && data[0]==0xef && data[1]==0xbb && data[2]==0xbf) { utf8=1; at=3; }
  while(at<size) {
    uint32_t cp;
    if(utf16) {
      if(size-at<2) goto invalid;
      cp=((uint32_t)data[at]<<8)|data[at+1]; at+=2;
      if(cp>=0xd800 && cp<=0xdbff) {
        uint32_t low; if(size-at<2) goto invalid;
        low=((uint32_t)data[at]<<8)|data[at+1]; at+=2; if(low<0xdc00 || low>0xdfff) goto invalid;
        cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);
      } else if(cp>=0xdc00 && cp<=0xdfff) goto invalid;
    } else if(utf8) { if(!exr_next((const char *)data,size,&at,&cp)) goto invalid; }
    else {
      cp=data[at++];
      if(cp==0x7f || cp==0x9f || cp==0xad) goto invalid;
      if(cp>=0x18 && cp<=0x1f) cp=accents[cp-0x18];
      else if(cp>=0x80 && cp<=0x9e) cp=symbols[cp-0x80];
      else if(cp==0xa0) cp=0x20ac;
    }
    if(!cp) goto invalid;
    if(!exr_codepoint(&b,cp)) { status=exr_fail(e,EXR_MEMORY,"PDF metadata allocation failed"); goto done; }
    if(b.size>65536) { status=exr_fail(e,EXR_LIMIT,"Decoded PDF metadata exceeds 64 KiB"); goto done; }
  }
  if(!b.data) b.data=exr_copy("",0);
  if(!b.data) { status=exr_fail(e,EXR_MEMORY,"PDF metadata allocation failed"); goto done; }
  *out=b.data; return EXR_OK;
invalid:
  status=exr_fail(e,EXR_FORMAT,"Invalid PDF metadata text encoding");
done:
  free(b.data); return status;
}
static exr_status merge_xmp(pdf_document *d,const exr_control *control,exr_error *e) {
  uint32_t id; const exr_pdf_value *v; const unsigned char *data; size_t size,i,j,n=0,bytes=0;
  exr_metadata_entry *xmp=NULL,*merged; size_t xcount=0; exr_status status;
  status=exr_pdf_resolve(d->file,exr_pdf_get(d->file,exr_pdf_root(d->file),"Metadata"),&id,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(d->file,id); if(!v || v->kind==EXR_PDF_NULL) return EXR_OK;
  if(v->kind!=EXR_PDF_STREAM) return exr_fail(e,EXR_FORMAT,"PDF Metadata is not a stream");
  status=exr_pdf_stream_data(d->file,id,&data,&size,e); if(status!=EXR_OK) return status;
  status=exr_metadata_read_xmp(data,size,control,&xmp,&xcount,e); if(status!=EXR_OK) return status;
  /* XMP replaces Info values of the same key; repeated XMP values keep order. */
  for(i=0;i<d->metadata_count;i++) {
    for(j=0;j<xcount;j++) if(!strcmp(d->metadata[i].key,xmp[j].key)) break;
    if(j<xcount) { free((void *)d->metadata[i].key); free((void *)d->metadata[i].value); }
    else d->metadata[n++]=d->metadata[i];
  }
  d->metadata_count=n;
  if(xcount>4096-n) { status=exr_fail(e,EXR_LIMIT,"PDF metadata exceeds 4096 values"); goto done; }
  for(i=0;i<n;i++) bytes+=strlen(d->metadata[i].key)+strlen(d->metadata[i].value)+2;
  for(i=0;i<xcount;i++) bytes+=strlen(xmp[i].key)+strlen(xmp[i].value)+2;
  if(bytes>(size_t)8*1024*1024) { status=exr_fail(e,EXR_LIMIT,"PDF metadata exceeds 8 MiB"); goto done; }
  if(xcount) {
    merged=realloc(d->metadata,(n+xcount)*sizeof(*merged)); if(!merged) { status=exr_fail(e,EXR_MEMORY,"PDF metadata merge allocation failed"); goto done; }
    d->metadata=merged; memcpy(d->metadata+n,xmp,xcount*sizeof(*xmp)); d->metadata_count=n+xcount; free(xmp); xmp=NULL;
  }
done:
  exr_metadata_free(xmp,xcount); return status;
}
static exr_status metadata(void *context,const exr_control *control,const exr_metadata_entry **out,size_t *count,exr_error *e) {
  static const char *names[]={"Title","Author","Subject","Keywords","Creator","Producer","CreationDate","ModDate"};
  static const char *keys[]={"http://purl.org/dc/terms/title","http://purl.org/dc/terms/creator","http://purl.org/dc/terms/description","http://ns.adobe.com/pdf/1.3/Keywords","http://ns.adobe.com/xap/1.0/CreatorTool","http://ns.adobe.com/pdf/1.3/Producer","http://ns.adobe.com/xap/1.0/CreateDate","http://ns.adobe.com/xap/1.0/ModifyDate"};
  pdf_document *d=context; uint32_t info; const exr_pdf_value *v; exr_status status; size_t i;
  *out=NULL; *count=0;
  exr_metadata_free(d->metadata,d->metadata_count); d->metadata=NULL; d->metadata_count=0;
  status=reader(d,e); if(status!=EXR_OK) return status;
  exr_pdf_control(d->file,control);
  status=exr_pdf_resolve(d->file,exr_pdf_info(d->file),&info,e); if(status!=EXR_OK) goto done;
  v=exr_pdf_value_at(d->file,info); if(!v || v->kind==EXR_PDF_NULL) goto read_xmp;
  if(v->kind!=EXR_PDF_DICT) { status=exr_fail(e,EXR_FORMAT,"PDF Info is not a dictionary"); goto done; }
  d->metadata=calloc(8,sizeof(*d->metadata)); if(!d->metadata) { status=exr_fail(e,EXR_MEMORY,"PDF metadata allocation failed"); goto done; }
  for(i=0;i<8;i++) {
    char *value=NULL; status=exr_control_poll(control,EXR_STAGE_READ,i,8,e); if(status!=EXR_OK) goto done;
    status=exr_pdf_metadata_string(d->file,exr_pdf_get(d->file,info,names[i]),&value,e); if(status!=EXR_OK) goto done;
    if(value) {
      char *key=exr_copy(keys[i],strlen(keys[i])); if(!key) { free(value); status=exr_fail(e,EXR_MEMORY,"PDF metadata key allocation failed"); goto done; }
      d->metadata[d->metadata_count++]=(exr_metadata_entry){key,value};
    }
  }
read_xmp:
  status=merge_xmp(d,control,e); if(status!=EXR_OK) goto done;
  *out=d->metadata; *count=d->metadata_count;
done:
  if(status!=EXR_OK) discard_reader(d); else exr_pdf_operation_end(d->file);
  return status;
}
static exr_status annotations(void *context,size_t page,const exr_control *control,const exr_page_annotation **out,size_t *count,exr_error *e) {
  pdf_document *d=context; exr_status status;
  *out=NULL; *count=0; exr_page_annotations_free(d->annotations,d->annotation_count); d->annotations=NULL; d->annotation_count=0;
  status=reader(d,e); if(status!=EXR_OK) return status;
  if(page>=d->count) return exr_fail(e,EXR_ARGUMENT,"PDF annotation page is out of range");
  exr_pdf_control(d->file,control);
  status=exr_pdf_page_annotations(d->file,d->pages[page].annotations,control,&d->annotations,&d->annotation_count,e);
  if(status!=EXR_OK) discard_reader(d); else { exr_pdf_operation_end(d->file); *out=d->annotations; *count=d->annotation_count; }
  return status;
}
exr_status exr_fixed_open_options_copy(const exr_fixed_open_options *input,exr_fixed_open_options *out,exr_error *e) {
  size_t i,minimum=offsetof(exr_fixed_open_options,control)+sizeof(out->control); memset(out,0,sizeof(*out));
  if(!input) return EXR_OK;
  if(input->struct_size<minimum || input->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed open options size");
  for(i=sizeof(*out);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported fixed open options extension");
  if((input->struct_size>offsetof(exr_fixed_open_options,pdf_password) && input->struct_size<offsetof(exr_fixed_open_options,pdf_password)+sizeof(out->pdf_password)) ||
     (input->struct_size>offsetof(exr_fixed_open_options,pdf_password_size) && input->struct_size<offsetof(exr_fixed_open_options,pdf_password_size)+sizeof(out->pdf_password_size)) ||
     (input->struct_size>offsetof(exr_fixed_open_options,pdf_security) && input->struct_size<offsetof(exr_fixed_open_options,pdf_security)+sizeof(out->pdf_security)))
    return exr_fail(e,EXR_ARGUMENT,"Truncated PDF open options field");
  memcpy(out,input,input->struct_size<sizeof(*out) ? input->struct_size : sizeof(*out));
  if(out->pdf_password_size && !out->pdf_password) return exr_fail(e,EXR_ARGUMENT,"Missing PDF password bytes");
  if(out->pdf_password_size>1024) return exr_fail(e,EXR_LIMIT,"PDF password exceeds 1024 bytes");
  if(out->pdf_security && (out->pdf_security->struct_size<sizeof(*out->pdf_security) || out->pdf_security->struct_size>4096))
    return exr_fail(e,EXR_ARGUMENT,"Invalid PDF security info size");
  return EXR_OK;
}
/* Takes bytes on every path; no second whole-file copy for file-based opens. */
static exr_status open_data(unsigned char *data,size_t size,const char *title,const exr_fixed_open_options *options,
                            exr_mapping *mapping,int mapped,exr_fixed_document **out,exr_error *e) {
  pdf_document *d=NULL; exr_fixed_page *pages=NULL; exr_fixed_input input={0}; exr_status status; size_t i;
  if(exr_control_cancel(&options->control,e)!=EXR_OK) {
    if(mapped) exr_unmap(mapping); else free(data);
    return EXR_CANCELLED;
  }
  d=calloc(1,sizeof(*d));
  if(!d) {
    if(mapped) exr_unmap(mapping); else free(data);
    return exr_fail(e,EXR_MEMORY,"PDF document allocation failed");
  }
  d->data=data; d->size=size; d->mapped=mapped;
  if(mapped) { d->mapping=*mapping; memset(mapping,0,sizeof(*mapping)); }
  d->font=options->fallback_font; exr_font_ref(d->font);
  status=exr_pdf_open_password(data,size,options->pdf_password,options->pdf_password_size,NULL,&options->control,&d->file,e);
  if(status==EXR_ARGUMENT) status=exr_fail(e,EXR_FORMAT,"Invalid PDF bytes");
  if(status!=EXR_OK) goto done;
  exr_pdf_crypt_snapshot(d->file,&d->crypt);
  exr_pdf_control(d->file,&options->control);
  status=exr_pdf_pages(d->file,&d->pages,&d->count,e); if(status!=EXR_OK) goto done;
  exr_pdf_operation_end(d->file);
  if(!d->count) { status=exr_fail(e,EXR_FORMAT,"PDF has no pages"); goto done; }
  pages=calloc(d->count,sizeof(*pages)); if(!pages) { status=exr_fail(e,EXR_MEMORY,"PDF fixed directory allocation failed"); goto done; }
  for(i=0;i<d->count;i++) {
    size_t k; exr_pdf_page_info *p=&d->pages[i];
    status=exr_control_poll(&options->control,EXR_STAGE_READ,i,d->count,e); if(status!=EXR_OK) goto done;
    for(k=0;k<2;k++) { pages[i].geometry.bounds[k]=fmax(p->crop[k],p->media[k]); pages[i].geometry.bounds[k+2]=fmin(p->crop[k+2],p->media[k+2]); }
    if(pages[i].geometry.bounds[0]>=pages[i].geometry.bounds[2] || pages[i].geometry.bounds[1]>=pages[i].geometry.bounds[3]) { status=exr_fail(e,EXR_FORMAT,"PDF page crop has no MediaBox intersection"); goto done; }
    pages[i].geometry.unit_scale=p->user_unit; pages[i].geometry.rotation=p->rotation;
  }
  input.struct_size=sizeof(input); input.title=title; input.pages=pages; input.page_count=d->count; input.draw=draw;input.draw_ex=draw_ex; input.context=d; input.release=release; input.text=text; input.metadata=metadata; input.annotations=annotations;
  status=exr_control_poll(&options->control,EXR_STAGE_READ,d->count,d->count,e);
  if(status==EXR_OK) status=exr_fixed_create(&input,out,e);
  if(status==EXR_OK && options->pdf_security) {
    exr_pdf_security_info info={0}; info.struct_size=options->pdf_security->struct_size; info.encrypted=!!d->crypt.revision;
    info.revision=d->crypt.revision; info.key_bits=d->crypt.length*8; info.owner_authenticated=d->crypt.owner;
    info.permissions=info.encrypted ? d->crypt.permissions : UINT32_MAX; info.metadata_encrypted=info.encrypted && d->crypt.metadata;
    memcpy(options->pdf_security,&info,sizeof(info));
  }
done:
  free(pages); if(status!=EXR_OK) release(d); return status;
}
exr_status exr_fixed_open_memory(exr_format format,const void *data,size_t size,const exr_fixed_open_options *input,exr_fixed_document **out,exr_error *e) {
  exr_fixed_open_options options; unsigned char *copy; exr_status status;
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing fixed document output");
  *out=NULL;
  if(!data || !size || size>EXR_MAX_INPUT) return exr_fail(e,size>EXR_MAX_INPUT ? EXR_LIMIT : EXR_ARGUMENT,"Invalid fixed document bytes");
  if(!exr_format_is_fixed(format)) return exr_fail(e,EXR_FORMAT,"No built-in fixed reader for this format");
  status=exr_fixed_open_options_copy(input,&options,e); if(status!=EXR_OK) return status;
  if(exr_control_cancel(&options.control,e)!=EXR_OK) return EXR_CANCELLED;
  copy=malloc(size); if(!copy) return exr_fail(e,EXR_MEMORY,"Fixed input copy allocation failed"); memcpy(copy,data,size);
  if(format==EXR_CBZ) return exr_cbz_open_owned(copy,size,"",&options,out,e);
  return open_data(copy,size,"",&options,NULL,0,out,e);
}
/* Takes ownership of mapping on every path. Used by the streaming library for
   a stored PDF whose bytes were paged into an anonymous mapping. */
exr_status exr_fixed_open_mapped(exr_format format,exr_mapping *mapping,const exr_fixed_open_options *input,
                                 exr_fixed_document **out,exr_error *e) {
  exr_fixed_open_options options; exr_status status;
  if(out) *out=NULL;
  if(!mapping || !mapping->address || !mapping->size) return exr_fail(e,EXR_ARGUMENT,"Invalid mapped fixed document");
  if(format!=EXR_PDF) { exr_unmap(mapping);return exr_fail(e,EXR_UNSUPPORTED,"Mapped fixed reading is available for PDF"); }
  if(!out) { exr_unmap(mapping);return exr_fail(e,EXR_ARGUMENT,"Missing fixed document output"); }
  status=exr_fixed_open_options_copy(input,&options,e);
  if(status!=EXR_OK) { exr_unmap(mapping);return status; }
  return open_data((unsigned char *)mapping->address,mapping->size,"",&options,mapping,1,out,e);
}
exr_status exr_fixed_open(const char *path,const exr_fixed_open_options *input,exr_fixed_document **out,exr_error *e) {
  exr_fixed_open_options options; unsigned char *data=NULL; size_t size=0; exr_status status; const char *title,*at; exr_mapping mapping={0};
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing fixed document output");
  *out=NULL; if(!path) return exr_fail(e,EXR_ARGUMENT,"Missing fixed document path");
  status=exr_fixed_open_options_copy(input,&options,e); if(status!=EXR_OK) return status;
  if(exr_control_cancel(&options.control,e)!=EXR_OK) return EXR_CANCELLED;
  title=path; for(at=path;*at;at++) if(*at=='/' || *at=='\\') title=at+1;
  at=strrchr(title,'.');
  if(at && (at[0]=='.' && (at[1]=='c' || at[1]=='C') && (at[2]=='b' || at[2]=='B') && (at[3]=='z' || at[3]=='Z') && !at[4])) return exr_cbz_open_file(path,title,&options,out,e);
  status=exr_map_file(path,&mapping,e);
  if(status==EXR_OK) return open_data((unsigned char *)mapping.address,mapping.size,title,&options,&mapping,1,out,e);
  status=exr_read(path,&data,&size,e); if(status!=EXR_OK) return status;
  return open_data(data,size,title,&options,NULL,0,out,e);
}
