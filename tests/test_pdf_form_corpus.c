/* SPDX-License-Identifier: MIT */
/* Independent-document AcroForm driver: reads the frozen corpus, executes the
   frozen edit plan, writes one edited PDF per accepted document and records
   every measurement as tab separated records that the Python checker converts
   into per-file JSON.  Verdicts live in the checker; this program only reports
   what the implementation did. */
#include "exreader.h"
#include "../src/pdf_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>

static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"corpus driver line %d failed: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)

typedef struct {
  unsigned char *field; size_t field_size;
  unsigned char **values; size_t *value_sizes; size_t value_count;
} change_spec;

typedef struct {
  char id[16], base[192], op[32];
  int font;
  change_spec *items; size_t count, capacity;
} plan_entry;

typedef struct { const char *name; const char **values; size_t count; } api_change;

static plan_entry *plan;
static size_t plan_count, plan_capacity;
static FILE *results;
static int cancel_state;

static const char *kind_name(exr_pdf_field_kind kind) {
  switch(kind) {
    case EXR_PDF_FIELD_TEXT: return "text";
    case EXR_PDF_FIELD_CHECKBOX: return "checkbox";
    case EXR_PDF_FIELD_RADIO: return "radio";
    case EXR_PDF_FIELD_CHOICE: return "choice";
    case EXR_PDF_FIELD_PUSHBUTTON: return "pushbutton";
    case EXR_PDF_FIELD_SIGNATURE: return "signature";
    default: return "unknown";
  }
}

static const char *status_name(exr_status status) {
  switch(status) {
    case EXR_OK: return "EXR_OK";
    case EXR_ARGUMENT: return "EXR_ARGUMENT";
    case EXR_MEMORY: return "EXR_MEMORY";
    case EXR_IO: return "EXR_IO";
    case EXR_ENCODING: return "EXR_ENCODING";
    case EXR_FORMAT: return "EXR_FORMAT";
    case EXR_LIMIT: return "EXR_LIMIT";
    case EXR_DATABASE: return "EXR_DATABASE";
    case EXR_FONT: return "EXR_FONT";
    case EXR_CANCELLED: return "EXR_CANCELLED";
    case EXR_PASSWORD: return "EXR_PASSWORD";
    default: return "EXR_UNSUPPORTED";
  }
}

static unsigned char *read_file(const char *path,size_t *size) {
  FILE *file=fopen(path,"rb"); unsigned char *data; long length;
  *size=0;
  if(!file) return NULL;
  if(fseek(file,0,SEEK_END)!=0) { fclose(file); return NULL; }
  length=ftell(file);
  if(length<0 || fseek(file,0,SEEK_SET)!=0) { fclose(file); return NULL; }
  data=malloc((size_t)length+1);
  if(!data) { fclose(file); return NULL; }
  if(length && fread(data,1,(size_t)length,file)!=(size_t)length) { free(data); fclose(file); return NULL; }
  data[length]=0; *size=(size_t)length; fclose(file); return data;
}

static int write_file(const char *path,const void *data,size_t size) {
  FILE *file=fopen(path,"wb"); int ok;
  if(!file) return 0;
  ok=fwrite(data,1,size,file)==size;
  fclose(file); return ok;
}

static unsigned char *unhex(const char *text,size_t *size) {
  size_t length=strlen(text),i; unsigned char *data;
  if(length%2) return NULL;
  data=malloc(length/2+1);
  if(!data) return NULL;
  for(i=0;i<length/2;i++) {
    unsigned value=0,j;
    for(j=0;j<2;j++) {
      char c=text[i*2+j]; unsigned digit;
      if(c>='0' && c<='9') digit=(unsigned)(c-'0');
      else if(c>='a' && c<='f') digit=(unsigned)(c-'a'+10);
      else if(c>='A' && c<='F') digit=(unsigned)(c-'A'+10);
      else { free(data); return NULL; }
      value=value*16+digit;
    }
    data[i]=(unsigned char)value;
  }
  data[length/2]=0; *size=length/2; return data;
}

