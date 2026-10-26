/* SPDX-License-Identifier: MIT */
#include "formats_internal.h"
#include "graphics_internal.h"
#include <ctype.h>
/* RTF font numbers are 16-bit; Word emits theme fonts such as lomajor31500. */
#define RTF_FONTS 32768
enum { BOLD, ITALIC, SIZE, COLOR, BACKGROUND, UNDERLINE, STRIKE, ALIGN, LEFT, RIGHT,
       INDENT, BEFORE, AFTER, LEADING, MULTIPLE, DIRECTION, RTF_PROPERTIES };
enum { LIST_TABLE=8,LIST_DEF,LIST_LEVEL,LEVEL_TEXT,LEVEL_NUMBERS,OVERRIDE_TABLE,LIST_OVERRIDE,OVERRIDE_LEVEL };
typedef struct { int skip,uc,destination,picture,inherited_skip,star,font,field,note,list_id,list_level,list_text,definition,number_level,override_index,override_level,font_set; unsigned specified; int properties[RTF_PROPERTIES]; } rtf_state;
typedef struct {
  int format,start,has_start,follow,legal,norestart,nfcn,font,font_set,expected,text_seen,numbers_seen; size_t count;
  unsigned specified; int properties[RTF_PROPERTIES]; uint32_t pattern[255]; uint64_t references[4];
} rtf_number_level;
typedef struct { int id,has_id; size_t count; rtf_number_level levels[9]; } rtf_number_definition;
typedef struct {
  int id,list_id,has_list_id,definition,expected; size_t count;
  unsigned start_flags,start_set,format_flags,format_set,started; int starts[9],counter[9]; rtf_number_level levels[9];
} rtf_number_override;
typedef struct { size_t node,paragraph; } rtf_note;
typedef struct { size_t container,depth; struct { size_t list,item; int id; } levels[9]; } rtf_lists;

