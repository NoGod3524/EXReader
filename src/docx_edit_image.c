/* SPDX-License-Identifier: MIT */
#include "docx_edit_internal.h"
#include <exr/graphics.h>
#include <math.h>
#define REL "http://schemas.openxmlformats.org/package/2006/relationships"
#define CT "http://schemas.openxmlformats.org/package/2006/content-types"
#define WP "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
#define WPS "http://purl.oclc.org/ooxml/drawingml/wordprocessingDrawing"
#define A "http://schemas.openxmlformats.org/drawingml/2006/main"
#define AS "http://purl.oclc.org/ooxml/drawingml/main"
#define PIC "http://schemas.openxmlformats.org/drawingml/2006/picture"
#define PICS "http://purl.oclc.org/ooxml/drawingml/picture"
static int put(exr_buffer *b,const char *s) { return exr_append(b,s,strlen(s)); }
static int local(const exr_node *n,const char *space,const char *name) {
  size_t length=strlen(space);
  return n->name && !strncmp(n->name,space,length) && n->name[length]=='|' && !strcmp(n->name+length+1,name);
}
static int escape(exr_buffer *b,const char *s) {
  for (;*s;s++) if (!put(b,*s=='&' ? "&amp;" : *s=='\"' ? "&quot;" : *s=='<' ? "&lt;" : *s=='>' ? "&gt;" : (char[2]){*s,0})) return 0;
  return 1;
}
exr_status exr_edit_insert_image(exr_edit_doc *d,exr_edit_id after,const void *bytes,size_t size,double width,double height,exr_edit_id *id) {
  exr_edit_image im={0}; exr_edit_block b={0}; exr_bitmap bitmap={0}; exr_status s=exr_edit_ready(d);
  if (id) *id=0;
  if (s) return s;
  if (!id || !bytes || !size || !isfinite(width) || !isfinite(height) || width<=0 || height<=0 ||
      width>(double)INT32_MAX/12700 || height>(double)INT32_MAX/12700) return exr_edit_failure(d,EXR_ARGUMENT);
  if (size>EXR_MAX_INPUT) return exr_edit_failure(d,EXR_LIMIT);
  im.format=(unsigned)exr_image_format_detect(bytes,size);
  if (im.format<EXR_EDIT_IMAGE_PNG || im.format>EXR_EDIT_IMAGE_BMP) return exr_edit_failure(d,EXR_FORMAT);
  im.jpeg=im.format==EXR_EDIT_IMAGE_JPEG;
  s=exr_image_decode(bytes,size,&bitmap,NULL); exr_bitmap_free(&bitmap);
  if (s) return exr_edit_failure(d,s);
  im.data=bytes; im.size=size; im.width_emu=(int64_t)llround(width*12700); im.height_emu=(int64_t)llround(height*12700);
  if (!im.width_emu || !im.height_emu) return exr_edit_failure(d,EXR_ARGUMENT);
  b.kind=EXR_EDIT_IMAGE; b.image=&im;
  return exr_edit_insert_block(d,after,&b,id);
}

/* Remove only drawing/pict elements, keeping text, rPr, bookmarks and other
   children even when Word stored them in the same opaque run. */