static void emit_hex(const unsigned char *data,size_t size) {
  static const char digits[]="0123456789abcdef"; size_t i;
  if(!data) { fputc('-',results); return; }
  for(i=0;i<size;i++) { fputc(digits[data[i]>>4],results); fputc(digits[data[i]&15],results); }
}

static uint64_t fnv(const unsigned char *data,size_t size) {
  uint64_t hash=1469598103934665603ull; size_t i;
  for(i=0;i<size;i++) { hash^=data[i]; hash*=1099511628211ull; }
  return hash;
}


static plan_entry *plan_find(const char *id) {
  size_t i;
  for(i=0;i<plan_count;i++) if(!strcmp(plan[i].id,id)) return &plan[i];
  return NULL;
}

static void plan_change(plan_entry *entry,unsigned char *field,size_t field_size,
  unsigned char **values,size_t *sizes,size_t count) {
  change_spec *items;
  if(entry->count==entry->capacity) {
    size_t capacity=entry->capacity ? entry->capacity*2 : 4;
    items=realloc(entry->items,capacity*sizeof(*items));
    if(!items) { fprintf(stderr,"plan allocation failed\n"); exit(1); }
    entry->items=items; entry->capacity=capacity;
  }
  entry->items[entry->count].field=field;
  entry->items[entry->count].field_size=field_size;
  entry->items[entry->count].values=values;
  entry->items[entry->count].value_sizes=sizes;
  entry->items[entry->count].value_count=count;
  entry->count++;
}

static char *next_cell(char **at) {
  char *start=*at,*tab;
  if(!start) return NULL;
  tab=strchr(start,'\t');
  if(tab) { *tab=0; *at=tab+1; } else *at=NULL;
  return start;
}

static void parse_plan(const char *path) {
  size_t size=0; unsigned char *data=read_file(path,&size); char *line,*end;
  if(!data) { fprintf(stderr,"cannot read plan\n"); exit(1); }
  line=(char *)data;
  while(line && *line) {
    char *at;
    end=strchr(line,'\n');
    if(end) *end=0;
    if(*line && line[strlen(line)-1]=='\r') line[strlen(line)-1]=0;
    at=line;
    if(line[0]=='P') {
      char *tag=next_cell(&at),*id=next_cell(&at),*base=next_cell(&at),*op=next_cell(&at),*font=next_cell(&at);
      plan_entry *entry;
      if(!tag || !id || !base || !op || !font) { fprintf(stderr,"malformed plan line\n"); exit(1); }
      if(plan_count==plan_capacity) {
        size_t capacity=plan_capacity ? plan_capacity*2 : 16;
        plan_entry *more=realloc(plan,capacity*sizeof(*more));
        if(!more) { fprintf(stderr,"plan allocation failed\n"); exit(1); }
        plan=more; plan_capacity=capacity;
      }
      entry=&plan[plan_count++];
      memset(entry,0,sizeof(*entry));
      snprintf(entry->id,sizeof(entry->id),"%s",id);
      snprintf(entry->base,sizeof(entry->base),"%s",base);
      snprintf(entry->op,sizeof(entry->op),"%s",op);
      entry->font=atoi(font);
    } else if(line[0]=='C') {
      char *tag=next_cell(&at),*id=next_cell(&at),*field=next_cell(&at),*cell;
      plan_entry *entry; unsigned char **values=NULL; size_t *sizes=NULL,count=0,capacity=0;
      unsigned char *name; size_t name_size;
      if(!tag || !id || !field) { fprintf(stderr,"malformed change line\n"); exit(1); }
      entry=plan_find(id);
      if(!entry) { fprintf(stderr,"change before plan\n"); exit(1); }
      name=unhex(field,&name_size);
      if(!name) { fprintf(stderr,"bad field hex\n"); exit(1); }
      while((cell=next_cell(&at))!=NULL) {
        size_t value_size; unsigned char *value=unhex(cell,&value_size);
        if(!value) { fprintf(stderr,"bad value hex\n"); exit(1); }
        if(count==capacity) {
          size_t more=capacity ? capacity*2 : 4;
          unsigned char **bigger=(unsigned char **)realloc(values,more*sizeof(*bigger));
          size_t *bigger_sizes=(size_t *)realloc(sizes,more*sizeof(*bigger_sizes));
          if(!bigger || !bigger_sizes) { fprintf(stderr,"plan allocation failed\n"); exit(1); }
          values=bigger; sizes=bigger_sizes; capacity=more;
        }
        values[count]=value; sizes[count]=value_size; count++;
      }
      plan_change(entry,name,name_size,values,sizes,count);
    }
    line=end ? end+1 : NULL;
  }
  free(data);
}