typedef struct { exr_buffer instruction; char *href; int ready; } rtf_field;
typedef struct { exr_buffer bytes; int type,nibble,width,height,goal_width,goal_height,scale_x,scale_y; } rtf_picture;
typedef struct {
  exr_document *doc;
  exr_buffer run;
  rtf_state style;
  size_t paragraph,body,table,row,cell,cell_count,definition_count;
  size_t cells[256],owner[256],owner_span[256],owner_rows[256];
  long boundaries[256],owner_left[256],owner_right[256],row_left;
  unsigned char horizontal[256],vertical[256],pending_horizontal,pending_vertical;
  uint32_t colors[4096];
  size_t color_count;
  unsigned red,green,blue,components;
  char **fonts;
  exr_buffer font_name,bookmark,title;
  size_t metadata_bytes,title_text;
  int default_font;
  rtf_field *fields;
  size_t field_count,field_capacity;
  rtf_picture *pictures;
  size_t picture_count,picture_capacity;
  rtf_lists lists,note_lists;
  rtf_number_definition *number_definitions; size_t number_count,number_capacity;
  rtf_number_override *number_overrides; size_t override_count,override_capacity; unsigned override_map[2001];
  rtf_note *notes; size_t note_count,note_capacity,pending_note_ref; int active_note;
  int last_picture;
  exr_status status;
  exr_error *error;
} rtf_context;
static int put(exr_buffer *b,const char *s) { return exr_append(b,s,strlen(s)); }
static size_t make(rtf_context *c,size_t parent,exr_node_kind kind,const char *tag,const char *text) {
  size_t at=exr_model_html(c->doc,parent,0,kind,tag,text);
  if(at==SIZE_MAX) c->status=EXR_LIMIT;
  return at;
}
static int set(rtf_context *c,size_t node,const char *key,const char *value) {
  if(!exr_model_attribute(c->doc,node,key,value)) { c->status=EXR_LIMIT; return 0; } return 1;
}
static int css_number(exr_buffer *b,const char *name,float value,int px) {
  char text[100]; snprintf(text,sizeof(text),"%s:%.4f%s;",name,value,px ? "px" : ""); return put(b,text);
}
static int run_flush(rtf_context *c);
static int style_control(rtf_context *c,rtf_state *s,const char *word,long value,int has);
static int number_grow(rtf_context *c,void **data,size_t *capacity,size_t count,size_t unit) {
  size_t next,delta; void *copy;
  if(count<*capacity) return 1;
  if(count>=2000) { c->status=EXR_LIMIT; return 0; }
  next=*capacity ? *capacity*2 : 1; if(next>2000) next=2000; delta=(next-*capacity)*unit;
  if(delta>EXR_MAX_TEXT-c->metadata_bytes) { c->status=EXR_LIMIT; return 0; }
  copy=realloc(*data,next*unit); if(!copy) { c->status=EXR_MEMORY; return 0; }
  *data=copy; *capacity=next; c->metadata_bytes+=delta; return 1;
}
static rtf_number_level *metadata_level(rtf_context *c,const rtf_state *s) {
  if(s->number_level<0 || s->number_level>8) return NULL;
  if(s->override_index>=0 && (size_t)s->override_index<c->override_count) return &c->number_overrides[s->override_index].levels[s->number_level];
  if(s->definition>=0 && (size_t)s->definition<c->number_count) return &c->number_definitions[s->definition].levels[s->number_level];
  return NULL;
}
static rtf_number_level *number_level(rtf_context *c,const rtf_state *s,rtf_number_override **instance) {
  rtf_number_override *o; size_t i; unsigned at;
  if(instance) *instance=NULL;
  if(s->list_id<=0 || s->list_id>2000 || s->list_level<0 || s->list_level>8 || !(at=c->override_map[s->list_id])) return NULL;
  o=&c->number_overrides[at-1]; if(instance) *instance=o;
  if(o->definition==-1) {
    o->definition=-2;
    for(i=0;i<c->number_count;i++) if(c->number_definitions[i].id==o->list_id) { o->definition=(int)i; break; }
  }
  if(o->definition<0 || (size_t)s->list_level>=c->number_definitions[o->definition].count) return NULL;
  return o->format_flags&(1u<<s->list_level) ? &o->levels[s->list_level] : &c->number_definitions[o->definition].levels[s->list_level];
}
static int number_literal(rtf_context *c,const rtf_state *s,uint32_t cp,int byte) {
  rtf_number_level *level=metadata_level(c,s);
  if(s->destination!=LEVEL_TEXT && s->destination!=LEVEL_NUMBERS) return 1;
  if(!level) goto invalid;
  if(s->destination==LEVEL_TEXT) {
    if(level->expected<0) { if(cp>255) goto invalid; level->expected=(int)cp; }
    else if(level->count<(size_t)level->expected) {
      if(byte && cp>=128) cp=exr_windows1252((unsigned char)cp);
      level->pattern[level->count++]=cp;
    } else if(cp!=';' && cp!=' ' && cp!='\t' && cp!='\r' && cp!='\n') goto invalid;
  } else if(!byte && (cp==';' || cp==' ' || cp=='\t' || cp=='\r' || cp=='\n')) return 1;
  else {
    size_t at;
    if(!cp || cp>255) goto invalid;
    at=cp-1; if(level->references[at/64]&(UINT64_C(1)<<(at%64))) goto invalid;
    level->references[at/64]|=UINT64_C(1)<<(at%64);
  }
  return 1;
invalid:
  c->status=EXR_FORMAT; return 0;
}
static int number_control(rtf_context *c,rtf_state *s,const char *word,long value,int has,int *handled) {
  rtf_number_level *level; rtf_number_override *o=s->override_index>=0 && (size_t)s->override_index<c->override_count ? &c->number_overrides[s->override_index] : NULL;
  *handled=1;
  if(s->destination<LIST_TABLE) { *handled=0; return 1; }
  if(!strcmp(word,"u") || !strcmp(word,"uc")) { *handled=0; return 1; }
  if(s->destination==LIST_TABLE && !strcmp(word,"list")) {
    rtf_number_definition *d;
    if(!number_grow(c,(void **)&c->number_definitions,&c->number_capacity,c->number_count,sizeof(*d))) return 0;
    s->definition=(int)c->number_count++; s->override_index=-1; s->number_level=-1; s->destination=LIST_DEF;
    d=&c->number_definitions[s->definition]; memset(d,0,sizeof(*d)); return 1;
  }
  if(s->destination==OVERRIDE_TABLE && !strcmp(word,"listoverride")) {
    if(!number_grow(c,(void **)&c->number_overrides,&c->override_capacity,c->override_count,sizeof(*o))) return 0;
    s->override_index=(int)c->override_count++; s->definition=s->number_level=s->override_level=-1; s->destination=LIST_OVERRIDE;
    o=&c->number_overrides[s->override_index]; memset(o,0,sizeof(*o)); o->definition=-1; return 1;
  }
  if(s->destination==LIST_OVERRIDE && !strcmp(word,"lfolevel")) {
    if(!o || o->count>=9) goto invalid;
    s->override_level=(int)o->count++; s->number_level=-1; s->destination=OVERRIDE_LEVEL; return 1;
  }
  if((s->destination==LIST_DEF || s->destination==OVERRIDE_LEVEL) && !strcmp(word,"listlevel")) {
    if(s->destination==LIST_DEF) {
      rtf_number_definition *d=&c->number_definitions[s->definition]; if(d->count>=9) goto invalid; s->number_level=(int)d->count++;
    } else s->number_level=s->override_level;
    level=metadata_level(c,s); if(!level) goto invalid; memset(level,0,sizeof(*level)); level->start=1; level->font=level->expected=-1;
    s->font=-1; s->font_set=0; s->specified=0; memset(s->properties,0,sizeof(s->properties)); s->destination=LIST_LEVEL; return 1;
  }
  if(!strcmp(word,"listid") && (s->destination==LIST_DEF || s->destination==LIST_OVERRIDE)) {
    /* Read-only compatibility: real Word streams use reserved IDs -1..-5.
       Keep their signed int32 identity intact, including 0 and INT_MIN;
       only the independent, bounded ls value indexes override_map. */
    if(!has) goto invalid;
    if(o) { o->list_id=(int)value; o->has_list_id=1; }
    else { c->number_definitions[s->definition].id=(int)value; c->number_definitions[s->definition].has_id=1; }
    return 1;
  }
  if(s->destination==LIST_OVERRIDE && !strcmp(word,"ls")) { if(!o || !has || value<1 || value>2000) goto invalid; o->id=(int)value; return 1; }
  if(s->destination==LIST_OVERRIDE && !strcmp(word,"listoverridecount")) { if(!o || !has || value<0 || value>9) goto invalid; o->expected=(int)value; return 1; }
  if(s->destination==OVERRIDE_LEVEL) {
    unsigned bit=1u<<s->override_level;
    if(!strcmp(word,"listoverridestartat") || !strcmp(word,"listoverridestart")) { o->start_flags|=bit; return 1; }
    if(!strcmp(word,"listoverrideformat")) { if(!has || value) o->format_flags|=bit; return 1; }
    if(!strcmp(word,"levelstartat")) { if(!has) goto invalid; o->starts[s->override_level]=(int)value; o->start_set|=bit; return 1; }
  }
  if(s->destination!=LIST_LEVEL) return 1;
  level=metadata_level(c,s); if(!level) goto invalid;
  if(!strcmp(word,"leveltext")) { if(level->text_seen) goto invalid; level->text_seen=1; s->destination=LEVEL_TEXT; return 1; }
  if(!strcmp(word,"levelnumbers")) { if(level->numbers_seen) goto invalid; level->numbers_seen=1; s->destination=LEVEL_NUMBERS; return 1; }
  if(!strcmp(word,"levelnfc") || !strcmp(word,"levelnfcn")) {
    if(!has || value<0 || value>255) goto invalid;
    if(!strcmp(word,"levelnfcn")) { level->format=(int)value; level->nfcn=1; } else if(!level->nfcn) level->format=(int)value; return 1;
  }
  if(!strcmp(word,"levelstartat")) { if(!has) goto invalid; level->start=(int)value; level->has_start=1; return 1; }
  if(!strcmp(word,"levelfollow")) { if(!has || value<0 || value>2) goto invalid; level->follow=(int)value; return 1; }
  if(!strcmp(word,"levellegal") || !strcmp(word,"levelnorestart")) { int flag=!has || value!=0; if(!strcmp(word,"levellegal")) level->legal=flag; else level->norestart=flag; return 1; }
  if(!strcmp(word,"f")) { if(!has || value<0 || value>=RTF_FONTS) goto invalid; s->font=(int)value; s->font_set=1; return 1; }
  return style_control(c,s,word,value,has);
invalid:
  c->status=EXR_FORMAT; return 0;
}
static int number_finish(rtf_context *c,const rtf_state *s,const rtf_state *parent) {
  size_t i; rtf_number_level *level=metadata_level(c,s);
  if(s->destination==LEVEL_TEXT && parent->destination!=LEVEL_TEXT && (!level || level->expected<0 || level->count!=(size_t)level->expected)) goto invalid;
  if(s->destination==LIST_LEVEL && parent->destination!=LIST_LEVEL) {
    if(!level) goto invalid;
    for(i=0;i<255;i++) {
      int reference=(level->references[i/64]&(UINT64_C(1)<<(i%64)))!=0;
      if(reference && (i>=level->count || level->pattern[i]>8)) goto invalid;
      if(i<level->count && level->pattern[i]<=8 && !reference) goto invalid;
    }
    level->font=s->font; level->font_set=s->font_set; level->specified=s->specified; memcpy(level->properties,s->properties,sizeof(level->properties));
    if(s->override_index>=0) {
      rtf_number_override *o=&c->number_overrides[s->override_index]; unsigned bit=1u<<s->number_level; o->format_set|=bit;
      if(level->has_start) { o->start_set|=bit; o->starts[s->number_level]=level->start; }
    }
  }
  if(s->destination==LIST_DEF && parent->destination!=LIST_DEF) {
    rtf_number_definition *d=&c->number_definitions[s->definition]; if(!d->has_id || !d->count) goto invalid;
    for(i=0;i<c->number_count;i++) if(i!=(size_t)s->definition && c->number_definitions[i].has_id && c->number_definitions[i].id==d->id) goto invalid;
  }
  if(s->destination==LIST_OVERRIDE && parent->destination!=LIST_OVERRIDE) {
    rtf_number_override *o=&c->number_overrides[s->override_index];
    if(!o->id || !o->has_list_id || c->override_map[o->id] || (o->expected && (size_t)o->expected!=o->count) || (o->start_flags&~o->start_set) || (o->format_flags&~o->format_set)) goto invalid;
    c->override_map[o->id]=(unsigned)s->override_index+1;
  }
  return 1;
invalid:
  c->status=EXR_FORMAT; return 0;
}
static const char *number_format(int format) {
  switch(format) { case 0:return "decimal"; case 1:return "upperRoman"; case 2:return "lowerRoman"; case 3:return "upperLetter"; case 4:return "lowerLetter"; case 22:return "decimalZero"; default:return NULL; }
}
static int number_marker(rtf_context *c,const rtf_state *s) {
  rtf_number_override *o=NULL; rtf_number_level *level=number_level(c,s,&o); rtf_state marker=*s; exr_buffer label={0},saved; rtf_state saved_style; size_t i; unsigned bit; int ok=0;
  if(!o) return 1;
  if(!level) { if(s->list_text) return 1; c->status=EXR_FORMAT; return 0; }
  bit=1u<<s->list_level;
  if(o->started&bit) { if(o->counter[s->list_level]==INT_MAX) { c->status=EXR_LIMIT; return 0; } o->counter[s->list_level]++; }
  else { o->counter[s->list_level]=o->start_flags&bit ? o->starts[s->list_level] : c->number_definitions[o->definition].levels[s->list_level].start; o->started|=bit; }
  for(i=(size_t)s->list_level+1;i<9;i++) { rtf_state other=*s; rtf_number_level *next; other.list_level=(int)i; next=number_level(c,&other,NULL); if(!next || !next->norestart) o->started&=~(1u<<i); }
  if(s->list_text) return 1;
  if(level->format==255) return 1;
  if(level->expected>=0) {
    for(i=0;i<level->count;i++) {
      uint32_t cp=level->pattern[i];
      if(cp<=8) {
        rtf_state other=*s; rtf_number_level *reference; const char *format; int value; unsigned flag=1u<<cp;
        other.list_level=(int)cp; reference=number_level(c,&other,NULL); if(!reference) { c->status=EXR_FORMAT; goto done; }
        format=number_format(level->legal && cp<(unsigned)s->list_level ? 0 : reference->format); if(!format) { c->status=EXR_FORMAT; goto done; }
        value=o->started&flag ? o->counter[cp] : o->start_flags&flag ? o->starts[cp] : c->number_definitions[o->definition].levels[cp].start;
        c->status=exr_number_text(&label,value,format,c->error); if(c->status!=EXR_OK) goto done;
      } else if(!exr_codepoint(&label,cp)) { c->status=EXR_LIMIT; goto done; }
    }
  } else if(level->format==23) { if(!exr_codepoint(&label,0x2022)) { c->status=EXR_LIMIT; goto done; } }
  else {
    const char *format=number_format(level->format); if(!format) { c->status=EXR_FORMAT; goto done; }
    c->status=exr_number_text(&label,o->counter[s->list_level],format,c->error); if(c->status!=EXR_OK) goto done;
    if(!put(&label,".")) { c->status=EXR_LIMIT; goto done; }
  }
  if(label.size && level->follow!=2 && !put(&label,level->follow ? " " : "\t")) { c->status=EXR_LIMIT; goto done; }
  if(label.size>4096) { c->status=EXR_LIMIT; goto done; }
  if(!label.size) { ok=1; goto done; }
  for(i=0;i<ALIGN;i++) if(level->specified&(1u<<i)) marker.properties[i]=level->properties[i];
  if(level->font_set) marker.font=level->font;
  marker.list_text=1; saved=c->run; saved_style=c->style; c->run=label; c->style=marker;
  ok=run_flush(c); label=c->run; c->run=saved; c->style=saved_style;
done:
  free(label.data); return ok;
}
static int paragraph_style(rtf_context *c,const rtf_state *s) {
  exr_buffer css={0}; int merged[RTF_PROPERTIES]; const int *p=s->properties; int ok; rtf_number_level *level=number_level(c,s,NULL);
  if(level) {
    memcpy(merged,p,sizeof(merged));
    if(!(s->specified&(1u<<LEFT)) && (level->specified&(1u<<LEFT))) merged[LEFT]=level->properties[LEFT];
    if(!(s->specified&(1u<<INDENT)) && (level->specified&(1u<<INDENT))) merged[INDENT]=level->properties[INDENT];
    p=merged;
  }
  if(c->paragraph==SIZE_MAX) return 1;
  ok=put(&css,p[ALIGN]==1 ? "text-align:right;" : p[ALIGN]==2 ? "text-align:center;" : p[ALIGN]==3 ? "text-align:justify;" : "text-align:left;") &&
      css_number(&css,"margin-left",p[LEFT]/15.0f,1) && css_number(&css,"margin-right",p[RIGHT]/15.0f,1) &&
      css_number(&css,"text-indent",p[INDENT]/15.0f,1) && css_number(&css,"margin-top",p[BEFORE]/15.0f,1) &&
      css_number(&css,"margin-bottom",p[AFTER]/15.0f,1);
  if(ok && p[LEADING]) ok=css_number(&css,"line-height",fabsf((float)p[LEADING])/(p[MULTIPLE] ? 240.0f : 15.0f),!p[MULTIPLE]);
  if(ok && p[DIRECTION]) ok=put(&css,p[DIRECTION]==1 ? "direction:ltr;" : "direction:rtl;");
  ok=ok && set(c,c->paragraph,"style",css.data); free(css.data); return ok;
}
static int list_parent(rtf_context *c,const rtf_state *s,size_t container,size_t *parent) {
  rtf_lists *lists=&c->lists; size_t level=(size_t)s->list_level,k; int bullet=0;
  *parent=container;
  if(lists->container!=container) { lists->container=container; lists->depth=0; }
  if(!s->list_id) { lists->depth=0; return 1; }
  if(level>=9) { c->status=EXR_FORMAT; return 0; }
  if(s->list_text && c->run.data) {
    size_t at=strspn(c->run.data," \t\r\n"); uint32_t cp;
    if(at<c->run.size && exr_next(c->run.data,c->run.size,&at,&cp)) bullet=cp==0x2022 || cp==0xb7 || cp==0x25cf || cp==0x25cb || cp==0x25aa || cp=='*' || cp=='-';
  }
  { rtf_number_level *definition=number_level(c,s,NULL); if(definition) bullet=definition->format==23; }
  if(lists->depth>level && (lists->levels[level].id!=s->list_id || ((s->list_text || number_level(c,s,NULL)) && strcmp(exr_html_tag(c->doc,&c->doc->nodes[lists->levels[level].list]),bullet ? "ul" : "ol")))) lists->depth=level;
  for(k=lists->depth;k<=level;k++) {
    size_t owner=k ? lists->levels[k-1].item : container,list; char value[48];
    rtf_state at_level=*s; rtf_number_override *instance=NULL; rtf_number_level *definition; int start,level_bullet;
    at_level.list_level=(int)k; definition=number_level(c,&at_level,&instance);
    level_bullet=definition ? definition->format==23 : bullet;
    list=make(c,owner,EXR_NODE_LIST,level_bullet ? "ul" : "ol",NULL); if(list==SIZE_MAX) return 0;
    if(!set(c,list,"style","list-style-type:none;padding:0;margin:0;")) return 0;
    { if(definition && instance) {
        snprintf(value,sizeof(value),"%d",definition->format); if(!set(c,list,"data-rtf-number-format",value)) return 0;
        start=instance->started&(1u<<k) ? instance->counter[k]+(instance->counter[k]<INT_MAX) : instance->start_flags&(1u<<k) ? instance->starts[k] : c->number_definitions[instance->definition].levels[k].start;
        if(!level_bullet) { snprintf(value,sizeof(value),"%d",start); if(!set(c,list,"start",value)) return 0; }
        if(definition->format>=1 && definition->format<=4 && !set(c,list,"type",definition->format==1 ? "I" : definition->format==2 ? "i" : definition->format==3 ? "A" : "a")) return 0;
      }
    }
    snprintf(value,sizeof(value),"%d",s->list_id); if(!set(c,list,"data-rtf-list-id",value)) return 0;
    snprintf(value,sizeof(value),"%zu",k); if(!set(c,list,"data-rtf-list-level",value)) return 0;
    lists->levels[k].list=list; lists->levels[k].id=s->list_id; lists->levels[k].item=SIZE_MAX;
    if(k<level) { lists->levels[k].item=make(c,list,EXR_NODE_LIST_ITEM,"li",NULL); if(lists->levels[k].item==SIZE_MAX || !set(c,lists->levels[k].item,"role","presentation")) return 0; }
  }
  lists->levels[level].item=make(c,lists->levels[level].list,EXR_NODE_LIST_ITEM,"li",NULL);
  if(lists->levels[level].item==SIZE_MAX) return 0;
  lists->depth=level+1; *parent=lists->levels[level].item; return 1;
}
static int paragraph(rtf_context *c,const rtf_state *s) {
  if(c->paragraph==SIZE_MAX) {
    size_t parent=c->body;
    if(c->active_note>=0) parent=c->notes[c->active_note].node;
    else if(c->row!=SIZE_MAX) {
      if(c->cell==SIZE_MAX) {
        if(c->cell_count>=256) { c->status=EXR_LIMIT; return 0; }
        c->cell=make(c,c->row,EXR_NODE_CELL,"td",NULL); if(c->cell==SIZE_MAX) return 0;
        c->cells[c->cell_count]=c->cell;
      }
      parent=c->cell;
    } else c->table=SIZE_MAX;
    if(!list_parent(c,s,parent,&parent)) return 0;
    c->paragraph=make(c,parent,EXR_NODE_PARAGRAPH,"p",NULL); if(c->paragraph==SIZE_MAX || !number_marker(c,s)) return 0;
  }
  return paragraph_style(c,s);
}
static int css_color(rtf_context *c,exr_buffer *b,const char *property,int index) {
  uint32_t color; char text[100];
  if(!index) return 1;
  if(index<0 || (size_t)index>=c->color_count) { c->status=EXR_FORMAT; return 0; }
  color=c->colors[index]; if(!color) return 1;
  snprintf(text,sizeof(text),"%s:#%06lx;",property,(unsigned long)(color>>8)); return put(b,text);
}
static int font_css(rtf_context *c,exr_buffer *css,const rtf_state *s) {
  int font=s->font<0 ? c->default_font : s->font; const char *family;
  if(!c->fonts || font<0 || font>=RTF_FONTS || !(family=c->fonts[font])) return 1;
  if(!put(css,"font-family:\"")) return 0;
  while(*family) {
    if((*family=='"' || *family=='\\') && !put(css,"\\")) return 0;
    if(!exr_append(css,family++,1)) return 0;
  }
  return put(css,"\";");
}
static int run_flush(rtf_context *c) {
  const int *p=c->style.properties; exr_buffer css={0}; size_t parent,span; int ok=0;
  if(!c->run.size) return 1;
  if(!paragraph(c,&c->style)) goto done;
  parent=c->paragraph;
  if(c->style.field>=0 && c->fields[c->style.field].href) {
    parent=make(c,parent,EXR_NODE_LINK,"a",NULL);
    if(parent==SIZE_MAX || !set(c,parent,"href",c->fields[c->style.field].href)) goto done;
  }
  if(p[BOLD]) { parent=make(c,parent,EXR_NODE_ELEMENT,"strong",NULL); if(parent==SIZE_MAX) goto done; }
  if(p[ITALIC]) { parent=make(c,parent,EXR_NODE_ELEMENT,"em",NULL); if(parent==SIZE_MAX) goto done; }
  if(p[UNDERLINE]) { parent=make(c,parent,EXR_NODE_ELEMENT,"u",NULL); if(parent==SIZE_MAX) goto done; }
  if(p[STRIKE]) { parent=make(c,parent,EXR_NODE_ELEMENT,"s",NULL); if(parent==SIZE_MAX) goto done; }
  if(!font_css(c,&css,&c->style)) goto done;
  if(p[SIZE] && !css_number(&css,"font-size",p[SIZE]*2.0f/3,1)) goto done;
  if(!css_color(c,&css,"color",p[COLOR]) || !css_color(c,&css,"background-color",p[BACKGROUND])) goto done;
  span=make(c,parent,EXR_NODE_ELEMENT,"span",NULL);
  if(span!=SIZE_MAX && c->style.list_text && (!set(c,span,"role","presentation") || !set(c,span,"aria-hidden","true"))) goto done;
  if(span==SIZE_MAX || (css.size && !set(c,span,"style",css.data)) || make(c,span,EXR_NODE_TEXT,NULL,c->run.data)==SIZE_MAX) goto done;
  c->run.size=0; if(c->run.data) c->run.data[0]=0; ok=1;
done:
  free(css.data); if(!ok && c->status==EXR_OK) c->status=EXR_LIMIT; return ok;
}
static int cell_content(const exr_document *d,size_t node) {
  size_t child;
  for(child=d->nodes[node].first_child;child!=SIZE_MAX;child=d->nodes[child].next_sibling) {
    const exr_node *n=&d->nodes[child];
    if(n->kind==EXR_NODE_IMAGE || n->kind==EXR_NODE_BREAK) return 1;
    if(n->kind==EXR_NODE_TEXT && n->text && n->text[strspn(n->text," \t\r\n")]) return 1;
    if(cell_content(d,child)) return 1;
  }
  return 0;
}
static void append_existing(rtf_context *c,size_t parent,size_t node) {
  exr_document *d=c->doc; size_t previous=d->last_children[parent];
  d->nodes[node].parent=parent; d->nodes[node].next_sibling=SIZE_MAX;
  if(previous==SIZE_MAX) d->nodes[parent].first_child=node; else d->nodes[previous].next_sibling=node;
  d->last_children[parent]=node;
}
/* Rebuild row links once; continued physical cells become ordinary content
   containers inside the merged owner, preserving all nonempty content. */