static int contains_image(const source_xml *x,size_t n) {
  size_t i;
  for (i=n+1;i<x->tree->node_count && x->spans[i].start<x->spans[n].end;i++) {
    const exr_node *v=x->tree->nodes+i;
    if (local(v,A,"blip") || local(v,AS,"blip") || local(v,"urn:schemas-microsoft-com:vml","imagedata")) return 1;
  }
  return 0;
}
static int strip_image(exr_buffer *out,const source_xml *x,const exr_edit_run *r,int *found) {
  size_t i,n=NONE,at,end;
  *found=0;
  if (r->kind!=EXR_EDIT_OPAQUE_RUN || !r->opaque_size) return 1;
  for (i=0;i<x->tree->node_count;i++) if (x->tree->nodes[i].name &&
      x->spans[i].end-x->spans[i].start==r->opaque_size && !memcmp(x->bytes+x->spans[i].start,r->opaque_xml,r->opaque_size)) { n=i; break; }
  if (n==NONE) return 1;
  at=x->spans[n].start; end=x->spans[n].end;
  for (i=n;i<x->tree->node_count && x->spans[i].start<end;i++) if (x->tree->nodes[i].name &&
      x->spans[i].start>=at && (exr_edit_xml_word(x->tree->nodes+i,"drawing") || exr_edit_xml_word(x->tree->nodes+i,"pict")) && contains_image(x,i)) {
    if (!exr_append(out,x->bytes+at,x->spans[i].start-at)) return 0;
    at=x->spans[i].end; *found=1;
  }
  return !*found || exr_append(out,x->bytes+at,end-at);
}
static exr_status delete_from_paragraph(exr_edit_doc *d,const source_xml *x,const exr_edit_block *p,
    exr_edit_id id,exr_edit_block *out,exr_edit_run **allocated,int *found) {
  size_t i; exr_edit_run *runs; exr_status s=EXR_OK;
  *allocated=NULL; *found=0; *out=*p;
  if (p->kind!=EXR_EDIT_PARAGRAPH) return EXR_OK;
  if (p->run_count>SIZE_MAX/sizeof(*runs)/2) return EXR_LIMIT;
  runs=calloc(p->run_count*2,sizeof(*runs)); if (p->run_count && !runs) return EXR_MEMORY;
  if (p->run_count) memcpy(runs+p->run_count,p->runs,p->run_count*sizeof(*runs));
  for (i=0;i<p->run_count;i++) {
    exr_buffer xml={0}; int removed=0; runs[i]=p->runs[i];
    if (p->id==id || p->runs[i].id==id) {
      if (!strip_image(&xml,x,p->runs+i,&removed)) { free(xml.data); s=EXR_MEMORY; break; }
      if (removed) { runs[i].opaque_xml=xml.data; runs[i].opaque_size=xml.size; *found=1; }
      else free(xml.data);
    }
  }
  if (s || !*found) {
    for (i=0;i<p->run_count;i++) if (runs[i].opaque_xml && runs[i].opaque_xml!=p->runs[i].opaque_xml) free((void *)runs[i].opaque_xml);
    free(runs); return s;
  }
  out->runs=runs; *allocated=runs; (void)d; return EXR_OK;
}
static void free_changed_runs(size_t count,exr_edit_run *runs) {
  size_t i;
  if (!runs) return;
  for (i=0;i<count;i++) if (runs[i].opaque_xml!=runs[count+i].opaque_xml) free((void *)runs[i].opaque_xml);
  free(runs);
}
exr_status exr_edit_delete_image(exr_edit_doc *d,exr_edit_id id) {
  const exr_edit_part *parts,*part; size_t count,i,j,k,l; char main[2048]; source_xml x={0};
  exr_status s=exr_edit_ready(d);
  if (s) return s;
  if (!id) return exr_edit_failure(d,EXR_ARGUMENT);
  { const exr_edit_block *b=exr_edit_find_block(d,id);
    if (b && b->kind==EXR_EDIT_IMAGE) {
      if (!b->image->anchor_run_id) return exr_edit_replace(d,id,NULL);
      return exr_edit_delete_block(d,id);
    }
  }
  parts=exr_edit_parts(d,&count); s=exr_edit_main_part(parts,count,main,NULL);
  if (s) return exr_edit_failure(d,EXR_ARGUMENT);
  part=exr_edit_part_named(parts,count,main);
  if (!part) return exr_edit_failure(d,EXR_ARGUMENT);
  s=exr_edit_xml_parse(&x,part->data,part->size,"document",NULL); if (s) return exr_edit_failure(d,s);
  for (i=0;i<exr_edit_block_count(d);i++) {
    const exr_edit_block *b=exr_edit_block_at(d,i); exr_edit_block v; exr_edit_run *runs; int found;
    s=delete_from_paragraph(d,&x,b,id,&v,&runs,&found); if (s) goto done;
    if (found) { size_t nr=b->run_count; s=exr_edit_replace(d,b->id,&v); free_changed_runs(nr,runs); goto done; }
    if (!b->table) continue;
    for (j=0;j<b->table->row_count;j++) for (k=0;k<b->table->rows[j].cell_count;k++) {
      const exr_edit_cell *cell=b->table->rows[j].cells+k;
      for (l=0;l<cell->block_count;l++) {
        const exr_edit_block *p=cell->blocks+l;
        s=delete_from_paragraph(d,&x,p,id,&v,&runs,&found); if (s) goto done;
        if (found) {
          size_t nr=p->run_count;
          exr_edit_table t=*b->table; exr_edit_block block=*b,*ps=malloc(cell->block_count*sizeof(*ps));
          exr_edit_row *rows=malloc(t.row_count*sizeof(*rows));
          exr_edit_cell *cells=malloc(t.rows[j].cell_count*sizeof(*cells));
          if (!ps || !rows || !cells) s=EXR_MEMORY;
          else {
            memcpy(rows,t.rows,t.row_count*sizeof(*rows)); memcpy(cells,t.rows[j].cells,t.rows[j].cell_count*sizeof(*cells));
            memcpy(ps,cell->blocks,cell->block_count*sizeof(*ps)); ps[l]=v; cells[k].blocks=ps;
            if (!(cells[k].changed&CELL_REPLACED)) cells[k].changed|=CELL_PATCHED;
            rows[j].cells=cells; t.rows=rows; block.table=&t; s=exr_edit_replace(d,b->id,&block);
          }
          free(ps); free(rows); free(cells); free_changed_runs(nr,runs); goto done;
        }
      }
    }
  }
  s=EXR_ARGUMENT;
done:
  exr_edit_xml_free(&x); return s ? exr_edit_failure(d,s) : EXR_OK;
}

