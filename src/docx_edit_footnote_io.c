/* SPDX-License-Identifier: MIT */
#include "docx_edit_internal.h"

#define REL "http://schemas.openxmlformats.org/package/2006/relationships"
#define CT "http://schemas.openxmlformats.org/package/2006/content-types"
#define NOTE_TYPE "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
static int put(exr_buffer *b,const char *s) { return exr_append(b,s,strlen(s)); }
static int escape(exr_buffer *b,const char *s,size_t n) {
  size_t i;
  for (i=0;i<n;i++) {
    const char *v=s[i]=='&' ? "&amp;" : s[i]=='<' ? "&lt;" : s[i]=='>' ? "&gt;" : s[i]=='\"' ? "&quot;" : s[i]=='\r' ? "&#13;" : NULL;
    if (!(v ? put(b,v) : exr_append(b,s+i,1))) return 0;
  }
  return 1;
}
static int relpath(const char *main,char path[2048]) {
  const char *slash=strrchr(main,'/'); size_t n=slash ? (size_t)(slash-main)+1 : 0;
  int length=snprintf(path,2048,"%.*s_rels/%s.rels",(int)n,main,main+n);
  return length>0 && length<2048;
}
static int note_type(const exr_node *n) {
  const char *s=exr_node_attribute(n,"Type");
  return s && (!strcmp(s,R "/footnotes") || !strcmp(s,RS "/footnotes"));
}
static exr_status open_notes(const exr_edit_part *parts,size_t count,const char *main,
                            source_xml *notes,char path[2048],exr_error *e) {
  char rp[2048]; const exr_edit_part *p; source_xml rels={0}; size_t i; exr_status s=EXR_OK;
  const char *slash=strrchr(main,'/'); size_t n=slash ? (size_t)(slash-main)+1 : 0;
  if (snprintf(path,2048,"%.*sfootnotes.xml",(int)n,main)>=2048 || !relpath(main,rp)) return EXR_LIMIT;
  p=exr_edit_part_named(parts,count,rp);
  if (p) {
    s=exr_edit_xml_parse(&rels,p->data,p->size,"Relationships",e); if (s) return s;
    for (i=0;i<rels.tree->node_count;i++) if (note_type(rels.tree->nodes+i)) {
      const char *target=exr_node_attribute(rels.tree->nodes+i,"Target"),*mode=exr_node_attribute(rels.tree->nodes+i,"TargetMode");
      if (!target || (mode && !strcmp(mode,"External")) || !exr_resolve_path(main,target,path)) s=EXR_FORMAT;
      break;
    }
    exr_edit_xml_free(&rels); if (s) return s;
  }
  p=exr_edit_part_named(parts,count,path);
  return p ? exr_edit_xml_parse(notes,p->data,p->size,"footnotes",e) : EXR_OK;
}
/* Only independent reference runs are modelled; compound fields/revisions stay
   opaque, so editing their neighbours cannot discard unknown inline content. */
