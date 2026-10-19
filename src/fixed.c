/* SPDX-License-Identifier: MIT */
#include "document_internal.h"
#include "graphics_internal.h"
struct exr_fixed_document {
  char *title; exr_fixed_page *pages; size_t count,bytes;
  exr_fixed_draw_ex_fn draw_ex;exr_fixed_draw_fn draw; exr_fixed_text_fn text; exr_fixed_metadata_fn metadata; exr_fixed_annotations_fn annotations; void *context; exr_context_release_fn release; unsigned busy;
};
static exr_status copy_string(const char *source,size_t *bytes,const char **out,exr_error *e) {
  size_t n=0,at=0; uint32_t cp;
  *out=NULL; if(!source) source="";
  while(n<=65536 && source[n]) n++;
  if(n>65536 || n+1>(size_t)8*1024*1024-*bytes) return exr_fail(e,EXR_LIMIT,"Fixed page metadata exceeds limit");
  while(at<n) if(!exr_next(source,n,&at,&cp)) return exr_fail(e,EXR_ENCODING,"Fixed page metadata is not UTF-8");
  *out=exr_copy(source,n); if(!*out) return exr_fail(e,EXR_MEMORY,"Fixed page metadata allocation failed");
  *bytes+=n+1; return EXR_OK;
}
static int compare_id(const void *a,const void *b) { return strcmp(*(const char *const *)a,*(const char *const *)b); }
static exr_status geometry_valid(const exr_page_geometry *g,exr_error *e) {
  exr_viewport view; exr_status status=exr_viewport_create(g,1,&view,e);
  if(status==EXR_LIMIT) {
    double extent=fmax(g->bounds[2]-g->bounds[0],g->bounds[3]-g->bounds[1]);
    double scale=g->unit_scale<1e-7 ? 1e7 : 1/g->unit_scale,scaled=extent*g->unit_scale;
    if(scaled>0 && scale*scaled>1e7) scale=1e7/scaled;
    status=exr_viewport_create(g,scale,&view,e);
  }
  return status;
}
void exr_fixed_free(exr_fixed_document *d) {
  size_t i; if(!d) return;
  if(d->release) d->release(d->context);
  for(i=0;i<d->count;i++) { free((void *)d->pages[i].id); free((void *)d->pages[i].label); }
  free(d->pages); free(d->title); free(d);
}
exr_status exr_fixed_create(const exr_fixed_input *input,exr_fixed_document **out,exr_error *e) {
  exr_fixed_input snapshot={0}; exr_fixed_document *d; exr_status status; size_t i,strings=0; const char *title=NULL; const char **ids=NULL;
  const size_t minimum=offsetof(exr_fixed_input,release)+sizeof(snapshot.release);
  if(!out) return exr_fail(e,EXR_ARGUMENT,"Missing fixed document output");
  *out=NULL;
  if(!input || input->struct_size<minimum || input->struct_size>4096) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed input size");
  for(i=sizeof(snapshot);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Unsupported fixed input extension");
  memcpy(&snapshot,input,input->struct_size<sizeof(snapshot) ? input->struct_size : sizeof(snapshot)); input=&snapshot;
  if(input->struct_size>offsetof(exr_fixed_input,text) && input->struct_size<offsetof(exr_fixed_input,text)+sizeof(input->text)) {
    for(i=offsetof(exr_fixed_input,text);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Truncated fixed text provider field");
    snapshot.text=NULL;
  }
  if(input->struct_size>offsetof(exr_fixed_input,metadata) && input->struct_size<offsetof(exr_fixed_input,metadata)+sizeof(input->metadata)) {
    for(i=offsetof(exr_fixed_input,metadata);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Truncated metadata provider field");
    snapshot.metadata=NULL;
  }
  if(input->struct_size>offsetof(exr_fixed_input,annotations) && input->struct_size<offsetof(exr_fixed_input,annotations)+sizeof(input->annotations)) {
    for(i=offsetof(exr_fixed_input,annotations);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Truncated annotations provider field");
    snapshot.annotations=NULL;
  }
  if(input->struct_size>offsetof(exr_fixed_input,draw_ex) && input->struct_size<offsetof(exr_fixed_input,draw_ex)+sizeof(input->draw_ex)) {
    for(i=offsetof(exr_fixed_input,draw_ex);i<input->struct_size;i++) if(((const unsigned char *)input)[i]) return exr_fail(e,EXR_ARGUMENT,"Truncated extended draw provider field");
    snapshot.draw_ex=NULL;
  }
  if(!input->draw || !input->pages || !input->page_count) return exr_fail(e,EXR_ARGUMENT,"Missing fixed page directory/provider");
  if(input->page_count>10000) return exr_fail(e,EXR_LIMIT,"Fixed document exceeds 10000 pages");
  d=calloc(1,sizeof(*d)); if(!d) return exr_fail(e,EXR_MEMORY,"Fixed document allocation failed");
  d->pages=calloc(input->page_count,sizeof(*d->pages)); ids=calloc(input->page_count,sizeof(*ids));
  if(!d->pages || !ids) { status=exr_fail(e,EXR_MEMORY,"Fixed page directory allocation failed"); goto done; }
  d->count=input->page_count; status=copy_string(input->title,&strings,&title,e); d->title=(char *)title;
  for(i=0;status==EXR_OK && i<d->count;i++) {
    char generated[32]; const exr_fixed_page *p=&input->pages[i]; exr_fixed_page *v=&d->pages[i];
    const char *id=p->id; if(!id || !*id) { snprintf(generated,sizeof(generated),"page-%zu",i+1); id=generated; }
    v->geometry=p->geometry; status=geometry_valid(&v->geometry,e);
    if(status==EXR_OK) status=copy_string(id,&strings,&v->id,e);
    if(status==EXR_OK) status=copy_string(p->label,&strings,&v->label,e);
    ids[i]=v->id;
  }
  if(status==EXR_OK) {
    qsort(ids,d->count,sizeof(*ids),compare_id);
    for(i=1;i<d->count;i++) if(!strcmp(ids[i-1],ids[i])) { status=exr_fail(e,EXR_ARGUMENT,"Duplicate fixed page IDs"); break; }
  }
done:
  free(ids);
  if(status!=EXR_OK) { exr_fixed_free(d); return status; }
  d->draw=input->draw;d->draw_ex=input->draw_ex; d->text=input->text; d->metadata=input->metadata; d->annotations=input->annotations; d->context=input->context; d->release=input->release; d->bytes=sizeof(*d)+d->count*sizeof(*d->pages)+strings;
  *out=d; return exr_fail(e,EXR_OK,"");
}
const char *exr_fixed_title(const exr_fixed_document *d) { return d ? d->title : ""; }
const exr_fixed_page *exr_fixed_pages(const exr_fixed_document *d,size_t *count) { if(count) *count=d ? d->count : 0; return d ? d->pages : NULL; }
size_t exr_fixed_memory_size(const exr_fixed_document *d) { return d ? d->bytes : 0; }
static exr_status provider_end(exr_fixed_document *d,exr_status status,exr_error *local,exr_error *e) {
  d->busy=0;
  if(status!=EXR_OK) { local->code=status; if(!local->message[0]) exr_fail(local,status,"Fixed page provider failed"); if(e) *e=*local; return status; }
  return exr_fail(e,EXR_OK,"");
}
exr_status exr_fixed_load_metadata(exr_fixed_document *d,const exr_control *control,exr_metadata_entry **out,size_t *count,exr_error *e) {
  const exr_metadata_entry *borrowed=NULL; exr_metadata_entry *entries=NULL; size_t n=0,i,bytes=0;
  exr_error local={0}; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!d || !out || !count || d->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant metadata load");
  if(!d->metadata) return exr_fail(e,EXR_FORMAT,"Fixed document has no metadata provider");
  d->busy=1; status=exr_control_poll(control,EXR_STAGE_READ,0,1,&local);
  if(status==EXR_OK) status=d->metadata(d->context,control,&borrowed,&n,&local);
  if(status==EXR_OK && local.code!=EXR_OK) status=local.code;
  if(status==EXR_OK && (n>4096 || (n && !borrowed))) status=exr_fail(&local,n>4096 ? EXR_LIMIT : EXR_FORMAT,"Invalid metadata provider result");
  if(status==EXR_OK && n) {
    entries=calloc(n,sizeof(*entries)); if(!entries) status=exr_fail(&local,EXR_MEMORY,"Metadata snapshot allocation failed");
  }
  for(i=0;status==EXR_OK && i<n;i++) {
    status=exr_control_cancel(control,&local); if(status!=EXR_OK) break;
    if(!borrowed[i].key || !borrowed[i].key[0] || !borrowed[i].value) { status=exr_fail(&local,EXR_FORMAT,"Missing metadata key/value"); break; }
    status=copy_string(borrowed[i].key,&bytes,&entries[i].key,&local);
    if(status==EXR_OK) status=copy_string(borrowed[i].value,&bytes,&entries[i].value,&local);
  }
  if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_READ,1,1,&local);
  if(status==EXR_OK) { *out=entries; *count=n; } else exr_metadata_free(entries,n);
  return provider_end(d,status,&local,e);
}
void exr_page_annotations_free(exr_page_annotation *annotations,size_t count) {
  size_t i; if(!annotations) return;
  for(i=0;i<count;i++) { free((void *)annotations[i].id); free((void *)annotations[i].kind); free((void *)annotations[i].quads); exr_metadata_free((exr_metadata_entry *)annotations[i].properties,annotations[i].property_count); }
  free(annotations);
}
exr_status exr_fixed_load_annotations(exr_fixed_document *d,size_t page,const exr_control *control,exr_page_annotation **out,size_t *count,exr_error *e) {
  const exr_page_annotation *source=NULL; exr_page_annotation *entries=NULL; size_t n=0,i,j,bytes=0; exr_error local={0}; exr_status status;
  if(out) *out=NULL;
  if(count) *count=0;
  if(!d || !out || !count || page>=d->count || d->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant page annotations load");
  if(!d->annotations) return exr_fail(e,EXR_FORMAT,"Fixed document has no annotations provider");
  d->busy=1; status=exr_control_poll(control,EXR_STAGE_READ,0,1,&local);
  if(status==EXR_OK) status=d->annotations(d->context,page,control,&source,&n,&local);
  if(status==EXR_OK && local.code!=EXR_OK) status=local.code;
  if(status==EXR_OK && (n>4096 || (n && !source))) status=exr_fail(&local,n>4096 ? EXR_LIMIT : EXR_FORMAT,"Invalid page annotations result");
  if(status==EXR_OK && n) { entries=calloc(n,sizeof(*entries)); if(!entries) status=exr_fail(&local,EXR_MEMORY,"Annotations allocation failed"); bytes=n*sizeof(*entries); }
  for(i=0;status==EXR_OK && i<n;i++) {
    exr_page_annotation *v=&entries[i]; const exr_page_annotation *s=&source[i]; exr_metadata_entry *properties; double *quads;
    status=exr_control_cancel(control,&local); if(status!=EXR_OK) break;
    if(!s->kind || !s->kind[0] || (s->quad_count && !s->quads) || (s->property_count && !s->properties)) { status=exr_fail(&local,EXR_FORMAT,"Missing annotation fields"); break; }
    memcpy(v->bounds,s->bounds,sizeof(v->bounds));
    for(j=0;j<4;j++) if(!isfinite(v->bounds[j]) || fabs(v->bounds[j])>1e7) { status=exr_fail(&local,EXR_FORMAT,"Invalid annotation bounds"); break; }
    if(status!=EXR_OK) break;
    if(v->bounds[0]>v->bounds[2] || v->bounds[1]>v->bounds[3]) { status=exr_fail(&local,EXR_FORMAT,"Reversed annotation bounds"); break; }
    status=copy_string(s->id,&bytes,&v->id,&local); if(status==EXR_OK) status=copy_string(s->kind,&bytes,&v->kind,&local); if(status!=EXR_OK) break;
    if(s->quad_count>((size_t)8*1024*1024-bytes)/(8*sizeof(double))) { status=exr_fail(&local,EXR_LIMIT,"Annotation quads exceed 8 MiB snapshot budget"); break; }
    if(s->quad_count) {
      size_t payload=s->quad_count*8*sizeof(double); quads=malloc(payload); if(!quads) { status=exr_fail(&local,EXR_MEMORY,"Annotation quads allocation failed"); break; }
      v->quads=quads; v->quad_count=s->quad_count; bytes+=payload;
      for(j=0;j<s->quad_count*8;j++) { quads[j]=s->quads[j]; if(!isfinite(quads[j]) || fabs(quads[j])>1e7) { status=exr_fail(&local,EXR_FORMAT,"Invalid annotation quad coordinate"); break; } }
      if(status!=EXR_OK) break;
    }
    if(s->property_count>4096 || s->property_count>((size_t)8*1024*1024-bytes)/sizeof(*properties)) { status=exr_fail(&local,EXR_LIMIT,"Annotation properties exceed snapshot budget"); break; }
    if(!s->property_count) continue;
    properties=calloc(s->property_count,sizeof(*properties)); if(!properties) { status=exr_fail(&local,EXR_MEMORY,"Annotation properties allocation failed"); break; }
    v->properties=properties; v->property_count=s->property_count; bytes+=s->property_count*sizeof(*properties);
    for(j=0;status==EXR_OK && j<s->property_count;j++) {
      if(!s->properties[j].key || !s->properties[j].key[0] || !s->properties[j].value) { status=exr_fail(&local,EXR_FORMAT,"Missing annotation property"); break; }
      status=copy_string(s->properties[j].key,&bytes,&properties[j].key,&local);
      if(status==EXR_OK) status=copy_string(s->properties[j].value,&bytes,&properties[j].value,&local);
    }
  }
  if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_READ,1,1,&local);
  if(status==EXR_OK) { *out=entries; *count=n; } else exr_page_annotations_free(entries,n);
  return provider_end(d,status,&local,e);
}
exr_status exr_fixed_load_text(exr_fixed_document *d,size_t page,const exr_control *control,exr_fixed_text **out,exr_error *e) {
  exr_fixed_text *text=NULL; exr_error local={0}; exr_status status;
  if(out) *out=NULL;
  if(!d || !out || page>=d->count || d->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant fixed text load");
  if(!d->text) return exr_fail(e,EXR_FORMAT,"Fixed document has no text provider");
  d->busy=1; status=exr_control_poll(control,EXR_STAGE_READ,0,1,&local);
  if(status==EXR_OK) status=d->text(d->context,page,control,&text,&local);
  if(status==EXR_OK && local.code!=EXR_OK) status=local.code;
  if(status==EXR_OK && !text) status=exr_fail(&local,EXR_FORMAT,"Fixed text provider returned no snapshot");
  if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_READ,1,1,&local);
  status=provider_end(d,status,&local,e);
  if(status==EXR_OK) *out=text; else exr_fixed_text_free(text);
  return status;
}
exr_status exr_fixed_draw(exr_fixed_document *d,size_t page,const double matrix[6],const exr_draw_sink *sink,const exr_control *control,exr_error *e) {
  const double identity[6]={1,0,0,1,0,0}; double transform[6]; exr_draw_sink consumer; exr_error local={0}; exr_status status; size_t i;
  if(!d || page>=d->count || !sink || (!sink->path && !sink->image && !sink->clip && !sink->state) || d->busy)
    return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant fixed page draw");
  memcpy(transform,matrix ? matrix : identity,sizeof(transform)); consumer=*sink;
  for(i=0;i<6;i++) if(!isfinite(transform[i]) || fabs(transform[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed page drawing matrix");
  d->busy=1; status=exr_control_poll(control,EXR_STAGE_RENDER,0,1,&local);
  if(status==EXR_OK) status=d->draw(d->context,page,transform,&consumer,control,&local);
  if(status==EXR_OK && local.code!=EXR_OK) status=local.code;
  if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_RENDER,1,1,&local);
  return provider_end(d,status,&local,e);
}
exr_status exr_fixed_draw_ex(exr_fixed_document *d,size_t page,const double matrix[6],const exr_draw_sink_ex *sink,const exr_control *control,exr_error *e) {
  const double identity[6]={1,0,0,1,0,0};double transform[6];exr_draw_sink_ex consumer;
  exr_error local={0};exr_status status;size_t i;
  status=exr_draw_sink_snapshot(sink,&consumer,e);if(status!=EXR_OK) return status;
  if(!d || page>=d->count || (!consumer.base.path && !consumer.base.image && !consumer.base.clip && !consumer.base.state) || d->busy)
    return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant extended page draw");
  memcpy(transform,matrix ? matrix : identity,sizeof(transform));
  for(i=0;i<6;i++) if(!isfinite(transform[i]) || fabs(transform[i])>1e7) return exr_fail(e,EXR_ARGUMENT,"Invalid fixed page drawing matrix");
  d->busy=1;status=exr_control_poll(control,EXR_STAGE_RENDER,0,1,&local);
  if(status==EXR_OK) status=d->draw_ex ? d->draw_ex(d->context,page,transform,&consumer,control,&local) : d->draw(d->context,page,transform,&consumer.base,control,&local);
  if(status==EXR_OK && local.code!=EXR_OK) status=local.code;
  if(status==EXR_OK) status=exr_control_poll(control,EXR_STAGE_RENDER,1,1,&local);
  return provider_end(d,status,&local,e);
}
exr_status exr_fixed_render(exr_fixed_document *d,size_t page,double scale,const exr_fixed_render_options *options,exr_bitmap *out,exr_error *e) {
  exr_canvas_config config={0}; exr_canvas *canvas=NULL; exr_draw_sink_ex sink={0}; exr_viewport view; exr_path_segment clip[5]={0}; exr_status status;int gray=0;
  if(out) memset(out,0,sizeof(*out));
  if(!d || page>=d->count || !out || d->busy) return exr_fail(e,EXR_ARGUMENT,"Invalid or reentrant fixed page render");
  if(options) { config.channels=options->channels; config.background=options->background; config.mask_budget=options->mask_budget; config.control=options->control; }
  else { config.channels=4; config.background=0xffffffff; }
  if(config.channels==1 && d->draw_ex) { gray=1;config.channels=4;config.background|=255; }
  if(exr_control_cancel(&config.control,e)!=EXR_OK) return EXR_CANCELLED;
  status=exr_viewport_create(&d->pages[page].geometry,scale,&view,e); if(status!=EXR_OK) return status;
  if(view.width>16384 || view.height>16384) return exr_fail(e,EXR_LIMIT,"Fixed page bitmap dimensions exceed 16384");
  config.width=(uint32_t)ceil(view.width); config.height=(uint32_t)ceil(view.height);
  status=exr_canvas_create(&config,&canvas,e); if(status!=EXR_OK) return status;
  clip[0].verb=EXR_PATH_MOVE; clip[1].verb=EXR_PATH_LINE; clip[1].points[0]=(exr_path_point){view.width,0};
  clip[2].verb=EXR_PATH_LINE; clip[2].points[0]=(exr_path_point){view.width,view.height};
  clip[3].verb=EXR_PATH_LINE; clip[3].points[0]=(exr_path_point){0,view.height}; clip[4].verb=EXR_PATH_CLOSE;
  status=exr_canvas_clip(canvas,clip,5,NULL,EXR_FILL_NONZERO,e);
  sink.struct_size=sizeof(sink);
  if(status==EXR_OK) status=exr_canvas_get_sink_ex(canvas,&sink,e);
  if(status==EXR_OK) status=exr_fixed_draw_ex(d,page,view.matrix,&sink,&config.control,e);
  if(status==EXR_OK) status=exr_canvas_take(canvas,out,e);
  if(status==EXR_OK && gray) status=exr_bitmap_to_gray(out,&config.control,e);
  if(status!=EXR_OK) exr_bitmap_free(out);
  exr_canvas_free(canvas); return status;
}