static void relpath(const char *main,char path[2048]) {
  const char *slash=strrchr(main,'/'); size_t dir=slash ? (size_t)(slash-main)+1 : 0;
  snprintf(path,2048,"%.*s_rels/%s.rels",(int)dir,main,main+dir);
}
static unsigned image_format(const exr_edit_image *im) { return im->format ? im->format : im->jpeg ? EXR_EDIT_IMAGE_JPEG : EXR_EDIT_IMAGE_PNG; }
static const char *image_extension(const exr_edit_image *im) {
  static const char *ext[]={"", "png", "jpeg", "gif", "bmp"}; return ext[image_format(im)];
}
static const char *image_mime(const exr_edit_image *im) {
  static const char *mime[]={"", "image/png", "image/jpeg", "image/gif", "image/bmp"}; return mime[image_format(im)];
}
/* Assign source IDs before creating anchor views, including protected cells. */
static void source_ids(exr_edit_block *b,exr_edit_id *next) {
  size_t i,j,k; b->id=(*next)++;
  for (i=0;i<b->run_count;i++) ((exr_edit_run *)b->runs)[i].id=(*next)++;
  if (b->table) for (i=0;i<b->table->row_count;i++) {
    exr_edit_row *r=(exr_edit_row *)b->table->rows+i; r->id=(*next)++;
    for (j=0;j<r->cell_count;j++) {
      exr_edit_cell *c=(exr_edit_cell *)r->cells+j; c->id=(*next)++;
      for (k=0;k<c->block_count;k++) source_ids((exr_edit_block *)c->blocks+k,next);
    }
  }
}
static int64_t emu(const char *s) {
  char *end; long long v;
  if (!s || !*s || strlen(s)>18) return 0;
  v=strtoll(s,&end,10); return !*end && v>0 ? (int64_t)v : 0;
}
static int64_t vml_size(const char *style,const char *key) {
  const char *p=style; size_t len=strlen(key);
  while (p && *p) {
    char *end; double v,scale; const char *colon;
    while (*p==' ' || *p=='\t' || *p==';') p++;
    colon=strchr(p,':'); if (!colon) break;
    if ((size_t)(colon-p)==len && !memcmp(p,key,len)) {
      v=strtod(colon+1,&end);
      while (*end==' ') end++;
      scale=!strncmp(end,"pt",2) ? 12700 : !strncmp(end,"px",2) ? 9525 :
        !strncmp(end,"in",2) ? 914400 : !strncmp(end,"cm",2) ? 360000 :
        !strncmp(end,"mm",2) ? 36000 : !strncmp(end,"pc",2) ? 152400 : 0;
      if (isfinite(v) && v>0 && scale && v*scale<(double)INT64_MAX) return (int64_t)llround(v*scale);
      return 0;
    }
    p=strchr(colon,';');
  }
  return 0;
}
static exr_status decode_paragraph_images(const source_xml *x,const source_xml *rels,
    const exr_edit_part *parts,size_t np,const char *main,const exr_edit_block *p,
    exr_edit_block **out,size_t *count,size_t *capacity) {
  size_t r,n,j,k;
  for (r=0;r<p->run_count;r++) {
    const exr_edit_run *run=p->runs+r; size_t start=NONE;
    if (run->kind!=EXR_EDIT_OPAQUE_RUN || !run->opaque_size || !memchr(run->opaque_xml,'<',run->opaque_size)) continue;
    for (n=0;n<x->tree->node_count;n++) if (x->tree->nodes[n].name &&
        run->opaque_size==x->spans[n].end-x->spans[n].start && run->opaque_size &&
        !memcmp(run->opaque_xml,x->bytes+x->spans[n].start,run->opaque_size)) { start=n; break; }
    if (start==NONE) continue;
    for (n=start;n<x->tree->node_count && x->spans[n].start<x->spans[start].end;n++) {
      exr_edit_image im={0}; exr_edit_block b={0}; const char *rid=NULL; size_t refs=0;
      const exr_edit_part *media=NULL; exr_bitmap bitmap={0}; exr_status status;
      if (!exr_edit_xml_word(x->tree->nodes+n,"drawing") && !exr_edit_xml_word(x->tree->nodes+n,"pict")) continue;
      for (j=n+1;j<x->tree->node_count && x->spans[j].start<x->spans[n].end;j++) {
        const exr_node *v=x->tree->nodes+j;
        if (local(v,A,"blip") || local(v,AS,"blip")) { rid=exr_edit_xml_attribute(v,R,RS,"embed"); refs++; }
        if (local(v,"urn:schemas-microsoft-com:vml","imagedata")) { rid=exr_edit_xml_attribute(v,R,RS,"id"); refs++; }
        if (local(v,WP,"extent") || local(v,WPS,"extent")) {
          im.width_emu=emu(exr_node_attribute(v,"cx")); im.height_emu=emu(exr_node_attribute(v,"cy"));
        }
        if (local(v,"urn:schemas-microsoft-com:vml","shape")) {
          const char *style=exr_node_attribute(v,"style"); im.width_emu=vml_size(style,"width"); im.height_emu=vml_size(style,"height");
        }
      }
      if (refs!=1 || !rid || !rels->tree) continue;
      for (k=0;k<rels->tree->node_count;k++) {
        const exr_node *v=rels->tree->nodes+k; const char *id=exr_node_attribute(v,"Id");
        const char *type=exr_node_attribute(v,"Type"),*target=exr_node_attribute(v,"Target"),*mode=exr_node_attribute(v,"TargetMode"); char path[2048];
        if (local(v,REL,"Relationship") && id && !strcmp(id,rid) && type &&
            (!strcmp(type,R "/image") || !strcmp(type,RS "/image")) && target &&
            (!mode || strcmp(mode,"External")) && exr_resolve_path(main,target,path)) media=exr_edit_part_named(parts,np,path);
      }
      if (!media) continue;
      im.format=(unsigned)exr_image_format_detect(media->data,media->size);
      if (im.format<EXR_EDIT_IMAGE_PNG || im.format>EXR_EDIT_IMAGE_BMP) continue;
      status=exr_image_decode(media->data,media->size,&bitmap,NULL);
      if (status) { if (status==EXR_MEMORY) return status; continue; }
      if (!im.width_emu) im.width_emu=(int64_t)bitmap.width*9525;
      if (!im.height_emu) im.height_emu=(int64_t)bitmap.height*9525;
      exr_bitmap_free(&bitmap);
      im.data=media->data; im.size=media->size; im.jpeg=im.format==EXR_EDIT_IMAGE_JPEG; im.anchor_run_id=run->id;
      im.anchor_offset=x->spans[n].start-x->spans[start].start;
      b.kind=EXR_EDIT_IMAGE; b.section_id=p->section_id;
      b.opaque_xml=x->bytes+x->spans[n].start; b.opaque_size=x->spans[n].end-x->spans[n].start;
      b.image=malloc(sizeof(im)); if (!b.image) return EXR_MEMORY;
      memcpy((void *)b.image,&im,sizeof(im));
      if (!exr_grow((void **)out,capacity,*count+1,sizeof(**out))) { free((void *)b.image); return EXR_MEMORY; }
      (*out)[(*count)++]=b;
    }
  }
  return EXR_OK;
}
static exr_status decode_owner_images(const source_xml *x,const source_xml *rels,
    const exr_edit_part *parts,size_t np,const char *main,const exr_edit_block *b,
    exr_edit_block **out,size_t *count,size_t *capacity) {
  size_t i,j,k; exr_status status;
  if (b->kind==EXR_EDIT_PARAGRAPH) return decode_paragraph_images(x,rels,parts,np,main,b,out,count,capacity);
  if (b->table) for (i=0;i<b->table->row_count;i++) for (j=0;j<b->table->rows[i].cell_count;j++) {
    const exr_edit_cell *c=b->table->rows[i].cells+j;
    for (k=0;k<c->block_count;k++) {
      exr_edit_block p=c->blocks[k]; p.section_id=b->section_id;
      status=decode_owner_images(x,rels,parts,np,main,&p,out,count,capacity); if (status) return status;
    }
  }
  return EXR_OK;
}
exr_status exr_edit_images_decode(const source_xml *x,const exr_edit_part *parts,size_t np,
    const char *main,exr_edit_block **blocks,size_t *count,size_t sections) {
  exr_edit_block *out=NULL; size_t n=0,capacity=0,i; exr_edit_id next=sections+1;
  source_xml rels={0}; char rp[2048]; const exr_edit_part *part; exr_status status=EXR_OK;
  relpath(main,rp); part=exr_edit_part_named(parts,np,rp);
  if (part) { status=exr_edit_xml_parse(&rels,part->data,part->size,"Relationships",NULL); if (status) return status; }
  for (i=0;i<*count;i++) source_ids(*blocks+i,&next);
  for (i=0;i<*count;i++) {
    if (!exr_grow((void **)&out,&capacity,n+1,sizeof(*out))) { status=EXR_MEMORY; break; }
    out[n++]=(*blocks)[i];
    status=decode_owner_images(x,&rels,parts,np,main,*blocks+i,&out,&n,&capacity); if (status) break;
  }
  exr_edit_xml_free(&rels);
  if (status) { for (i=0;i<n;i++) free((void *)out[i].image); free(out); return status; }
  free(*blocks); *blocks=out; *count=n; return EXR_OK;
}
static int rel_id(const source_xml *x,const char *id) {
  size_t i;
  if (!x->tree) return 0;
  for (i=0;i<x->tree->node_count;i++) {
    const char *v=exr_node_attribute(x->tree->nodes+i,"Id"); if (v && !strcmp(v,id)) return 1;
  }
  return 0;
}
exr_status exr_edit_images_prepare(const exr_edit_doc *d,const char *main,const source_xml *x,edit_image_output **out,size_t *count) {
  const exr_edit_part *parts,*p; size_t np,i,k=0; char rp[2048]; source_xml rels={0};
  uint32_t drawing=0; exr_status s=EXR_OK; edit_image_output *images=NULL;
  *out=NULL; *count=0; parts=exr_edit_parts(d,&np); relpath(main,rp); p=exr_edit_part_named(parts,np,rp);
  if (p) { s=exr_edit_xml_parse(&rels,p->data,p->size,"Relationships",NULL); if (s) return s; }
  if (x->tree) for (i=0;i<x->tree->node_count;i++) {
    const exr_node *n=x->tree->nodes+i;
    if (local(n,WP,"docPr") || local(n,WPS,"docPr")) {
      const char *v=exr_node_attribute(n,"id"); char *end; unsigned long long value;
      if (!v) continue;
      value=strtoull(v,&end,10); if (!*end && value<=UINT32_MAX && value>drawing) drawing=(uint32_t)value;
    }
  }
  for (i=0;i<exr_edit_block_count(d);i++) if (exr_edit_block_at(d,i)->kind==EXR_EDIT_IMAGE && !exr_edit_block_at(d,i)->image->anchor_run_id) k++;
  if (k) { images=calloc(k,sizeof(*images)); if (!images) { s=EXR_MEMORY; goto done; } }
  k=0;
  for (i=0;i<exr_edit_block_count(d);i++) {
    const exr_edit_block *b=exr_edit_block_at(d,i); edit_image_output *im; unsigned suffix=0;
    const char *slash; size_t dir;
    if (b->kind!=EXR_EDIT_IMAGE || b->image->anchor_run_id) continue;
    if (drawing==UINT32_MAX) { s=EXR_LIMIT; goto done; }
    im=images+k++; im->block=b; im->drawing_id=++drawing; slash=strrchr(main,'/'); dir=slash ? (size_t)(slash-main)+1 : 0;
    do {
      int length=snprintf(im->target,sizeof(im->target),"media/exr-image-%llu-%u.%s",(unsigned long long)b->id,suffix++,image_extension(b->image));
      if (length<0 || dir+(size_t)length>=sizeof(im->part)) { s=EXR_LIMIT; goto done; }
      memcpy(im->part,main,dir); strcpy(im->part+dir,im->target);
    } while (exr_edit_part_named(parts,np,im->part));
    suffix=0;
    do { snprintf(im->rid,sizeof(im->rid),"exrImage%llu_%u",(unsigned long long)b->id,suffix++); } while (rel_id(&rels,im->rid));
  }
  *out=images; *count=k; images=NULL;
done:
  free(images); exr_edit_xml_free(&rels); return s;
}
int exr_edit_image_write(exr_buffer *b,const source_xml *x,const edit_image_output *im) {
  const exr_edit_image *p=im->block->image; char values[512];
  int strict=!strcmp(exr_edit_xml_ns(x),WS);
  const char *r=strict ? RS : R,*wp=strict ? WPS : WP,*a=strict ? AS : A,*pic=strict ? PICS : PIC;
  if (!put(b,"<w:p xmlns:w=\"") || !put(b,exr_edit_xml_ns(x)) || !put(b,"\" xmlns:r=\"") || !put(b,r) ||
      !put(b,"\" xmlns:wp=\"") || !put(b,wp) || !put(b,"\" xmlns:a=\"") || !put(b,a) || !put(b,"\" xmlns:pic=\"") || !put(b,pic) ||
      !put(b,"\"><w:pPr><w:spacing w:line=\"480\" w:lineRule=\"auto\"/></w:pPr><w:r><w:drawing><wp:inline><wp:extent ")) return 0;
  snprintf(values,sizeof(values),"cx=\"%lld\" cy=\"%lld\"/><wp:docPr id=\"%u\" name=\"Image %u\"/>",
    (long long)p->width_emu,(long long)p->height_emu,im->drawing_id,im->drawing_id);
  if (!put(b,values) || !put(b,"<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect=\"1\"/></wp:cNvGraphicFramePr><a:graphic><a:graphicData uri=\"") || !put(b,pic) ||
      !put(b,"\"><pic:pic><pic:nvPicPr><pic:cNvPr id=\"0\" name=\"image\"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed=\"") || !put(b,im->rid) ||
      !put(b,"\"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext ")) return 0;
  snprintf(values,sizeof(values),"cx=\"%lld\" cy=\"%lld\"/>",(long long)p->width_emu,(long long)p->height_emu);
  return put(b,values) && put(b,"</a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>");
}