static uint32_t get_id(exr_pdf_file *file,uint32_t dict,const char *key) {
  uint32_t id=EXR_PDF_NONE;
  OK(exr_pdf_resolve(file,exr_pdf_get(file,dict,key),&id,&error));
  return id;
}

static void dump_need(size_t index,const char *phase,exr_pdf_file *file) {
  uint32_t form=get_id(file,exr_pdf_root(file),"AcroForm"),need;
  const exr_pdf_value *value;
  int present=0,flag=0;
  need=form==EXR_PDF_NONE ? EXR_PDF_NONE : get_id(file,form,"NeedAppearances");
  value=need==EXR_PDF_NONE ? NULL : exr_pdf_value_at(file,need);
  if(value) { present=1; if(value->kind==EXR_PDF_BOOL) flag=value->u.integer ? 1 : 0; }
  fprintf(results,"S\t%zu\t%s\t%d\t%d\n",index,phase,present,flag);
}

static void dump_annots(size_t index,const char *phase,exr_pdf_file *file) {
  exr_pdf_page_info *pages=NULL; size_t count=0,i;
  OK(exr_pdf_pages(file,&pages,&count,&error));
  for(i=0;i<count;i++) {
    uint32_t annots=get_id(file,pages[i].object,"Annots"),at;
    const exr_pdf_value *array;
    if(annots==EXR_PDF_NONE) continue;
    array=exr_pdf_value_at(file,annots);
    if(!array || array->kind!=EXR_PDF_ARRAY) continue;
    for(at=array->first;at!=EXR_PDF_NONE;) {
      const exr_pdf_value *item=exr_pdf_value_at(file,at);
      uint32_t next=item->next,widget=EXR_PDF_NONE,ap,normal,state;
      size_t as_size=0;
      const unsigned char *as_bytes=NULL;
      OK(exr_pdf_resolve(file,at,&widget,&error));
      fprintf(results,"A\t%zu\t%s\t%zu",index,phase,i);
      {
        uint32_t rect=get_id(file,widget,"Rect"),corner; double bounds[4]={0,0,0,0}; size_t n=0;
        const exr_pdf_value *array2=rect==EXR_PDF_NONE ? NULL : exr_pdf_value_at(file,rect);
        if(array2 && array2->kind==EXR_PDF_ARRAY) {
          for(corner=array2->first;corner!=EXR_PDF_NONE && n<4;) {
            const exr_pdf_value *number=exr_pdf_value_at(file,corner);
            uint32_t next=number->next,resolved;
            OK(exr_pdf_resolve(file,corner,&resolved,&error));
            number=exr_pdf_value_at(file,resolved);
            if(number && (number->kind==EXR_PDF_INT || number->kind==EXR_PDF_REAL))
              bounds[n++]=number->kind==EXR_PDF_INT ? (double)number->u.integer : number->u.number;
            corner=next;
          }
        }
        fprintf(results,"\t%ld\t%ld\t%ld\t%ld\t",(long)llround(bounds[0]*1000.0),
          (long)llround(bounds[1]*1000.0),(long)llround(bounds[2]*1000.0),(long)llround(bounds[3]*1000.0));
      }
      state=get_id(file,widget,"AS");
      if(state!=EXR_PDF_NONE && exr_pdf_value_at(file,state) &&
         exr_pdf_value_at(file,state)->kind==EXR_PDF_NAME)
        as_bytes=exr_pdf_bytes(file,state,&as_size);
      emit_hex(as_bytes,as_size);
      ap=get_id(file,widget,"AP");
      normal=ap==EXR_PDF_NONE ? EXR_PDF_NONE : get_id(file,ap,"N");
      if(normal!=EXR_PDF_NONE && exr_pdf_value_at(file,normal) &&
         exr_pdf_value_at(file,normal)->kind==EXR_PDF_STREAM) {
        const unsigned char *bytes=NULL; size_t size=0;
        OK(exr_pdf_stream_data(file,normal,&bytes,&size,&error));
        fprintf(results,"\tstream\t%zu\t%016llx\t-\n",size,(unsigned long long)fnv(bytes,size));
      } else if(normal!=EXR_PDF_NONE && exr_pdf_value_at(file,normal) &&
                exr_pdf_value_at(file,normal)->kind==EXR_PDF_DICT) {
        uint32_t key=exr_pdf_value_at(file,normal)->first; int first=1;
        fprintf(results,"\tdict\t0\t0\t");
        while(key!=EXR_PDF_NONE) {
          const exr_pdf_value *entry=exr_pdf_value_at(file,key);
          uint32_t value=entry->next,after;
          const unsigned char *name=exr_pdf_bytes(file,key,&as_size);
          if(!first) fputc(',',results);
          emit_hex(name,as_size); first=0;
          after=value==EXR_PDF_NONE ? EXR_PDF_NONE : exr_pdf_value_at(file,value)->next;
          key=after;
        }
        fputc('\n',results);
      } else {
        fprintf(results,"\tnone\t0\t0\t-\n");
      }
      at=next;
    }
  }
  free(pages);
}