static size_t reference(const source_xml *x,size_t r) {
  size_t i,found=NONE;
  if (r==NONE || !exr_edit_xml_word(x->tree->nodes+r,"r")) return NONE;
  for (i=x->tree->nodes[r].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
    if (exr_edit_xml_word(x->tree->nodes+i,"footnoteReference") && found==NONE) found=i;
    else if (!exr_edit_xml_word(x->tree->nodes+i,"rPr")) return NONE;
  }
  return found;
}
static size_t note_node(const source_xml *notes,const char *id) {
  size_t i;
  if (!notes->tree || !id) return NONE;
  for (i=notes->tree->nodes[notes->root].first_child;i!=NONE;i=notes->tree->nodes[i].next_sibling) {
    const char *v=exr_edit_xml_wa(notes->tree->nodes+i,"id");
    if (exr_edit_xml_word(notes->tree->nodes+i,"footnote") && v && !strcmp(v,id)) return i;
  }
  return NONE;
}
static int note_text(const source_xml *x,size_t n,exr_buffer *text,int *paragraph) {
  size_t i;
  if (exr_edit_xml_word(x->tree->nodes+n,"p")) {
    if ((*paragraph)++ && !put(text,"\n")) return 0;
  }
  if (exr_edit_xml_word(x->tree->nodes+n,"t")) {
    for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling)
      if (x->tree->nodes[i].text && !put(text,x->tree->nodes[i].text)) return 0;
    return 1;
  }
  if (exr_edit_xml_word(x->tree->nodes+n,"tab")) return put(text,"\t");
  if (exr_edit_xml_word(x->tree->nodes+n,"br") || exr_edit_xml_word(x->tree->nodes+n,"cr")) return put(text,"\n");
  for (i=x->tree->nodes[n].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling)
    if (!note_text(x,i,text,paragraph)) return 0;
  return 1;
}
static int text_equal(const source_xml *notes,size_t n,const char *text,size_t size) {
  exr_buffer original={0}; int paragraphs=0,same;
  if (n==NONE || !note_text(notes,n,&original,&paragraphs)) { free(original.data); return 0; }
  same=original.size==size && (!size || !memcmp(original.data,text,size)); free(original.data); return same;
}
static exr_status decode_paragraphs(const source_xml *main,const source_xml *notes,exr_edit_block *blocks,size_t count) {
  size_t i,j,k,l;
  for (i=0;i<count;i++) {
    exr_edit_block *p=blocks+i;
    for (j=0;j<p->run_count;j++) {
      exr_edit_run *r=(exr_edit_run *)p->runs+j; size_t n,ref,note; exr_buffer text={0}; int paragraphs=0;
      if (r->kind!=EXR_EDIT_OPAQUE_RUN) continue;
      n=exr_edit_xml_locate(main,r->opaque_xml,r->opaque_size,"r",NONE); ref=reference(main,n);
      if (ref==NONE) continue;
      note=note_node(notes,exr_edit_xml_wa(main->tree->nodes+ref,"id")); if (note==NONE) continue;
      if (!note_text(notes,note,&text,&paragraphs)) { free(text.data); return EXR_MEMORY; }
      r->kind=EXR_EDIT_FOOTNOTE; r->text=text.data; r->text_size=text.size;
    }
    if (p->table) for (j=0;j<p->table->row_count;j++) for (k=0;k<p->table->rows[j].cell_count;k++) {
      exr_edit_cell *cell=(exr_edit_cell *)p->table->rows[j].cells+k;
      exr_status s=decode_paragraphs(main,notes,(exr_edit_block *)cell->blocks,cell->block_count);
      if (s) return s;
      if (cell->block_count==1 && cell->blocks[0].kind==EXR_EDIT_PARAGRAPH) {
        int opaque=0;
        for (l=0;l<cell->blocks[0].run_count;l++) {
          const exr_edit_run *r=cell->blocks[0].runs+l;
          if (r->kind==EXR_EDIT_OPAQUE_RUN && memchr(r->opaque_xml,'<',r->opaque_size)) opaque=1;
        }
        if (!opaque) cell->unsupported&=~EXR_EDIT_CELL_OPAQUE;
      }
    }
  }
  return EXR_OK;
}
exr_status exr_edit_footnotes_decode(const source_xml *main,const exr_edit_part *parts,size_t count,
    const char *path,exr_edit_block *blocks,size_t block_count,exr_error *e) {
  source_xml notes={0}; char name[2048]; exr_status s=open_notes(parts,count,path,&notes,name,e);
  if (!s && notes.tree) s=decode_paragraphs(main,&notes,blocks,block_count);
  exr_edit_xml_free(&notes); return s;
}
static int source_paragraph(const source_xml *x,size_t r) {
  size_t p=x->tree->nodes[r].parent,parent;
  if (p==NONE || !exr_edit_xml_word(x->tree->nodes+p,"p")) return 0;
  parent=x->tree->nodes[p].parent;
  if (parent==x->body) return 1;
  if (parent==NONE || !exr_edit_xml_word(x->tree->nodes+parent,"tc")) return 0;
  parent=x->tree->nodes[parent].parent;
  if (parent==NONE || !exr_edit_xml_word(x->tree->nodes+parent,"tr")) return 0;
  parent=x->tree->nodes[parent].parent;
  return parent!=NONE && exr_edit_xml_word(x->tree->nodes+parent,"tbl") && x->tree->nodes[parent].parent==x->body;
}
static size_t old_note(const source_xml *main,const source_xml *notes,const exr_edit_run *run) {
  size_t r=exr_edit_xml_locate(main,run->opaque_xml,run->opaque_size,"r",NONE),ref=reference(main,r);
  return ref==NONE ? NONE : note_node(notes,exr_edit_xml_wa(main->tree->nodes+ref,"id"));
}
static int emit_text(exr_buffer *b,const char *text,size_t size) {
  size_t i,at=0;
  for (i=0;i<size;i++) if (text[i]=='\n' || text[i]=='\t') {
    if (!escape(b,text+at,i-at) || !put(b,text[i]=='\n' ? "</w:t><w:br/><w:t xml:space=\"preserve\">" :
        "</w:t><w:tab/><w:t xml:space=\"preserve\">")) return 0;
    at=i+1;
  }
  return escape(b,size ? text+at : "",size-at);
}
static int emit_note(exr_buffer *b,const source_xml *notes,size_t old,const exr_edit_footnote *note,const char *ns) {
  char number[32]; snprintf(number,sizeof(number),"%zu",note->number);
  if (text_equal(notes,old,note->text,note->text_size)) {
    attr_edit id={"id",number}; return exr_edit_xml_attrs(b,notes,old,"footnote",&id,1);
  }
  return put(b,"<w:footnote xmlns:w=\"") && put(b,ns) && put(b,"\" w:id=\"") && put(b,number) &&
    put(b,"\"><w:p><w:pPr><w:pStyle w:val=\"FootnoteText\"/></w:pPr><w:r><w:rPr><w:vertAlign w:val=\"superscript\"/></w:rPr><w:footnoteRef/></w:r><w:r><w:t xml:space=\"preserve\">") &&
    emit_text(b,note->text,note->text_size) && put(b,"</w:t></w:r></w:p></w:footnote>");
}
exr_status exr_edit_footnotes_prepare(const exr_edit_doc *doc,source_xml *main,const exr_edit_part *parts,
    size_t count,const char *path,edit_footnote_output *out,exr_error *e) {
  source_xml notes={0}; size_t i,j=0,old_count=0,n=exr_edit_footnote_count(doc),at; int same=1,unmanaged=0;
  exr_status s=open_notes(parts,count,path,&notes,out->part,e);
  main->edit_doc=doc;
  out->strict=!strcmp(exr_edit_xml_ns(main),WS);
  if (!relpath(path,out->relpart)) { exr_edit_xml_free(&notes); return EXR_LIMIT; }
  if (s) return s;
  /* Source references determine whether notes changed. Ordinary text edits keep
     the entire original footnotes part byte-identical, including rich content. */
  if (main->tree) for (i=0;i<main->tree->node_count;i++) {
    size_t ref=reference(main,i),old;
    if (ref==NONE || !source_paragraph(main,i)) continue;
    old=note_node(&notes,exr_edit_xml_wa(main->tree->nodes+ref,"id")); if (old==NONE) continue;
    old_count++;
    if (j<n) {
      exr_edit_footnote note; const exr_edit_block *p; const exr_edit_run *run;
      if (exr_edit_footnote_at(doc,j++,&note)) { s=EXR_ARGUMENT; goto done; }
      p=exr_edit_find_block(doc,note.paragraph_id); run=p->runs+note.run_index;
      if (run->opaque_size!=main->spans[i].end-main->spans[i].start ||
          memcmp(run->opaque_xml,main->bytes+main->spans[i].start,run->opaque_size) ||
          !text_equal(&notes,old,note.text,note.text_size)) same=0;
    } else same=0;
  }
  if (old_count!=n) same=0;
  if (same) goto done;
  if (main->tree) for (i=0;i<main->tree->node_count;i++) if (exr_edit_xml_word(main->tree->nodes+i,"footnoteReference")) {
    size_t r=main->tree->nodes[i].parent;
    if (r==NONE || reference(main,r)!=i || !source_paragraph(main,r)) unmanaged=1;
  }
  if (unmanaged) { s=exr_fail(e,EXR_UNSUPPORTED,"Cannot renumber compound or unmodelled footnote references"); goto done; }
  out->changed=main->footnotes_changed=1;
  if (notes.tree) {
    if (!exr_append(&out->xml,notes.bytes,notes.spans[notes.root].start) || !exr_edit_xml_start(&out->xml,&notes,notes.root,"footnotes")) { s=EXR_MEMORY; goto done; }
    at=notes.spans[notes.root].open;
    for (i=notes.tree->nodes[notes.root].first_child;i!=NONE;i=notes.tree->nodes[i].next_sibling) if (notes.tree->nodes[i].name) {
      const char *type=exr_edit_xml_wa(notes.tree->nodes+i,"type");
      int normal=exr_edit_xml_word(notes.tree->nodes+i,"footnote") && (!type || !strcmp(type,"normal"));
      if (!exr_append(&out->xml,notes.bytes+at,notes.spans[i].start-at) || (!normal && !exr_edit_xml_raw(&out->xml,&notes,i))) { s=EXR_MEMORY; goto done; }
      at=notes.spans[i].end;
    }
    if (!exr_append(&out->xml,notes.bytes+at,notes.spans[notes.root].close-at)) { s=EXR_MEMORY; goto done; }
  } else if (!put(&out->xml,"<?xml version=\"1.0\" encoding=\"UTF-8\"?><w:footnotes xmlns:w=\"") ||
      !put(&out->xml,exr_edit_xml_ns(main)) || !put(&out->xml,"\"><w:footnote w:type=\"separator\" w:id=\"-1\"><w:p><w:r><w:separator/></w:r></w:p></w:footnote><w:footnote w:type=\"continuationSeparator\" w:id=\"0\"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>")) { s=EXR_MEMORY; goto done; }
  for (i=0;i<n;i++) {
    exr_edit_footnote note; const exr_edit_block *p;
    if (exr_edit_footnote_at(doc,i,&note)) { s=EXR_ARGUMENT; goto done; }
    p=exr_edit_find_block(doc,note.paragraph_id);
    if (!emit_note(&out->xml,&notes,old_note(main,&notes,p->runs+note.run_index),&note,exr_edit_xml_ns(main))) { s=EXR_MEMORY; goto done; }
  }
  if (notes.tree) {
    if (!exr_edit_xml_end(&out->xml,&notes,notes.root,"footnotes") || !exr_append(&out->xml,notes.bytes+notes.spans[notes.root].end,notes.size-notes.spans[notes.root].end)) s=EXR_MEMORY;
  } else if (!put(&out->xml,"</w:footnotes>")) s=EXR_MEMORY;
done:
  exr_edit_xml_free(&notes); return s;
}
static int reference_properties(exr_buffer *b,const source_xml *x,size_t pr) {
  size_t i,at=pr==NONE ? 0 : x->spans[pr].open;
  if (!exr_edit_xml_start(b,x,pr,"rPr")) return 0;
  if (pr!=NONE) for (i=x->tree->nodes[pr].first_child;i!=NONE;i=x->tree->nodes[i].next_sibling) if (x->tree->nodes[i].name) {
    if (!exr_append(b,x->bytes+at,x->spans[i].start-at) ||
        (!exr_edit_xml_word(x->tree->nodes+i,"vertAlign") && !exr_edit_xml_raw(b,x,i))) return 0;
    at=x->spans[i].end;
  }
  return (pr==NONE || exr_append(b,x->bytes+at,x->spans[pr].close-at)) &&
    exr_edit_xml_attrs(b,x,NONE,"vertAlign",&(attr_edit){"val","superscript"},1) && exr_edit_xml_end(b,x,pr,"rPr");
}
int exr_edit_footnote_reference_write(exr_buffer *b,const source_xml *x,const exr_edit_run *r,size_t parent) {
  size_t i,n=exr_edit_xml_locate(x,r->opaque_xml,r->opaque_size,"r",parent),ref=reference(x,n); char number[32];
  if (!x->footnotes_changed && ref!=NONE) return exr_edit_xml_raw(b,x,n);
  /* ponytail: document-order lookup per reference; index if note-heavy files
     make export profiling justify a second numbering cache. */
  for (i=0;i<exr_edit_footnote_count(x->edit_doc);i++) {
    exr_edit_footnote note;
    if (!exr_edit_footnote_at(x->edit_doc,i,&note) && note.id==r->id) {
      attr_edit id={"id",number}; snprintf(number,sizeof(number),"%zu",note.number);
      if (ref!=NONE) {
        size_t child,pr=exr_edit_xml_child(x,n,"rPr"),at=x->spans[n].open;
        if (!exr_edit_xml_start(b,x,n,"r") || (pr==NONE && !reference_properties(b,x,NONE))) return 0;
        for (child=x->tree->nodes[n].first_child;child!=NONE;child=x->tree->nodes[child].next_sibling) if (x->tree->nodes[child].name) {
          if (!exr_append(b,x->bytes+at,x->spans[child].start-at) ||
              !(child==pr ? reference_properties(b,x,pr) : exr_edit_xml_attrs(b,x,ref,"footnoteReference",&id,1))) return 0;
          at=x->spans[child].end;
        }
        return exr_append(b,x->bytes+at,x->spans[n].close-at) && exr_edit_xml_end(b,x,n,"r");
      }
      return put(b,"<w:r xmlns:w=\"") && put(b,exr_edit_xml_ns(x)) && put(b,"\"><w:rPr><w:vertAlign w:val=\"superscript\"/></w:rPr><w:footnoteReference w:id=\"") && put(b,number) && put(b,"\"/></w:r>");
    }
  }
  return 0;
}
/* Patch an OPC container root while retaining every unrelated entry and all
   original namespace declarations. New entries declare their own namespace. */