static int referenced(const source_xml *x,const char *id) {
  size_t i,j;
  if (!x->tree) return 0;
  for (i=0;i<x->tree->node_count;i++) for (j=0;j<x->tree->nodes[i].attribute_count;j++) {
    const exr_attribute *a=x->tree->nodes[i].attributes+j;
    if ((!strncmp(a->name,R "|",sizeof(R)) || !strncmp(a->name,RS "|",sizeof(RS))) && !strcmp(a->value,id)) return 1;
  }
  return 0;
}
typedef struct { const char *id; char target[2048]; } removed_rel;
static int xml_append_tail(exr_buffer *b,const source_xml *x,size_t at) {
  return exr_append(b,x->bytes+at,x->spans[x->root].close-at);
}
static int relationship(exr_buffer *b,const edit_image_output *im,int strict) {
  return put(b,"<Relationship xmlns=\"" REL "\" Id=\"") && put(b,im->rid) && put(b,"\" Type=\"") &&
    put(b,strict ? RS : R) && put(b,"/image\" Target=\"") && escape(b,im->target) && put(b,"\"/>");
}
/* Keep source defaults (including unusual MIME declarations) and use a precise
   per-part Override if a new extension conflicts with an existing declaration. */
static int content_types(exr_buffer *b,const exr_edit_part *part,const edit_image_output *images,size_t count,
    const removed_rel *removed,size_t nr,const unsigned char *keep) {
  source_xml x={0}; size_t i,j,at; int seen[5]={0}; exr_status s;
  if (!part) return 0;
  s=exr_edit_xml_parse(&x,part->data,part->size,"Types",NULL); if (s) return 0;
  if (!exr_append(b,x.bytes,x.spans[x.root].start) || !exr_edit_xml_start(b,&x,x.root,"Types")) goto fail;
  at=x.spans[x.root].open;
  for (i=x.tree->nodes[x.root].first_child;i!=NONE;i=x.tree->nodes[i].next_sibling) if (x.tree->nodes[i].name) {
    const exr_node *n=x.tree->nodes+i; int drop=0;
    if (local(n,CT,"Default")) {
      const char *ext=exr_node_attribute(n,"Extension"),*type=exr_node_attribute(n,"ContentType");
      for (j=0;j<count;j++) if (ext && !strcmp(ext,image_extension(images[j].block->image)))
        seen[image_format(images[j].block->image)]=type && !strcmp(type,image_mime(images[j].block->image)) ? 1 : -1;
    }
    if (local(n,CT,"Override")) {
      const char *name=exr_node_attribute(n,"PartName");
      for (j=0;j<nr;j++) if (!keep[j] && name && name[0]=='/' && !strcmp(name+1,removed[j].target)) drop=1;
    }
    if (!exr_append(b,x.bytes+at,x.spans[i].start-at) || (!drop && !exr_edit_xml_raw(b,&x,i))) goto fail;
    at=x.spans[i].end;
  }
  if (!xml_append_tail(b,&x,at)) goto fail;
  for (i=0;i<count;i++) {
    int *declared=seen+image_format(images[i].block->image);
    const char *ext=image_extension(images[i].block->image),*mime=image_mime(images[i].block->image);
    if (!*declared) {
      if (!put(b,"<Default xmlns=\"" CT "\" Extension=\"") || !put(b,ext) || !put(b,"\" ContentType=\"") || !put(b,mime) || !put(b,"\"/>")) goto fail;
      *declared=1;
    } else if (*declared<0 && (!put(b,"<Override xmlns=\"" CT "\" PartName=\"/") || !escape(b,images[i].part) || !put(b,"\" ContentType=\"") || !put(b,mime) || !put(b,"\"/>"))) goto fail;
  }
  if (!exr_edit_xml_end(b,&x,x.root,"Types") || !exr_append(b,x.bytes+x.spans[x.root].end,x.size-x.spans[x.root].end)) goto fail;
  exr_edit_xml_free(&x); return 1;
fail:
  exr_edit_xml_free(&x); return 0;
}
exr_status exr_edit_images_package(mz_zip_archive *zip,const exr_edit_part *parts,size_t count,const char *main,
    const exr_buffer *xml,const edit_image_output *images,size_t ni,exr_error *e) {
  char rp[2048]; const exr_edit_part *relpart,*original; source_xml rels={0},old={0},now={0};
  removed_rel *removed=NULL; unsigned char *keep=NULL; size_t nr=0,i,j,at; exr_buffer relbuf={0},types={0};
  exr_status s=EXR_MEMORY;
  /* New documents receive their base OPC parts from the bridge. */
  if (!count) {
    if (!ni) return EXR_OK;
    return EXR_ARGUMENT;
  }
  relpath(main,rp); relpart=exr_edit_part_named(parts,count,rp); original=exr_edit_part_named(parts,count,main);
  if (relpart) { s=exr_edit_xml_parse(&rels,relpart->data,relpart->size,"Relationships",e); if (s) goto done; }
  if (original) { s=exr_edit_xml_parse(&old,original->data,original->size,"document",e); if (s) goto done; }
  s=exr_edit_xml_parse(&now,xml->data,xml->size,"document",e); if (s) goto done;
  s=EXR_MEMORY;
  if (rels.tree) {
    removed=calloc(rels.tree->node_count,sizeof(*removed)); keep=calloc(rels.tree->node_count,1);
    if (!removed || !keep) goto done;
    for (i=rels.tree->nodes[rels.root].first_child;i!=NONE;i=rels.tree->nodes[i].next_sibling) {
      const exr_node *n=rels.tree->nodes+i; const char *id=exr_node_attribute(n,"Id"),*type=exr_node_attribute(n,"Type");
      const char *target=exr_node_attribute(n,"Target"),*mode=exr_node_attribute(n,"TargetMode");
      if (local(n,REL,"Relationship") && id && target && type && (!strcmp(type,R "/image") || !strcmp(type,RS "/image")) &&
          referenced(&old,id) && !referenced(&now,id)) {
        removed[nr].id=id;
        if ((!mode || strcmp(mode,"External")) && !exr_resolve_path(main,target,removed[nr].target)) { s=EXR_FORMAT; goto done; }
        nr++;
      }
    }
  }
  if (ni || nr) {
    if (relpart) {
      if (!exr_append(&relbuf,rels.bytes,rels.spans[rels.root].start) || !exr_edit_xml_start(&relbuf,&rels,rels.root,"Relationships")) goto done;
    }
    else if (!put(&relbuf,"<Relationships xmlns=\"" REL "\">")) goto done;
    at=rels.tree ? rels.spans[rels.root].open : 0;
    if (rels.tree) for (i=rels.tree->nodes[rels.root].first_child;i!=NONE;i=rels.tree->nodes[i].next_sibling) if (rels.tree->nodes[i].name) {
      const char *id=exr_node_attribute(rels.tree->nodes+i,"Id"); int drop=0;
      for (j=0;j<nr;j++) if (id && !strcmp(id,removed[j].id)) drop=1;
      if (!exr_append(&relbuf,rels.bytes+at,rels.spans[i].start-at) || (!drop && !exr_edit_xml_raw(&relbuf,&rels,i))) goto done;
      at=rels.spans[i].end;
    }
    if (rels.tree && !xml_append_tail(&relbuf,&rels,at)) goto done;
    for (i=0;i<ni;i++) if (!relationship(&relbuf,images+i,!strcmp(exr_edit_xml_ns(&now),WS))) goto done;
    if (rels.tree) {
      if (!exr_edit_xml_end(&relbuf,&rels,rels.root,"Relationships") || !exr_append(&relbuf,rels.bytes+rels.spans[rels.root].end,rels.size-rels.spans[rels.root].end)) goto done;
    } else if (!put(&relbuf,"</Relationships>")) goto done;
    /* Every remaining OPC relationship participates, including headers, notes,
       shared images and duplicate image relationships to the same payload. */
    for (i=0;i<count;i++) {
      source_xml rx={0}; const char *name=parts[i].name,*marker=strstr(name,"_rels/"); char owner[2048]; size_t len=strlen(name),prefix;
      const void *bytes=parts[i].data; size_t size=parts[i].size;
      if (!marker || len<5 || strcmp(name+len-5,".rels")) continue;
      prefix=(size_t)(marker-name);
      if (!strcmp(name,"_rels/.rels")) owner[0]=0;
      else { memcpy(owner,name,prefix); memcpy(owner+prefix,marker+6,len-prefix-11); owner[len-11]=0; }
      if (!strcmp(name,rp)) { bytes=relbuf.data; size=relbuf.size; }
      s=exr_edit_xml_parse(&rx,bytes,size,"Relationships",e); if (s) goto done;
      for (j=0;j<rx.tree->node_count;j++) if (local(rx.tree->nodes+j,REL,"Relationship")) {
        const char *target=exr_node_attribute(rx.tree->nodes+j,"Target"),*mode=exr_node_attribute(rx.tree->nodes+j,"TargetMode"); char resolved[2048]; size_t k;
        if (target && (!mode || strcmp(mode,"External")) && exr_resolve_path(owner,target,resolved))
          for (k=0;k<nr;k++) if (!strcmp(resolved,removed[k].target)) keep[k]=1;
      }
      exr_edit_xml_free(&rx);
    }
    s=EXR_MEMORY;
    if (!content_types(&types,exr_edit_part_named(parts,count,"[Content_Types].xml"),images,ni,removed,nr,keep)) goto done;
  }
  for (i=0;i<count;i++) {
    int drop=!strcmp(parts[i].name,main);
    for (j=0;j<nr;j++) if (!keep[j] && !strcmp(parts[i].name,removed[j].target)) drop=1;
    if (drop) continue;
    if ((ni || nr) && !strcmp(parts[i].name,rp)) {
      if (!mz_zip_writer_add_mem(zip,rp,relbuf.data,relbuf.size,6)) goto done;
    } else if ((ni || nr) && !strcmp(parts[i].name,"[Content_Types].xml")) {
      if (!mz_zip_writer_add_mem(zip,parts[i].name,types.data,types.size,6)) goto done;
    } else if (!mz_zip_writer_add_mem(zip,parts[i].name,parts[i].data,parts[i].size,6)) goto done;
  }
  if (ni && !relpart && !mz_zip_writer_add_mem(zip,rp,relbuf.data,relbuf.size,6)) goto done;
  for (i=0;i<ni;i++) if (!mz_zip_writer_add_mem(zip,images[i].part,images[i].block->image->data,images[i].block->image->size,6)) goto done;
  s=EXR_OK;
done:
  exr_edit_xml_free(&rels); exr_edit_xml_free(&old); exr_edit_xml_free(&now);
  free(removed); free(keep); free(relbuf.data); free(types.data); return s;
}