static void dump_fields(size_t index,const char *phase,const exr_pdf_form_field *fields,size_t count) {
  size_t i,j;
  for(i=0;i<count;i++) {
    const exr_pdf_form_field *field=&fields[i];
    fprintf(results,"FLD\t%zu\t%s\t",index,phase);
    emit_hex((const unsigned char *)field->name,strlen(field->name));
    fprintf(results,"\t%s\t%u\t%u\t%zu\t",kind_name(field->kind),field->flags,field->issues,field->max_length);
    for(j=0;j<field->value_count;j++) { if(j) fputc(',',results); emit_hex((const unsigned char *)field->values[j],strlen(field->values[j])); }
    if(!field->value_count) fputc('-',results);
    fputc('\t',results);
    for(j=0;j<field->default_value_count;j++) { if(j) fputc(',',results); emit_hex((const unsigned char *)field->default_values[j],strlen(field->default_values[j])); }
    if(!field->default_value_count) fputc('-',results);
    fputc('\t',results);
    for(j=0;j<field->option_count;j++) {
      if(j) fputc(',',results);
      emit_hex((const unsigned char *)field->options[j].value,strlen(field->options[j].value));
      fputc(':',results);
      emit_hex((const unsigned char *)field->options[j].label,strlen(field->options[j].label));
    }
    if(!field->option_count) fputc('-',results);
    fputc('\t',results);
    for(j=0;j<field->widget_count;j++) {
      const exr_pdf_field_widget *widget=&field->widgets[j];
      int k;
      if(j) fputc(';',results);
      if(widget->page==SIZE_MAX) fprintf(results,"-1"); else fprintf(results,"%zu",widget->page);
      for(k=0;k<4;k++) fprintf(results,",%ld",(long)llround(widget->bounds[k]*1000.0));
      fputc(',',results);
      if(widget->on_state) emit_hex((const unsigned char *)widget->on_state,strlen(widget->on_state));
      else fputc('-',results);
    }
    if(!field->widget_count) fputc('-',results);
    fputc('\n',results);
  }
}