static int cell_append(rtf_context *c,size_t parent,size_t cell,int continuation) {
  exr_document *d=c->doc; exr_node *n=&d->nodes[cell];
  if(continuation) {
    const char name[]="http://www.w3.org/1999/xhtml|div"; char *copy=exr_model_copy(d,name,sizeof(name)-1);
    if(!copy) { c->status=EXR_LIMIT; return 0; }
    d->model_bytes-=strlen(n->name)+1; free((void *)n->name); n->name=copy; n->kind=EXR_NODE_ELEMENT;
    if(!cell_content(d,cell) && !set(c,cell,"style","display:none;")) return 0;
  }
  append_existing(c,parent,cell); return 1;
}
static int row_merge(rtf_context *c) {
  size_t i=0,k;
  c->doc->nodes[c->row].first_child=SIZE_MAX; c->doc->last_children[c->row]=SIZE_MAX;
  while(i<c->cell_count) {
    size_t end=i+1,td,rows=1; unsigned v=0,h=c->definition_count ? c->horizontal[i] : 0; long left=c->definition_count ? (i ? c->boundaries[i-1] : c->row_left) : 0,right=0; char number[48];
    if(h==2) goto invalid;
    if(h==1) while(end<c->cell_count && c->horizontal[end]==2) end++;
    if(c->definition_count) {
      right=c->boundaries[end-1];
      for(k=i;k<end;k++) if(c->vertical[k]) { if(v && v!=c->vertical[k]) goto invalid; v=c->vertical[k]; }
    }
    if(v==2) {
      td=c->owner[i];
      if(td==SIZE_MAX || c->owner_span[i]!=end-i || c->owner_left[i]!=left || c->owner_right[i]!=right) goto invalid;
      rows=c->owner_rows[i]+1;
      for(k=i;k<end;k++) if(c->owner[k]!=td || c->owner_span[k]!=end-i || c->owner_rows[k]+1!=rows) goto invalid;
      snprintf(number,sizeof(number),"%zu",rows); if(!set(c,td,"rowspan",number)) return 0;
      for(k=i;k<end;k++) if(!cell_append(c,td,c->cells[k],1)) return 0;
    } else {
      td=c->cells[i]; if(!cell_append(c,c->row,td,0)) return 0;
      if(end-i>1) { snprintf(number,sizeof(number),"%zu",end-i); if(!set(c,td,"colspan",number)) return 0; }
      for(k=i+1;k<end;k++) if(!cell_append(c,td,c->cells[k],1)) return 0;
    }
    for(k=i;k<end;k++) {
      c->owner[k]=v ? td : SIZE_MAX; c->owner_span[k]=end-i; c->owner_rows[k]=rows; c->owner_left[k]=left; c->owner_right[k]=right;
    }
    i=end;
  }
  for(;i<256;i++) c->owner[i]=SIZE_MAX;
  return 1;
invalid:
  c->status=EXR_FORMAT; return 0;
}
static int note_reference(rtf_context *c,const rtf_state *s) {
  size_t reference; char id[48],href[64],label[32];
  if(c->pending_note_ref!=SIZE_MAX) { c->status=EXR_FORMAT; return 0; }
  if(c->note_count>=10000) { c->status=EXR_LIMIT; return 0; }
  if(!run_flush(c) || !paragraph(c,s)) return 0;
  snprintf(id,sizeof(id),"rtf-ref-%zu",c->note_count+1); snprintf(href,sizeof(href),"#rtf-note-%zu",c->note_count+1); snprintf(label,sizeof(label),"%zu",c->note_count+1);
  reference=make(c,c->paragraph,EXR_NODE_LINK,"a",NULL);
  if(reference==SIZE_MAX || !set(c,reference,"id",id) || !set(c,reference,"href",href) || !set(c,reference,"role","doc-noteref") || make(c,reference,EXR_NODE_TEXT,NULL,label)==SIZE_MAX) return 0;
  c->pending_note_ref=reference; return 1;
}
static int note_start(rtf_context *c,rtf_state *s) {
  size_t node; char id[48]; rtf_note *note;
  if(s->note>=0 || c->active_note>=0) { c->status=EXR_FORMAT; return 0; }
  if(!run_flush(c) || !paragraph(c,s)) return 0;
  if(c->note_count>=10000 || !exr_grow((void **)&c->notes,&c->note_capacity,c->note_count+1,sizeof(*c->notes))) { c->status=EXR_LIMIT; return 0; }
  if(c->pending_note_ref==SIZE_MAX && !note_reference(c,s)) return 0;
  c->pending_note_ref=SIZE_MAX;
  node=make(c,SIZE_MAX,EXR_NODE_NOTE,"aside",NULL); if(node==SIZE_MAX) return 0;
  snprintf(id,sizeof(id),"rtf-note-%zu",c->note_count+1);
  if(!set(c,node,"id",id) || !set(c,node,"role","doc-footnote")) return 0;
  note=&c->notes[c->note_count]; note->node=node; note->paragraph=c->paragraph;
  c->note_lists=c->lists;
  s->note=c->active_note=(int)c->note_count++; s->field=-1; s->list_id=s->list_level=s->list_text=0; c->paragraph=SIZE_MAX; c->last_picture=0; return 1;
}
static int note_finish(rtf_context *c,const rtf_state *s) {
  size_t backlink; char href[64]; rtf_note *note;
  if(c->active_note!=s->note || s->note<0 || !run_flush(c) || !paragraph(c,s)) { if(c->status==EXR_OK) c->status=EXR_FORMAT; return 0; }
  note=&c->notes[s->note]; snprintf(href,sizeof(href),"#rtf-ref-%d",s->note+1);
  backlink=make(c,c->paragraph,EXR_NODE_LINK,"a",NULL);
  if(backlink==SIZE_MAX || !set(c,backlink,"href",href) || !set(c,backlink,"role","doc-backlink") || make(c,backlink,EXR_NODE_TEXT,NULL,"\xe2\x86\xa9")==SIZE_MAX) return 0;
  c->paragraph=note->paragraph; c->lists=c->note_lists; c->active_note=-1; c->last_picture=0; return 1;
}
static int table_control(rtf_context *c,const rtf_state *state,const char *word,long value,int has,int *handled) {
  *handled=1;
  if(c->active_note>=0 && (!strcmp(word,"trowd") || !strcmp(word,"cell") || !strcmp(word,"row") || !strcmp(word,"cellx") || !strcmp(word,"trleft") || !strncmp(word,"clm",3) || !strncmp(word,"clvm",4))) { c->status=EXR_FORMAT; return 0; }
  if(!strcmp(word,"trowd")) {
    if(c->row!=SIZE_MAX) { c->status=EXR_FORMAT; return 0; }
    if(!run_flush(c)) return 0;
    c->paragraph=SIZE_MAX; c->last_picture=0; c->lists.depth=0;
    if(c->table==SIZE_MAX) { size_t k; c->table=make(c,c->body,EXR_NODE_TABLE,"table",NULL); if(c->table==SIZE_MAX) return 0; for(k=0;k<256;k++) c->owner[k]=SIZE_MAX; }
    c->row=make(c,c->table,EXR_NODE_ROW,"tr",NULL); c->cell=SIZE_MAX; c->cell_count=c->definition_count=0; c->row_left=0; c->pending_horizontal=c->pending_vertical=0;
    return c->row!=SIZE_MAX;
  }
  if(!strcmp(word,"cellx")) {
    if(c->row==SIZE_MAX || !has || value< -10000000 || value>10000000 ||
       (c->definition_count && value<=c->boundaries[c->definition_count-1])) { c->status=EXR_FORMAT; return 0; }
    if(c->definition_count==256) { c->status=EXR_LIMIT; return 0; }
    c->horizontal[c->definition_count]=c->pending_horizontal; c->vertical[c->definition_count]=c->pending_vertical;
    c->pending_horizontal=c->pending_vertical=0; c->boundaries[c->definition_count++]=value; return 1;
  }
  if(!strcmp(word,"cell")) {
    if(c->row==SIZE_MAX) { c->status=EXR_FORMAT; return 0; }
    if(!run_flush(c)) return 0;
    if(c->cell==SIZE_MAX && !paragraph(c,state)) return 0;
    c->cell=SIZE_MAX; c->paragraph=SIZE_MAX; c->last_picture=0; c->cell_count++; return 1;
  }
  if(!strcmp(word,"row")) {
    size_t i;
    if(c->row==SIZE_MAX || !run_flush(c)) { if(c->status==EXR_OK) c->status=EXR_FORMAT; return 0; }
    if(c->cell!=SIZE_MAX || !c->cell_count || c->pending_horizontal || c->pending_vertical || (c->definition_count && c->definition_count!=c->cell_count)) { c->status=EXR_FORMAT; return 0; }
    for(i=0;i<c->definition_count;i++) { char number[48]; snprintf(number,sizeof(number),"%ld",c->boundaries[i]); if(!set(c,c->cells[i],"data-rtf-cellx",number)) return 0; }
    { char number[48]; snprintf(number,sizeof(number),"%ld",c->row_left); if(!set(c,c->row,"data-rtf-row-left",number)) return 0; }
    if(!row_merge(c)) return 0;
    c->row=c->cell=c->paragraph=SIZE_MAX; c->last_picture=0; return 1;
  }
  if(!strcmp(word,"intbl")) return 1;
  if(!strcmp(word,"itap")) { if(!has || value<0 || value>1) { c->status=EXR_FORMAT; return 0; } return 1; }
  if(!strcmp(word,"trleft")) { if(c->row==SIZE_MAX || !has || value< -10000000 || value>10000000) { c->status=EXR_FORMAT; return 0; } c->row_left=value; return 1; }
  if(!strcmp(word,"clmgf") || !strcmp(word,"clmrg") || !strcmp(word,"clvmgf") || !strcmp(word,"clvmrg")) {
    int vertical=!strncmp(word,"clv",3); unsigned char value_flag=(!strcmp(word,"clmgf") || !strcmp(word,"clvmgf")) ? 1 : 2;
    unsigned char *pending=vertical ? &c->pending_vertical : &c->pending_horizontal;
    if(c->row==SIZE_MAX || *pending) { c->status=EXR_FORMAT; return 0; } *pending=value_flag; return 1;
  }
  if(!strcmp(word,"nestcell") || !strcmp(word,"nestrow")) { c->status=EXR_FORMAT; return 0; }
  *handled=0; return 1;
}
static int emit(rtf_context *c,const rtf_state *s,uint32_t cp) {
  if(s->skip || s->destination) return 1;
  if(cp!=32 && cp!=9 && cp!=10 && cp!=13) c->last_picture=0;
  if(c->run.size && (memcmp(c->style.properties,s->properties,sizeof(s->properties)) || c->style.font!=s->font || c->style.field!=s->field || c->style.specified!=s->specified) && !run_flush(c)) return 0;
  if(!c->run.size) c->style=*s;
  if(!exr_codepoint(&c->run,cp)) { c->status=EXR_LIMIT; return 0; } return 1;
}
static int picture_bytes(rtf_context *c,int index,const void *data,size_t size) {
  rtf_picture *p=&c->pictures[index];
  if(size>32u*1024*1024-p->bytes.size || !exr_append(&p->bytes,data,size)) { c->status=EXR_LIMIT; return 0; }
  return 1;
}
static int font_commit(rtf_context *c,const rtf_state *s) {
  size_t start=0,end=c->font_name.size,old; char *name;
  if(s->font<0) { c->font_name.size=0; return 1; }
  if(!c->fonts || s->font>=RTF_FONTS) { c->status=EXR_FORMAT; return 0; }
  while(start<end && isspace((unsigned char)c->font_name.data[start])) start++;
  while(end>start && isspace((unsigned char)c->font_name.data[end-1])) end--;
  old=c->fonts[s->font] ? strlen(c->fonts[s->font]) : 0;
  if(end-start>EXR_MAX_TEXT-(c->metadata_bytes-old)) { c->status=EXR_LIMIT; return 0; }
  name=exr_copy(c->font_name.data ? c->font_name.data+start : "",end-start); if(!name) { c->status=EXR_MEMORY; return 0; }
  free(c->fonts[s->font]); c->fonts[s->font]=name; c->metadata_bytes=c->metadata_bytes-old+end-start;
  c->font_name.size=0; if(c->font_name.data) c->font_name.data[0]=0; return 1;
}
static int literal(rtf_context *c,const rtf_state *s,uint32_t cp) {
  if(s->skip) return 1;
  if(s->destination>=LIST_TABLE) return number_literal(c,s,cp,0);
  if(!cp) { c->status=EXR_FORMAT; return 0; }
  if(s->destination==3) {
    if(cp==';') return font_commit(c,s);
    if(c->font_name.size>=65536 || !exr_codepoint(&c->font_name,cp) || c->font_name.size>65536) { c->status=EXR_LIMIT; return 0; } return 1;
  }
  if(s->destination==4 && s->field>=0) {
    exr_buffer *instruction=&c->fields[s->field].instruction;
    size_t before=instruction->size;
    if(instruction->size>=65536 || c->metadata_bytes>EXR_MAX_TEXT-4 || !exr_codepoint(instruction,cp) || instruction->size>65536) { c->status=EXR_LIMIT; return 0; }
    c->metadata_bytes+=instruction->size-before; return 1;
  }
  if(s->destination==5 || s->destination==7) {
    exr_buffer *value=s->destination==5 ? &c->bookmark : &c->title;
    if(value->size>=65536 || !exr_codepoint(value,cp) || value->size>65536) { c->status=EXR_LIMIT; return 0; } return 1;
  }
  if(s->destination==2 && s->picture>=0) {
    rtf_picture *p=&c->pictures[s->picture]; unsigned char byte; int digit;
    if(!p->type || cp==32 || cp==9 || cp==10 || cp==13) return 1;
    if(cp<128 && isxdigit((unsigned char)cp)) digit=isdigit((unsigned char)cp) ? (int)cp-'0' : tolower((unsigned char)cp)-'a'+10;
    else { c->status=EXR_FORMAT; return 0; }
    if(p->nibble<0) p->nibble=digit;
    else { byte=(unsigned char)(p->nibble*16+digit); p->nibble=-1; return picture_bytes(c,s->picture,&byte,1); }
    return 1;
  }
  if(s->destination==1) {
    if(cp==';') {
      if(c->color_count>=4096) { c->status=EXR_LIMIT; return 0; }
      c->colors[c->color_count++]=c->components ? (c->red<<24)|(c->green<<16)|(c->blue<<8)|255u : 0;
      c->red=c->green=c->blue=c->components=0;
    }
    return 1;
  }
  return emit(c,s,cp);
}
static int line_break(rtf_context *c,const rtf_state *s,int soft) {
  if(!run_flush(c)) return 0;
  c->last_picture=0;
  if(soft) {
    if(!paragraph(c,s) || make(c,c->paragraph,EXR_NODE_BREAK,"br",NULL)==SIZE_MAX) return 0;
  } else { c->paragraph=SIZE_MAX; if(c->row==SIZE_MAX) c->table=SIZE_MAX; }
  return 1;
}
static int picture_start(rtf_context *c,rtf_state *s) {
  rtf_picture *p;
  if(s->picture>=0) { c->status=EXR_FORMAT; return 0; }
  if(c->picture_count>=9996 || !exr_grow((void **)&c->pictures,&c->picture_capacity,c->picture_count+1,sizeof(*c->pictures))) { c->status=EXR_LIMIT; return 0; }
  s->picture=(int)c->picture_count++; s->destination=2; p=&c->pictures[s->picture]; memset(p,0,sizeof(*p));
  p->nibble=-1; p->scale_x=p->scale_y=100; return run_flush(c);
}
static int picture_finish(rtf_context *c,const rtf_state *s) {
  rtf_picture *p=&c->pictures[s->picture]; exr_resource *resources; exr_resource_data *encoded;
  size_t i=c->doc->resource_count,node; char path[100],id[48],value[64];
  const char *mime=p->type==1 ? "image/png" : p->type==2 ? "image/jpeg" : p->type==3 ? "image/wmf" : "image/emf";
  if(!p->type) return 1;
  if(p->nibble>=0 || !p->bytes.size || (p->type==1 && (p->bytes.size<8 || memcmp(p->bytes.data,"\x89PNG\r\n\x1a\n",8))) ||
      (p->type==2 && (p->bytes.size<2 || (unsigned char)p->bytes.data[0]!=255 || (unsigned char)p->bytes.data[1]!=216))) { c->status=EXR_FORMAT; return 0; }
  resources=realloc(c->doc->resources,(i+1)*sizeof(*resources)); if(!resources) { c->status=EXR_MEMORY; return 0; }
  c->doc->resources=resources; encoded=realloc(c->doc->resource_data,(i+1)*sizeof(*encoded));
  if(!encoded) { c->status=EXR_MEMORY; return 0; } c->doc->resource_data=encoded;
  c->doc->resource_count=c->doc->resource_capacity=i+1; memset(&resources[i],0,sizeof(resources[i]));
  encoded[i]=(exr_resource_data){(unsigned char *)p->bytes.data,p->bytes.size}; p->bytes.data=NULL; p->bytes.size=p->bytes.capacity=0;
  snprintf(id,sizeof(id),"picture-%zu",i);
  snprintf(path,sizeof(path),"assets/rtf-picture-%zu.%s",i,p->type==1 ? "png" : p->type==2 ? "jpg" : p->type==3 ? "wmf" : "emf");
  resources[i].id=exr_model_copy(c->doc,id,strlen(id)); resources[i].path=exr_model_copy(c->doc,path,strlen(path));
  resources[i].media_type=exr_model_copy(c->doc,mime,strlen(mime)); resources[i].properties=exr_model_copy(c->doc,"",0);
  if(!resources[i].id || !resources[i].path || !resources[i].media_type || !resources[i].properties || !paragraph(c,s)) { c->status=EXR_LIMIT; return 0; }
  node=make(c,c->paragraph,EXR_NODE_IMAGE,"img",NULL); if(node==SIZE_MAX || !set(c,node,"src",path)) return 0;
  if(p->goal_width || p->width) {
    snprintf(value,sizeof(value),"%.4f",(p->goal_width ? p->goal_width/15.0 : p->width)*p->scale_x/100.0);
    if(!set(c,node,"width",value)) return 0;
  }
  if(p->goal_height || p->height) {
    snprintf(value,sizeof(value),"%.4f",(p->goal_height ? p->goal_height/15.0 : p->height)*p->scale_y/100.0);
    if(!set(c,node,"height",value)) return 0;
  }
  c->last_picture=p->type==1 || p->type==2; return 1;
}
static int picture_control(rtf_context *c,rtf_state *s,const char *word,long value,int has) {
  rtf_picture *p=&c->pictures[s->picture]; int *dimension=NULL;
  if(!strcmp(word,"pngblip")) p->type=1;
  else if(!strcmp(word,"jpegblip")) p->type=2;
  else if(!strcmp(word,"wmetafile")) p->type=3;
  else if(!strcmp(word,"emfblip")) p->type=4;
  else {
    if(!strcmp(word,"picw")) dimension=&p->width;
    else if(!strcmp(word,"pich")) dimension=&p->height;
    else if(!strcmp(word,"picwgoal")) dimension=&p->goal_width;
    else if(!strcmp(word,"pichgoal")) dimension=&p->goal_height;
    else if(!strcmp(word,"picscalex")) dimension=&p->scale_x;
    else if(!strcmp(word,"picscaley")) dimension=&p->scale_y;
    if(dimension) { if(!has || value<0 || value>100000000) { c->status=EXR_FORMAT; return 0; } *dimension=(int)value; }
  }
  return 1;
}
static int field_start(rtf_context *c,rtf_state *s) {
  if(c->field_count>=10000 || !exr_grow((void **)&c->fields,&c->field_capacity,c->field_count+1,sizeof(*c->fields))) { c->status=EXR_LIMIT; return 0; }
  s->field=(int)c->field_count++; memset(&c->fields[s->field],0,sizeof(*c->fields)); return run_flush(c);
}
static int same(const char *a,const char *b) {
  while(*a && *b) { if(tolower((unsigned char)*a++)!=tolower((unsigned char)*b++)) return 0; }
  return !*a && !*b;
}
static int field_token(rtf_context *c,const char **cursor,exr_buffer *out) {
  const char *p=*cursor; int quote;
  out->size=0;
  while(*p && isspace((unsigned char)*p)) p++;
  if(!*p) { *cursor=p; return 0; }
  quote=*p=='"'; if(quote) p++;
  while(*p && (quote ? *p!='"' : !isspace((unsigned char)*p))) {
    if(quote && *p=='\\' && (p[1]=='"' || p[1]=='\\')) p++;
    if(!exr_append(out,p++,1)) { c->status=EXR_LIMIT; return 0; }
  }
  if(quote) { if(*p!='"') return 0; p++; }
  if(!exr_append(out,"",0)) { c->status=EXR_LIMIT; return 0; }
  *cursor=p; return 1;
}
static int metadata_append(rtf_context *c,exr_buffer *buffer,const char *text) {
  if(!put(buffer,text)) { c->status=EXR_LIMIT; return 0; } return 1;
}
static int field_link(rtf_context *c,int index) {
  rtf_field *f=&c->fields[index]; exr_buffer token={0},url={0},anchor={0},href={0};
  const char *cursor=f->instruction.data ? f->instruction.data : ""; int ok=1;
  if(f->ready) return 1;
  f->ready=1;
  if(!field_token(c,&cursor,&token) || !same(token.data,"HYPERLINK")) goto done;
  while(field_token(c,&cursor,&token)) {
    if(token.data[0]=='\\') {
      if(same(token.data,"\\l")) {
        if(!field_token(c,&cursor,&token) || !metadata_append(c,&anchor,token.data)) goto done;
      } else if(same(token.data,"\\o") || same(token.data,"\\t")) {
        if(!field_token(c,&cursor,&token)) goto done;
      } else if(!same(token.data,"\\m") && !same(token.data,"\\n")) goto done;
    } else {
      if(url.size || !metadata_append(c,&url,token.data)) goto done;
    }
  }
  if(!url.size && !anchor.size) goto done;
  if(url.size && !put(&href,url.data)) { ok=0; goto done; }
  if(anchor.size && (!put(&href,url.size ? "#" : "#bookmark-") || !exr_uri_path(&href,anchor.data))) { ok=0; goto done; }
  if(href.size>EXR_MAX_TEXT-(c->metadata_bytes-f->instruction.size)) { c->status=EXR_LIMIT; goto done; }
  f->href=href.data; href.data=NULL;
  c->metadata_bytes+=strlen(f->href);
done:
  free(token.data); free(url.data); free(anchor.data); free(href.data);
  c->metadata_bytes-=f->instruction.size;
  free(f->instruction.data); memset(&f->instruction,0,sizeof(f->instruction));
  if(!ok && c->status==EXR_OK) c->status=EXR_LIMIT;
  return ok && c->status==EXR_OK;
}
static int destination_finish(rtf_context *c,const rtf_state *s,const rtf_state *parent) {
  if(s->destination>=LIST_TABLE && !number_finish(c,s,parent)) return 0;
  if(s->note>=0 && s->note!=parent->note && !note_finish(c,s)) return 0;
  if(s->list_text && !parent->list_text && !paragraph_style(c,parent)) return 0;
  if(s->destination==5 && parent->destination!=5) {
    exr_buffer id={0}; size_t start=0,end=c->bookmark.size,node; int ok;
    while(start<end && isspace((unsigned char)c->bookmark.data[start])) start++;
    while(end>start && isspace((unsigned char)c->bookmark.data[end-1])) end--;
    if(start==end) return 1;
    ok=put(&id,"bookmark-") && exr_append(&id,c->bookmark.data+start,end-start) && paragraph(c,s);
    node=ok ? make(c,c->paragraph,EXR_NODE_ELEMENT,"span",NULL) : SIZE_MAX;
    ok=ok && node!=SIZE_MAX && set(c,node,"id",id.data); free(id.data); return ok;
  }
  if(s->destination==7 && parent->destination!=7) {
    char *title=exr_copy(c->title.data,c->title.size),*node_title;
    if(!title) { c->status=EXR_MEMORY; return 0; }
    node_title=exr_model_copy(c->doc,title,c->title.size);
    if(!node_title) { free(title); c->status=EXR_LIMIT; return 0; }
    free(c->doc->title); c->doc->title=title;
    free((void *)c->doc->nodes[c->title_text].text); c->doc->nodes[c->title_text].text=node_title;
  }
  return 1;
}
static int style_control(rtf_context *c,rtf_state *s,const char *word,long value,int has) {
  int key=-1;
  if(!strcmp(word,"b")) key=BOLD;
  else if(!strcmp(word,"i")) key=ITALIC;
  else if(!strcmp(word,"ul") || !strcmp(word,"ulnone")) key=UNDERLINE;
  else if(!strcmp(word,"strike")) key=STRIKE;
  if(key>=0) { s->properties[key]=strcmp(word,"ulnone") && (!has || value!=0); s->specified|=1u<<key; }
  else if(!strcmp(word,"fs")) { if(!has || value<1 || value>32767) return 0; s->properties[SIZE]=(int)value; s->specified|=1u<<SIZE; }
  else if(!strcmp(word,"cf") || !strcmp(word,"highlight")) {
    if(!has || value<0 || value>=4096) return 0;
    key=!strcmp(word,"cf") ? COLOR : BACKGROUND; s->properties[key]=(int)value; s->specified|=1u<<key;
  } else if(!strcmp(word,"ql")) { s->properties[ALIGN]=0; s->specified|=1u<<ALIGN; }
  else if(!strcmp(word,"qr")) { s->properties[ALIGN]=1; s->specified|=1u<<ALIGN; }
  else if(!strcmp(word,"qc")) { s->properties[ALIGN]=2; s->specified|=1u<<ALIGN; }
  else if(!strcmp(word,"qj")) { s->properties[ALIGN]=3; s->specified|=1u<<ALIGN; }
  else if(!strcmp(word,"ltrpar")) { s->properties[DIRECTION]=1; s->specified|=1u<<DIRECTION; }
  else if(!strcmp(word,"rtlpar")) { s->properties[DIRECTION]=2; s->specified|=1u<<DIRECTION; }
  else if(!strcmp(word,"plain")) { memset(s->properties,0,ALIGN*sizeof(*s->properties)); s->font=-1; s->font_set=1; s->specified|=(1u<<ALIGN)-1; }
  else if(!strcmp(word,"pard")) { memset(s->properties+ALIGN,0,(RTF_PROPERTIES-ALIGN)*sizeof(*s->properties)); s->specified&=(1u<<ALIGN)-1; if(!s->list_text) s->list_id=s->list_level=0; }
  else if(!strcmp(word,"ls")) { if(!has || value<0 || value>INT_MAX) { c->status=EXR_FORMAT; return 0; } s->list_id=(int)value; }
  else if(!strcmp(word,"ilvl")) { if(!has || value<0 || value>8) { c->status=EXR_FORMAT; return 0; } s->list_level=(int)value; }
  else {
    if(!strcmp(word,"li")) key=LEFT;
    else if(!strcmp(word,"ri")) key=RIGHT;
    else if(!strcmp(word,"fi")) key=INDENT;
    else if(!strcmp(word,"sb")) key=BEFORE;
    else if(!strcmp(word,"sa")) key=AFTER;
    else if(!strcmp(word,"sl")) key=LEADING;
    else if(!strcmp(word,"slmult")) key=MULTIPLE;
    if(key>=0) { if(!has || value < -10000000 || value>10000000) return 0; s->properties[key]=(int)value; s->specified|=1u<<key; }
  }
  (void)c; return 1;
}
exr_status exr_rtf(exr_document *d, const void *data, size_t n, exr_error *e) {
  const unsigned char *s = data;
  rtf_state states[256] = {{0}};
  rtf_context context={0};
  size_t depth = 0, i = 0;
  int fallback = 0, closed = 0;
  uint32_t high = 0;

  exr_status result = EXR_FORMAT;
  if (n < 5 || memcmp(s, "{\\rtf", 5))
    return exr_fail(e, EXR_FORMAT, "Invalid RTF header");
  context.doc=d; context.error=e; context.paragraph=context.table=context.row=context.cell=SIZE_MAX; states[0].uc=1; states[0].picture=states[0].font=states[0].field=states[0].note=-1; states[0].definition=states[0].number_level=states[0].override_index=states[0].override_level=-1; context.active_note=-1; context.pending_note_ref=SIZE_MAX;
  if(exr_model_node(d,SIZE_MAX,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX) return EXR_LIMIT;
  {
    size_t chapter=make(&context,0,EXR_NODE_CHAPTER,NULL,NULL),html,head,title;
    if(chapter==SIZE_MAX) return EXR_LIMIT;
    d->chapters=calloc(1,sizeof(*d->chapters)); if(!d->chapters) return EXR_MEMORY;
    d->chapter_count=d->chapter_capacity=1; d->chapters[0]=(exr_chapter){"main","book.xhtml",chapter,SIZE_MAX,1,1};
    html=make(&context,chapter,EXR_NODE_ELEMENT,"html",NULL); if(html==SIZE_MAX) return EXR_LIMIT;
    head=make(&context,html,EXR_NODE_ELEMENT,"head",NULL); if(head==SIZE_MAX) return EXR_LIMIT;
    title=make(&context,head,EXR_NODE_ELEMENT,"title",NULL); if(title==SIZE_MAX) return EXR_LIMIT;
    context.title_text=make(&context,title,EXR_NODE_TEXT,NULL,"Untitled"); if(context.title_text==SIZE_MAX) return EXR_LIMIT;
    context.body=make(&context,html,EXR_NODE_ELEMENT,"body",NULL); if(context.body==SIZE_MAX) return EXR_LIMIT;
  }
  while (i < n) {
    unsigned c = s[i++];
    /* After the root group only the NUL/whitespace padding some writers append is accepted. */
    if (closed) {
      if (c == 0 || c == '\r' || c == '\n' || c == ' ' || c == '\t')
        continue;
      goto done;
    }
    if (c == '{') {
      fallback = 0; /* Group delimiters terminate the Unicode fallback sequence. */
      if(!run_flush(&context)) goto done;
      if (depth + 1 >= 256)
        goto done;
      states[depth].star=0;
      states[depth + 1] = states[depth];
      states[depth + 1].inherited_skip=states[depth].skip;
      depth++;
      continue;
    }
    if (c == '}') {
      fallback = 0;
      if(!run_flush(&context)) goto done;
      if (!depth)
        goto done;
      if(states[depth].picture>=0 && states[depth].picture!=states[depth-1].picture && !picture_finish(&context,&states[depth])) goto done;
      if(!destination_finish(&context,&states[depth],&states[depth-1])) goto done;
      depth--;
      closed = !depth;
      continue;
    }
    if (c == '\\') {
      char word[40] = {0};
      size_t k = 0;
      long value = 0; uint64_t magnitude=0;
      int negative = 0, has = 0, optional = 0;
      if (i >= n)
        goto done;
      c = s[i++];
      if (!isalpha(c) && c != '\'') {
        if (fallback) {
          fallback--;
          continue;
        }
        if(c!='*') states[depth].star=0;
        if (c == '*') { states[depth].skip = 1; states[depth].star=1; }
        else if ((c == '\\' || c == '{' || c == '}') && !states[depth].skip &&
                 !literal(&context,&states[depth],c))
          goto done;
        continue;
      }
      if (c == '\'') {
        unsigned a, b;
        if (n - i < 2 || !isxdigit(s[i]) || !isxdigit(s[i + 1]))
          goto done;
        a = (unsigned)(isdigit(s[i]) ? s[i] - '0' : tolower(s[i]) - 'a' + 10);
        b = (unsigned)(isdigit(s[i + 1]) ? s[i + 1] - '0' : tolower(s[i + 1]) - 'a' + 10);
        c = a * 16 + b;
        i += 2;
        if (fallback) {
          fallback--;
          continue;
        }
        states[depth].star=0;
        if(!states[depth].skip) {
          if(states[depth].destination==LEVEL_TEXT || states[depth].destination==LEVEL_NUMBERS) { if(!number_literal(&context,&states[depth],c,1)) goto done; }
          else if(!literal(&context,&states[depth],exr_windows1252((unsigned char)c))) goto done;
        }
        continue;
      }
      word[k++] = (char)c;
      while (i < n && isalpha(s[i])) {
        if (k < 39)
          word[k++] = (char)s[i];
        i++;
      }
      if (i < n && s[i] == '-') {
        negative = 1;
        i++;
      }
      while (i < n && isdigit(s[i])) {
        has = 1;
        unsigned digit=s[i]-'0'; uint64_t maximum=negative ? UINT64_C(2147483648) : UINT64_C(2147483647);
        if(magnitude>(maximum-digit)/10) goto done;
        magnitude=magnitude*10+digit; i++;
      }
      value=negative ? (long)-(int64_t)magnitude : (long)magnitude;
      if (i < n && s[i] == ' ')
        i++;
      if (!strcmp(word, "bin")) {
        if (!has || value < 0 || (size_t)value > n - i)
          goto done;
        if(!fallback && !states[depth].skip && states[depth].destination==2 && states[depth].picture>=0) {
          if(context.pictures[states[depth].picture].nibble>=0 || !picture_bytes(&context,states[depth].picture,s+i,(size_t)value)) goto done;
        }
        i += (size_t)value;
        if (fallback)
          fallback--;
        continue;
      }
      /* A whole control word counts as one fallback character, without executing it. */
      if (fallback) {
        fallback--;
        continue;
      }
      optional=states[depth].star; states[depth].star=0;
      if(!states[depth].inherited_skip && states[depth].destination==0 && (!states[depth].skip || optional)) {
        if(!strcmp(word,"listtable") || !strcmp(word,"listoverridetable")) { states[depth].skip=0; states[depth].destination=!strcmp(word,"listtable") ? LIST_TABLE : OVERRIDE_TABLE; continue; }
        if(!strcmp(word,"listtext") || !strcmp(word,"pntext")) { states[depth].skip=0; states[depth].list_text=1; if(!states[depth].list_id) states[depth].list_id=-1; continue; }
        if(!strcmp(word,"footnote")) { states[depth].skip=0; if(!note_start(&context,&states[depth])) goto done; continue; }
        if(!strcmp(word,"fonttbl")) {
          if(!context.fonts) { context.fonts=calloc(RTF_FONTS,sizeof(*context.fonts)); if(!context.fonts) { context.status=EXR_MEMORY; goto done; } }
          states[depth].skip=0; states[depth].destination=3; states[depth].font=-1; context.font_name.size=0; continue;
        }
        if(!strcmp(word,"field")) { states[depth].skip=0; if(!field_start(&context,&states[depth])) goto done; continue; }
        if(!strcmp(word,"bkmkstart")) {
          states[depth].skip=0; states[depth].destination=5; context.bookmark.size=0; if(!run_flush(&context)) goto done; continue;
        }
        if(!strcmp(word,"bkmkend")) { states[depth].skip=1; continue; }
        if(!strcmp(word,"info")) { states[depth].skip=0; states[depth].destination=6; continue; }
      }
      if(!states[depth].skip && states[depth].destination==6 && !strcmp(word,"title")) { states[depth].destination=7; context.title.size=0; continue; }
      if(!states[depth].inherited_skip && (!states[depth].skip || optional) && states[depth].field>=0 &&
          (states[depth].destination==0 || states[depth].destination==4)) {
        if(!strcmp(word,"fldinst")) { states[depth].skip=0; states[depth].destination=4; continue; }
        if(!strcmp(word,"fldrslt")) { states[depth].skip=0; states[depth].destination=0; if(!field_link(&context,states[depth].field)) goto done; continue; }
      }
      if(!states[depth].skip && (states[depth].destination==0 || states[depth].destination==3) && (!strcmp(word,"f") || !strcmp(word,"deff"))) {
        if(!has || value<0 || value>=RTF_FONTS) goto done;
        if(!strcmp(word,"deff")) context.default_font=(int)value;
        else { states[depth].font=(int)value; states[depth].font_set=1; }
        continue;
      }
      if(optional && !states[depth].inherited_skip && states[depth].destination==0 && !strcmp(word,"shppict")) { states[depth].skip=0; continue; }
      if(!states[depth].skip && !strcmp(word,"nonshppict") && context.last_picture) { states[depth].skip=1; continue; }
      if(!states[depth].skip && states[depth].destination==0 && !strcmp(word,"pict")) { if(!picture_start(&context,&states[depth])) goto done; continue; }
      if(!states[depth].skip && states[depth].destination==2) { if(!picture_control(&context,&states[depth],word,value,has)) goto done; continue; }
      if(!states[depth].skip && states[depth].destination==0 && !strcmp(word,"colortbl")) {
        states[depth].destination=1; context.color_count=0; context.red=context.green=context.blue=context.components=0; continue;
      }
      if(!states[depth].skip && states[depth].destination==1) {
        if(!strcmp(word,"red") || !strcmp(word,"green") || !strcmp(word,"blue")) {
          if(!has || value<0 || value>255) goto done;
          if(!strcmp(word,"red")) context.red=(unsigned)value;
          else if(!strcmp(word,"green")) context.green=(unsigned)value;
          else context.blue=(unsigned)value;
          context.components=1;
        }
        continue;
      }
      if (!strcmp(word, "stylesheet") || !strcmp(word, "fontemb") || !strcmp(word, "fontfile") || !strcmp(word, "object") ||
          !strcmp(word, "header") || !strcmp(word, "footer")) {
        states[depth].skip = 1;
        continue;
      }
      if (states[depth].skip)
        continue;
      { int handled; if(!number_control(&context,&states[depth],word,value,has,&handled)) goto done; if(handled) continue; }
      if(states[depth].destination && (!strcmp(word,"par") || !strcmp(word,"line") || !strcmp(word,"tab"))) {
        if(!literal(&context,&states[depth],' ')) goto done;
        continue;
      }
      if(!states[depth].destination && !strcmp(word,"chftn")) {
        if(states[depth].note>=0) { char label[32]; size_t k; snprintf(label,sizeof(label),"%d ",states[depth].note+1); for(k=0;label[k];k++) if(!literal(&context,&states[depth],(unsigned char)label[k])) goto done; }
        else if(!note_reference(&context,&states[depth])) goto done;
        continue;
      }
      if(!states[depth].destination && !strcmp(word,"ftnalt") && states[depth].note>=0) { if(!set(&context,context.notes[states[depth].note].node,"role","doc-endnote")) goto done; continue; }
      if(!states[depth].destination) {
        int handled; if(!table_control(&context,&states[depth],word,value,has,&handled)) goto done; if(handled) continue;
      }
      if (!strcmp(word, "ansicpg") && value != 1252)
        goto done;
      if (!strcmp(word, "uc")) {
        if (!has || value < 0 || value > 16)
          goto done;
        states[depth].uc = (int)value;
      } else if (!strcmp(word, "u")) {
        uint32_t cp;
        if (!has || value < -32768 || value > 65535)
          goto done;
        cp = (uint16_t)value;
        if (cp >= 0xd800 && cp <= 0xdbff) {
          if (high)
            goto done;
          high = cp;
        } else {
          if (cp >= 0xdc00 && cp <= 0xdfff) {
            if (!high)
              goto done;
            cp = 0x10000 + ((high - 0xd800) << 10) + (cp - 0xdc00);
            high = 0;
          } else if (high)
            goto done;
          if ((!cp && states[depth].destination!=LEVEL_TEXT) || !literal(&context,&states[depth],cp))
            goto done;
        }
        fallback = states[depth].uc;
      } else if (!strcmp(word, "par") || !strcmp(word, "line")) {
        if (!line_break(&context,&states[depth],!strcmp(word,"line")))
          goto done;
      } else if (!strcmp(word, "tab")) {
        if (!literal(&context,&states[depth],' '))
          goto done;
      } else if(!style_control(&context,&states[depth],word,value,has)) goto done;
      continue;
    }
    if(states[depth].skip && c!=' ' && c!='\t' && c!='\r' && c!='\n') states[depth].star=0;
    if (c == '\r' || c == '\n' || states[depth].skip)
      continue;
    if (fallback) {
      fallback--;
      continue;
    }
    if (high || !c || !literal(&context,&states[depth],exr_windows1252((unsigned char)c)))
      goto done;
  }
  if (depth || high || !run_flush(&context) || context.row!=SIZE_MAX || context.active_note>=0 || context.pending_note_ref!=SIZE_MAX)
    goto done;
  for(i=0;i<context.note_count;i++) append_existing(&context,context.body,context.notes[i].node);
  result = EXR_OK;
done:
  if(context.fonts) { for(i=0;i<RTF_FONTS;i++) free(context.fonts[i]); }
  for(i=0;i<context.field_count;i++) { free(context.fields[i].instruction.data); free(context.fields[i].href); }
  free(context.fields); free(context.fonts); free(context.font_name.data); free(context.bookmark.data); free(context.title.data);
  for(i=0;i<context.picture_count;i++) free(context.pictures[i].bytes.data);
  free(context.pictures); free(context.notes); free(context.number_definitions); free(context.number_overrides); free(context.run.data);
  if(result==EXR_OK) return EXR_OK;
  result=context.status!=EXR_OK ? context.status : EXR_FORMAT;
  return exr_fail(e,result,"Invalid or unsupported RTF stream");
}