static exr_status package_xml(exr_buffer *out,const exr_edit_part *part,const char *root,const char *ns,
    const char *entry,int types,const char *note_part,const char *rid,const char *target,int strict) {
  source_xml x={0}; size_t i,at=0; exr_status s=EXR_MEMORY;
  if (part) { s=exr_edit_xml_parse(&x,part->data,part->size,root,NULL); if (s) return s; }
  s=EXR_MEMORY;
  if (part) {
    if (!exr_append(out,x.bytes,x.spans[x.root].start) || !exr_edit_xml_start(out,&x,x.root,root)) goto done;
    at=x.spans[x.root].open;
    for (i=x.tree->nodes[x.root].first_child;i!=NONE;i=x.tree->nodes[i].next_sibling) if (x.tree->nodes[i].name) {
      const char *name=exr_node_attribute(x.tree->nodes+i,"PartName");
      int drop=types ? name && *name=='/' && !strcmp(name+1,note_part) : note_type(x.tree->nodes+i);
      if (!exr_append(out,x.bytes+at,x.spans[i].start-at) || (!drop && !exr_edit_xml_raw(out,&x,i))) goto done;
      at=x.spans[i].end;
    }
    if (!exr_append(out,x.bytes+at,x.spans[x.root].close-at)) goto done;
  } else if (!put(out,"<") || !put(out,root) || !put(out," xmlns=\"") || !put(out,ns) || !put(out,"\">")) goto done;
  if (!put(out,"<") || !put(out,entry) || !put(out," xmlns=\"") || !put(out,ns)) goto done;
  if (types) {
    if (!put(out,"\" PartName=\"/") || !escape(out,note_part,strlen(note_part)) || !put(out,"\" ContentType=\"" NOTE_TYPE "\"/>")) goto done;
  } else if (!put(out,"\" Id=\"") || !put(out,rid) || !put(out,"\" Type=\"") || !put(out,strict ? RS : R) || !put(out,"/footnotes\" Target=\"") || !escape(out,target,strlen(target)) || !put(out,"\"/>")) goto done;
  if (part) {
    if (!exr_edit_xml_end(out,&x,x.root,root) || !exr_append(out,x.bytes+x.spans[x.root].end,x.size-x.spans[x.root].end)) goto done;
  } else if (!put(out,"</") || !put(out,root) || !put(out,">")) goto done;
  s=EXR_OK;
done:
  exr_edit_xml_free(&x); return s;
}
exr_status exr_edit_footnotes_package(mz_zip_archive *zip,const exr_edit_part *parts,size_t count,const char *main,
    const exr_buffer *xml,const edit_image_output *images,size_t image_count,const edit_footnote_output *notes,exr_error *e) {
  exr_edit_part *updated=NULL; source_xml rels={0}; exr_buffer rb={0},tb={0};
  const exr_edit_part *rp=exr_edit_part_named(parts,count,notes->relpart),*tp=exr_edit_part_named(parts,count,"[Content_Types].xml");
  size_t i,n=count; char rid[64],target[2050]; unsigned suffix=0; exr_status s=EXR_MEMORY; int collision;
  if (!notes->changed) return exr_edit_images_package(zip,parts,count,main,xml,images,image_count,e);
  if (rp) { s=exr_edit_xml_parse(&rels,rp->data,rp->size,"Relationships",e); if (s) goto done; }
  do {
    snprintf(rid,sizeof(rid),"exrFootnotes%u",suffix++); collision=0;
    if (rels.tree) for (i=0;i<rels.tree->node_count;i++) {
      const char *id=exr_node_attribute(rels.tree->nodes+i,"Id"); if (id && !strcmp(id,rid)) collision=1;
    }
  } while (collision);
  { const char *slash=strrchr(main,'/'); size_t dir=slash ? (size_t)(slash-main)+1 : 0;
    if (!strncmp(notes->part,main,dir)) snprintf(target,sizeof(target),"%s",notes->part+dir);
    else snprintf(target,sizeof(target),"/%s",notes->part);
  }
  s=package_xml(&rb,rp,"Relationships",REL,"Relationship",0,notes->part,rid,target,notes->strict); if (s) goto done;
  s=package_xml(&tb,tp,"Types",CT,"Override",1,notes->part,NULL,NULL,0); if (s) goto done;
  s=EXR_MEMORY; updated=calloc(count+3,sizeof(*updated)); if (!updated) goto done;
  memcpy(updated,parts,count*sizeof(*updated));
#define REPLACE_PART(name_,data_,size_) do { \
  for (i=0;i<n;i++) if (!strcmp(updated[i].name,(name_))) break; \
  if (i==n) n++; \
  updated[i].name=(name_); updated[i].data=(data_); updated[i].size=(size_); \
} while (0)
  REPLACE_PART(notes->part,notes->xml.data,notes->xml.size);
  REPLACE_PART(notes->relpart,rb.data,rb.size);
  REPLACE_PART("[Content_Types].xml",tb.data,tb.size);
#undef REPLACE_PART
  s=exr_edit_images_package(zip,updated,n,main,xml,images,image_count,e);
done:
  free(updated); free(rb.data); free(tb.data); exr_edit_xml_free(&rels); return s;
}