static long ink_count(const void *data,size_t size,size_t page,const double bounds[4],int button) {
  exr_fixed_open_options options; exr_fixed_document *doc=NULL; exr_bitmap bitmap; long dark=0,x,y;
  double inset=button ? fmin(bounds[2]-bounds[0],bounds[3]-bounds[1])*0.25 : 2.5;
  long x0,x1,y0,y1;
  memset(&options,0,sizeof(options)); options.struct_size=sizeof(options);
  memset(&bitmap,0,sizeof(bitmap));
  if(exr_fixed_open_memory(EXR_PDF,data,size,&options,&doc,&error)!=EXR_OK) return -1;
  if(exr_fixed_render(doc,page,1,NULL,&bitmap,&error)!=EXR_OK) {
    exr_bitmap_free(&bitmap); exr_fixed_free(doc); return -1;
  }
  x0=(long)(bounds[0]+inset); x1=(long)(bounds[2]-inset);
  y0=(long)bitmap.height-(long)(bounds[3]-inset); y1=(long)bitmap.height-(long)(bounds[1]+inset);
  if(x0<0) x0=0;
  if(y0<0) y0=0;
  if(x1>(long)bitmap.width) x1=(long)bitmap.width;
  if(y1>(long)bitmap.height) y1=(long)bitmap.height;
  for(y=y0;y<y1;y++)
    for(x=x0;x<x1;x++)
      if(bitmap.pixels[(size_t)y*bitmap.stride+(size_t)x*bitmap.channels]<100) dark++;
  exr_bitmap_free(&bitmap); exr_fixed_free(doc); return dark;
}

static exr_pdf_form_change *build_changes(plan_entry *entry) {
  exr_pdf_form_change *changes; size_t i;
  if(!entry->count) return NULL;
  changes=malloc(entry->count*sizeof(*changes));
  if(!changes) { fprintf(stderr,"change allocation failed\n"); exit(1); }
  for(i=0;i<entry->count;i++) {
    changes[i].name=(const char *)entry->items[i].field;
    changes[i].values=(const char *const *)entry->items[i].values;
    changes[i].value_count=entry->items[i].value_count;
  }
  return changes;
}

static void output_name(const char *base,char *out,size_t size) {
  size_t n=strlen(base);
  if(n>4 && !strcmp(base+n-4,".pdf")) snprintf(out,size,"%.*s.edited.pdf",(int)(n-4),base);
  else snprintf(out,size,"%s.edited.pdf",base);
}

static void emit_write(size_t index,const char *op,exr_status status,size_t out_size,
  int prefix,int same,size_t changes,const char *out_name) {
  fprintf(results,"W\t%zu\t%s\t%s\t%d\t%zu\t%d\t%d\t%zu\t",index,op,status_name(status),status,
    out_size,prefix,same,changes);
  emit_hex((const unsigned char *)out_name,strlen(out_name));
  fputc('\t',results);
  emit_hex((const unsigned char *)error.message,strlen(error.message));
  fputc('\n',results);
}

static int cancel_flag(void *context) { (void)context; return cancel_state; }
static void progress_cancel(void *context,exr_stage stage,uint64_t done,uint64_t total) {
  (void)context;
  if(stage==EXR_STAGE_EXPORT && done==total) cancel_state=1;
}
static void progress_shape(void *context,exr_stage stage,uint64_t done,uint64_t total) {
  (void)context; (void)done; (void)total;
  if(stage==EXR_STAGE_SHAPE) cancel_state=1;
}

static const exr_pdf_form_field *find_field(const exr_pdf_form_field *fields,size_t count,const char *name) {
  size_t i;
  for(i=0;i<count;i++) if(!strcmp(fields[i].name,name)) return &fields[i];
  return NULL;
}

static void run_entry(size_t index,const char *corpus,const char *outdir,
  exr_font *text_font,exr_font *bitmap_font) {
  plan_entry *entry=&plan[index];
  char path[1024],target[1024];
  size_t size=0,out_size=0,i;
  unsigned char *input,*pristine;
  void *out=NULL;
  exr_pdf_form_field *fields=NULL;
  size_t count=0;
  exr_pdf_form_write_options options=exr_pdf_form_write_defaults();
  exr_pdf_form_change *changes=build_changes(entry);
  exr_status status;
  int prefix=0,same=0;
  snprintf(path,sizeof(path),"%s/%s",corpus,entry->base);
  input=read_file(path,&size);
  if(!input) { fprintf(stderr,"cannot read %s\n",path); exit(1); }
  pristine=malloc(size ? size : 1);
  if(!pristine) exit(1);
  memcpy(pristine,input,size);
  fprintf(results,"F\t%zu\t%s\t",index,entry->id);
  emit_hex((const unsigned char *)entry->base,strlen(entry->base));
  fprintf(results,"\t%zu\t%016llx\n",size,(unsigned long long)fnv(input,size));
  { exr_pdf_file *file=NULL;
    if(exr_pdf_open(input,size,&file,&error)==EXR_OK) {
      dump_need(index,"in",file); dump_annots(index,"in",file); exr_pdf_close(file);
    }
  }
  { exr_pdf_file *file=NULL;
    if(exr_pdf_open(input,size,&file,&error)==EXR_OK) {
      exr_pdf_revision_info revision;
      exr_pdf_revision(file,&revision);
      fprintf(results,"REV\t%zu\t%zu\t%zu\n",index,revision.size,revision.startxref);
      exr_pdf_close(file);
    }
  }
  status=exr_pdf_form_read(input,size,NULL,&fields,&count,&error);
  fprintf(results,"R\t%zu\tin\t%s\t%d\t%zu\t0\n",index,status_name(status),status,
    status==EXR_OK ? count : 0);
  if(status==EXR_OK && count) dump_fields(index,"in",fields,count);
  output_name(entry->base,target,sizeof(target));
  if(entry->font==1) options.font=text_font;
  else if(entry->font==2) options.font=bitmap_font;
  if(!strcmp(entry->op,"write") || !strcmp(entry->op,"write-empty")) {
    size_t change_count=(entry->count && strcmp(entry->op,"write-empty")) ? entry->count : 0;
    status=exr_pdf_form_write(input,size,changes,change_count,&options,&out,&out_size,&error);
    prefix=out && out_size>=size && !memcmp(out,input,size);
    same=!memcmp(input,pristine,size);
    emit_write(index,entry->op,status,out_size,prefix,same,change_count,target);
    if(status==EXR_OK) {
      char full[1200];
      snprintf(full,sizeof(full),"%s/%s",outdir,target);
      if(!write_file(full,out,out_size)) { fprintf(stderr,"cannot write %s\n",full); exit(1); }
      { exr_pdf_form_field *again=NULL; size_t again_count=0; exr_status reopened;
        exr_pdf_file *file=NULL;
        reopened=exr_pdf_form_read(out,out_size,NULL,&again,&again_count,&error);
        fprintf(results,"RO\t%zu\t%s\t%d\t%zu\n",index,status_name(reopened),reopened,
          reopened==EXR_OK ? again_count : 0);
        if(exr_pdf_open(out,out_size,&file,&error)==EXR_OK) {
          dump_need(index,"out",file); dump_annots(index,"out",file); exr_pdf_close(file);
        }
        if(reopened==EXR_OK && again_count) {
          dump_fields(index,"out",again,again_count);
          for(i=0;i<entry->count;i++) {
            const exr_pdf_form_field *field=find_field(fields,count,(const char *)entry->items[i].field);
            size_t w;
            if(!field) continue;
            for(w=0;w<field->widget_count;w++) {
              const exr_pdf_field_widget *widget=&field->widgets[w];
              long dark;
              if(widget->page==SIZE_MAX) continue;
              dark=ink_count(out,out_size,widget->page,widget->bounds,
                field->kind==EXR_PDF_FIELD_CHECKBOX || field->kind==EXR_PDF_FIELD_RADIO);
              fprintf(results,"INK\t%zu\tout\t",index);
              emit_hex(entry->items[i].field,entry->items[i].field_size);
              fprintf(results,"\t%zu\t%zu\t%ld\t",w,widget->page,dark);
              emit_hex((const unsigned char *)error.message,strlen(error.message));
              fputc('\n',results);
            }
          }
        }
        exr_pdf_form_free(again,again_count);
      }
      exr_free(out); out=NULL;
    }
  } else if(!strcmp(entry->op,"reject")) {
    exr_status first,second,noop;
    size_t noop_size=0; void *noop_out=NULL;
    first=exr_pdf_form_write(input,size,changes,entry->count,&options,&out,&out_size,&error);
    same=!memcmp(input,pristine,size);
    emit_write(index,entry->op,first,out_size,0,same,entry->count,target);
    exr_free(out); out=NULL; out_size=0;
    second=exr_pdf_form_write(input,size,changes,entry->count,&options,&out,&out_size,&error);
    exr_free(out); out=NULL; out_size=0;
    noop=exr_pdf_form_write(input,size,NULL,0,&options,&noop_out,&noop_size,&error);
    fprintf(results,"J\t%zu\t%s\t%d\t%s\t%d\t%s\t%d\t%zu\t%d\n",index,
      status_name(first),first,status_name(second),second,status_name(noop),noop,noop_size,
      noop==EXR_OK && noop_out && noop_size==size && !memcmp(noop_out,input,size));
    exr_free(noop_out);
  } else if(!strcmp(entry->op,"cancel-entry") || !strcmp(entry->op,"cancel-final") ||
            !strcmp(entry->op,"cancel-shape")) {
    if(!strcmp(entry->op,"cancel-entry")) { cancel_state=1; options.control.cancelled=cancel_flag; }
    else if(!strcmp(entry->op,"cancel-final")) { cancel_state=0; options.control.cancelled=cancel_flag; options.control.progress=progress_cancel; }
    else { cancel_state=0; options.control.cancelled=cancel_flag; options.control.progress=progress_shape; }
    options.control.context=NULL;
    status=exr_pdf_form_write(input,size,changes,entry->count,&options,&out,&out_size,&error);
    same=!memcmp(input,pristine,size);
    emit_write(index,entry->op,status,out_size,0,same,entry->count,target);
    exr_free(out); out=NULL;
    cancel_state=0;
  } else if(!strcmp(entry->op,"read") || !strcmp(entry->op,"read-fail")) {
    /* A pure read: the R record above is the whole measurement. */
  } else {
    fprintf(stderr,"unknown op %s\n",entry->op); exit(1);
  }
  same=!memcmp(input,pristine,size);
  if(!same) { fprintf(stderr,"input bytes changed for %s\n",entry->base); exit(1); }
  exr_pdf_form_free(fields,count);
  free(changes); free(pristine); free(input);
}


int main(int argc,char **argv) {
  exr_font *text_font=NULL,*bitmap_font=NULL;
  size_t i;
  char plan_path[1024];
  if(argc<6) {
    fprintf(stderr,"usage: %s corpus-dir out-dir results.tsv fallback-font bitmap-font [platform]\n",argv[0]);
    return 2;
  }
  snprintf(plan_path,sizeof(plan_path),"%s/plan.tsv",argv[1]);
  parse_plan(plan_path);
  results=fopen(argv[3],"wb");
  if(!results) { fprintf(stderr,"cannot open results\n"); return 1; }
  OK(exr_font_open(argv[4],&text_font,&error));
  OK(exr_font_open(argv[5],&bitmap_font,&error));
  fprintf(results,"META\tplatform\t%s\n",argc>6 ? argv[6] : "unknown");
  fprintf(results,"META\tfiles\t%zu\n",plan_count);
  fprintf(results,"META\tfont_text\t%s\n",argv[4]);
  fprintf(results,"META\tfont_bitmap\t%s\n",argv[5]);
  for(i=0;i<plan_count;i++) run_entry(i,argv[1],argv[2],text_font,bitmap_font);
  fprintf(results,"META\tchecks\t%u\n",checks);
  fclose(results);
  for(i=0;i<plan_count;i++) {
    size_t j,k;
    for(j=0;j<plan[i].count;j++) {
      for(k=0;k<plan[i].items[j].value_count;k++) free(plan[i].items[j].values[k]);
      free(plan[i].items[j].values); free(plan[i].items[j].value_sizes);
      free(plan[i].items[j].field);
    }
    free(plan[i].items);
  }
  free(plan);

  exr_font_free(text_font); exr_font_free(bitmap_font);
  printf("AcroForm corpus: %zu documents, %u harness checks\n",plan_count,checks);
  return 0;
}

