/* SPDX-License-Identifier: GPL-3.0-only */
#include "../src/pdf_internal.h"
#include <float.h>
#include <locale.h>
static exr_error error; static unsigned checks;
static int cancelled(void *context);
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *read_fixture(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *file; long length; unsigned char *data;
  snprintf(path,sizeof(path),"%s/%s",dir,name); file=fopen(path,"rb"); CHECK(file);
  CHECK(!fseek(file,0,SEEK_END)); length=ftell(file); CHECK(length>0); rewind(file);
  *size=(size_t)length; data=malloc(*size); CHECK(data && fread(data,1,*size,file)==*size); fclose(file); return data;
}
static uint32_t get(exr_pdf_file *file,uint32_t dict,const char *key) {
  uint32_t out; OK(exr_pdf_resolve(file,exr_pdf_get(file,dict,key),&out,&error)); CHECK(out!=EXR_PDF_NONE); return out;
}
static void bytes(exr_pdf_file *file,uint32_t id,const void *expected,size_t length) {
  size_t size; const unsigned char *data=exr_pdf_bytes(file,id,&size); CHECK(data && size==length && !memcmp(data,expected,length));
}
static void basic(const char *dir,const char *name) {
  size_t size,n,again; unsigned char *data=read_fixture(dir,name,&size); const unsigned char *stream,*same;
  exr_pdf_file *file=NULL; uint32_t root,dict,value,array; const exr_pdf_value *v;
  OK(exr_pdf_open(data,size,&file,&error)); root=exr_pdf_root(file); CHECK(root!=EXR_PDF_NONE);
  { exr_pdf_revision_info revision; exr_buffer out={0}; uint32_t object,generation;
    exr_pdf_revision(file,&revision); CHECK(revision.size>0 && revision.startxref<size);
    v=exr_pdf_value_at(file,revision.root); CHECK(v && v->kind==EXR_PDF_REF);
    OK(exr_pdf_object_identity(file,root,&object,&generation,&error));
    CHECK(object==v->u.ref.object && generation==v->u.ref.generation && object<revision.size);
    OK(exr_pdf_serialize(file,revision.root,NULL,0,&out,NULL,&error));
    CHECK(strstr(out.data," R") && !strstr(out.data,"Catalog")); free(out.data);
    CHECK(exr_pdf_object_identity(file,EXR_PDF_NONE,&object,&generation,&error)==EXR_ARGUMENT && object==EXR_PDF_NONE);
  }
  dict=get(file,root,"Data"); CHECK(exr_pdf_value_at(file,dict)->kind==EXR_PDF_DICT);
  { exr_buffer out={0}; const char *skip[]={"Duplicate"}; size_t saved,stop=1; exr_control control={0};
    OK(exr_pdf_serialize(file,dict,skip,1,&out,NULL,&error)); saved=out.size;
    CHECK(!strstr(out.data,"/Duplicate ") && strstr(out.data,"/EscapedName /A#20B") && strstr(out.data,"<FEFF4E8C>"));
    CHECK(strstr(out.data,"9223372036854775807") && strstr(out.data,"-9223372036854775808") && strstr(out.data," R"));
    value=get(file,root,"Raw"); CHECK(exr_pdf_serialize(file,value,NULL,0,&out,NULL,&error)==EXR_FORMAT);
    CHECK(out.size==saved && out.data[saved]==0);
    control.context=&stop; control.cancelled=cancelled;
    CHECK(exr_pdf_serialize(file,dict,NULL,0,&out,&control,&error)==EXR_CANCELLED && out.size==saved);
    CHECK(exr_pdf_serialize(file,dict,NULL,1,&out,NULL,&error)==EXR_ARGUMENT && out.size==saved);
    free(out.data);
  }
  bytes(file,get(file,dict,"EscapedName"),"A B",3);
  bytes(file,get(file,dict,"Text"),"a(b)A\nlinecontinued\nend",sizeof("a(b)A\nlinecontinued\nend")-1);
  bytes(file,get(file,dict,"Nested"),"nested (inner)",14);
  bytes(file,get(file,dict,"Hex"),"AB@",3); bytes(file,get(file,dict,"UTF16"),"\xfe\xff\x4e\x8c",4);
  value=get(file,dict,"Duplicate"); CHECK(exr_pdf_value_at(file,value)->u.integer==2);
  value=get(file,dict,"I64"); CHECK(exr_pdf_value_at(file,value)->u.integer==INT64_MAX);
  value=get(file,dict,"Min"); CHECK(exr_pdf_value_at(file,value)->u.integer==INT64_MIN);
  value=get(file,dict,"Null"); CHECK(exr_pdf_value_at(file,value)->kind==EXR_PDF_NULL);
  value=get(file,dict,"Bool"); CHECK(exr_pdf_value_at(file,value)->kind==EXR_PDF_BOOL && exr_pdf_value_at(file,value)->u.number==1);
  array=get(file,dict,"Values"); v=exr_pdf_value_at(file,array); CHECK(v->kind==EXR_PDF_ARRAY);
  value=v->first; v=exr_pdf_value_at(file,value); CHECK(v->kind==EXR_PDF_INT && v->u.integer==-2);
  value=v->next; v=exr_pdf_value_at(file,value); CHECK(v->kind==EXR_PDF_REAL && v->u.number==0.5);
  value=v->next; v=exr_pdf_value_at(file,value); CHECK(v->kind==EXR_PDF_REAL && v->u.number==1.25);
  value=v->next; v=exr_pdf_value_at(file,value); CHECK(v->kind==EXR_PDF_INT && !v->u.integer);
  value=v->next; OK(exr_pdf_resolve(file,value,&value,&error)); CHECK(value==dict);
  OK(exr_pdf_resolve(file,exr_pdf_get(file,root,"Unknown"),&value,&error)); CHECK(value==EXR_PDF_NONE);
  OK(exr_pdf_resolve(file,exr_pdf_get(file,root,"WrongGeneration"),&value,&error)); CHECK(value==EXR_PDF_NONE);
  value=get(file,root,"Raw"); OK(exr_pdf_stream_data(file,value,&stream,&n,&error));
  CHECK(n==sizeof("Raw\0\nendstream-not-a-token\n")-1 && !memcmp(stream,"Raw\0\nendstream-not-a-token\n",n));
  OK(exr_pdf_stream_data(file,value,&same,&again,&error)); CHECK(same==stream && again==n);
  value=get(file,root,"Flate"); OK(exr_pdf_stream_data(file,value,&stream,&n,&error));
  CHECK(n==strlen("BT /F1 12 Tf (Hello native PDF.) Tj ET\n") && !memcmp(stream,"BT /F1 12 Tf (Hello native PDF.) Tj ET\n",n));
  OK(exr_pdf_stream_data(file,value,&same,&again,&error)); CHECK(same==stream && again==n);
  CHECK(exr_pdf_resolve(file,exr_pdf_get(file,root,"Cycle"),&value,&error)==EXR_FORMAT);
  exr_pdf_close(file); free(data);
}
static void incremental(const char *dir,const char *name) {
  unsigned char *data; size_t size; exr_pdf_file *file=NULL; uint32_t root,id;
  data=read_fixture(dir,name,&size); OK(exr_pdf_open(data,size,&file,&error)); root=exr_pdf_root(file);
  bytes(file,get(file,root,"Revision"),"Updated",7); bytes(file,get(file,root,"Extra"),"Extra object",12);
  OK(exr_pdf_resolve(file,exr_pdf_get(file,root,"Deleted"),&id,&error)); CHECK(id==EXR_PDF_NONE);
  id=get(file,root,"Pages"); CHECK(exr_pdf_value_at(file,id)->kind==EXR_PDF_DICT);
  exr_pdf_close(file); free(data);
}
static void bad_open(const char *dir,const char *name,exr_status expected) {
  unsigned char *data; size_t size; exr_pdf_file *file=(exr_pdf_file *)(uintptr_t)1; exr_status status;
  data=read_fixture(dir,name,&size); status=exr_pdf_open(data,size,&file,&error);
  if(status!=expected) fprintf(stderr,"fixture %s returned %d\n",name,status);
  CHECK(status==expected && !file && error.code==expected && error.message[0]); free(data);
}
static void bad_stream(const char *dir,const char *name,exr_status expected) {
  unsigned char *data; size_t size,n; exr_pdf_file *file=NULL; uint32_t id; const unsigned char *stream=(const unsigned char *)(uintptr_t)1;
  data=read_fixture(dir,name,&size); OK(exr_pdf_open(data,size,&file,&error)); id=exr_pdf_get(file,exr_pdf_root(file),"Flate");
  CHECK(exr_pdf_stream_data(file,id,&stream,&n,&error)==expected && !stream && !n && error.code==expected);
  exr_pdf_close(file); free(data);
}
static void filter_case(const char *dir,const char *name,const void *expected,size_t length) {
  char path[256]; unsigned char *data; size_t size,n,again; const unsigned char *decoded,*same;
  exr_pdf_file *file=NULL; uint32_t id;
  snprintf(path,sizeof(path),"pdf-filter-%s.pdf",name); data=read_fixture(dir,path,&size);
  OK(exr_pdf_open(data,size,&file,&error)); id=exr_pdf_get(file,exr_pdf_root(file),"Flate");
  if(exr_pdf_stream_data(file,id,&decoded,&n,&error)!=EXR_OK) { fprintf(stderr,"filter %s\n",name); CHECK(0); }
  CHECK(n==length && (!n || !memcmp(decoded,expected,n)));
  OK(exr_pdf_stream_data(file,id,&same,&again,&error)); CHECK(same==decoded && again==n);
  exr_pdf_close(file); free(data);
}
static void filter_cases(const char *dir) {
  const char *plain[]={"lzw","hex","a85","runlength","chain","chain-hex","empty-array","tiff8"};
  const char *bad[]={"lzw-bad-code","lzw-first-reference","lzw-no-clear","lzw-no-end","lzw-tail","lzw-bad-early","png-short","png-bad-tag","tiff-short","bad-bits","bad-colors","bad-columns","bad-predictor","bad-hex","hex-tail","hex-end","a85-overflow","a85-z","a85-one","a85-tail","a85-end","rl-short","rl-repeat","rl-end","rl-tail","params-short","params-shape","filter-value","filter-depth"};
  const char text[]="BT /F1 12 Tf (Hello native PDF.) Tj ET\n"; size_t i; char repeated[sizeof(text)*5],runs[128];
  for(i=0;i<sizeof(plain)/sizeof(*plain);i++) filter_case(dir,plain[i],text,sizeof(text)-1);
  filter_case(dir,"hex-odd","A@",2); filter_case(dir,"empty-hex","",0);
  for(i=1;i<=4;i++) { char name[64]; snprintf(name,sizeof(name),"a85-tail%u",(unsigned)i); filter_case(dir,name,"\0\0\0\0",i); }
  memset(runs,'X',sizeof(runs)); filter_case(dir,"repeat",runs,sizeof(runs));
  for(i=0;i<5;i++) memcpy(repeated+i*(sizeof(text)-1),text,sizeof(text)-1);
  filter_case(dir,"lzw-png",repeated,5*(sizeof(text)-1)); filter_case(dir,"lzw-empty","",0);
  { char *large=malloc(20000); unsigned early; CHECK(large); memset(large,'A',1000); filter_case(dir,"lzw-special",large,1000);
    for(early=0;early<=1;early++) { char name[64];
      for(i=0;i<10000;i++) large[i]=(char)(i%256); snprintf(name,sizeof(name),"lzw-wide%u",early); filter_case(dir,name,large,10000);
      for(i=0;i<20000;i++) large[i]=(char)(i%251); snprintf(name,sizeof(name),"lzw-dictionary%u",early); filter_case(dir,name,large,20000);
      for(i=0;i<2000;i++) large[i]=(char)((i%1000)%256); snprintf(name,sizeof(name),"lzw-reset%u",early); filter_case(dir,name,large,2000);
    } free(large);
  }
  filter_case(dir,"png",repeated,5*(sizeof(text)-1)); filter_case(dir,"png-chain",repeated,5*(sizeof(text)-1));
  filter_case(dir,"tiff1","\xb4",1); filter_case(dir,"tiff2","\x4d\x10",2);
  filter_case(dir,"tiff4","\x10\xf1\x01",3); filter_case(dir,"tiff16","\0\1\0\0\xff\xff\0\1\0\0\0\1",12);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) { char name[256]; snprintf(name,sizeof(name),"pdf-filter-%s.pdf",bad[i]); bad_stream(dir,name,EXR_FORMAT); }
}
static exr_status inspect_operation(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *e) {
  static const char *names[]={"q","cm","BT","Tf","TJ","DP","ET","Q"};
  size_t *step=context; const exr_pdf_value *v; uint32_t at;
  (void)e; CHECK(*step<8 && !strcmp(name,names[*step]));
  if(*step==1) CHECK(count==6 && exr_pdf_value_at(arena,values[4])->u.integer==10 && exr_pdf_value_at(arena,values[5])->u.integer==20);
  else if(*step==3) { CHECK(count==2); bytes(arena,values[0],"F1",2); CHECK(exr_pdf_value_at(arena,values[1])->u.integer==12); }
  else if(*step==4) {
    CHECK(count==1); v=exr_pdf_value_at(arena,values[0]); CHECK(v->kind==EXR_PDF_ARRAY); at=v->first;
    bytes(arena,at,"A+",2); at=exr_pdf_value_at(arena,at)->next; CHECK(exr_pdf_value_at(arena,at)->u.integer==-120);
    at=exr_pdf_value_at(arena,at)->next; bytes(arena,at,"B",1); CHECK(exr_pdf_value_at(arena,at)->next==EXR_PDF_NONE);
  } else if(*step==5) {
    CHECK(count==5 && exr_pdf_value_at(arena,values[0])->kind==EXR_PDF_BOOL && exr_pdf_value_at(arena,values[1])->kind==EXR_PDF_BOOL);
    CHECK(exr_pdf_value_at(arena,values[2])->kind==EXR_PDF_NULL); bytes(arena,values[3],"tag",3);
    CHECK(exr_pdf_value_at(arena,exr_pdf_get(arena,values[4],"K"))->kind==EXR_PDF_ARRAY);
  } else CHECK(!count);
  (*step)++; return EXR_OK;
}
static exr_status count_operation(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *e) {
  size_t *operations=context; (void)e;
  if(!strcmp(name,"Tj")) { CHECK(count==1 && values[0]==0); bytes(arena,values[0],"abc",3); }
  (*operations)++; return EXR_OK;
}
static exr_status stop_operation(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *e) {
  (void)context; (void)arena; (void)name; (void)values; (void)count; (void)e; return EXR_CANCELLED;
}
static int cancelled(void *context) { return *(size_t *)context>0; }
static exr_status serialize_operand(void *context,exr_pdf_file *arena,const char *name,const uint32_t *values,size_t count,exr_error *e) {
  (void)name; CHECK(count==1); return exr_pdf_serialize(arena,values[0],NULL,0,context,NULL,e);
}
static void serialization(void) {
  const char input[]="<< /Bin <00FF2380> /Name /A#00#23#2F /Values [null true false -9223372036854775808 9223372036854775807 0.00000000125 1000000000000000000000000000000000000000000000000000000000000.0] /Nested << /Annots /Keep >> >> Check";
  const double reals[]={0.0,-0.0,1.25,1e-9,1e60,1e-300,DBL_MIN,DBL_MAX};
  const char *locales[]={"de_DE.UTF-8","de-DE","German_Germany.1252","fr_FR.UTF-8"};
  exr_buffer first={0},second={0},real={0}; char *saved; size_t size,i;
  OK(exr_pdf_content_ops(input,sizeof(input)-1,serialize_operand,&first,NULL,&error)); size=first.size;
  CHECK(strstr(first.data,"/Bin <00FF2380>") && strstr(first.data,"/Name /A#00#23#2F") && strstr(first.data,"/Annots /Keep"));
  CHECK(exr_append(&first," Check",6));
  OK(exr_pdf_content_ops(first.data,first.size,serialize_operand,&second,NULL,&error));
  CHECK(size==second.size && !memcmp(first.data,second.data,size));
  for(i=0;i<sizeof(reals)/sizeof(*reals);i++) {
    real.size=0; OK(exr_pdf_real(&real,reals[i],&error)); CHECK(strchr(real.data,'.') && !strchr(real.data,'e') && !strchr(real.data,'E'));
    CHECK(strtod(real.data,NULL)==reals[i]);
  }
  saved=exr_copy(setlocale(LC_NUMERIC,NULL),strlen(setlocale(LC_NUMERIC,NULL))); CHECK(saved);
  for(i=0;i<sizeof(locales)/sizeof(*locales);i++) if(setlocale(LC_NUMERIC,locales[i])) {
    real.size=0; OK(exr_pdf_real(&real,1.25,&error)); CHECK(!strcmp(real.data,"1.25")); break;
  }
  CHECK(setlocale(LC_NUMERIC,saved)); free(saved);
  CHECK(exr_pdf_real(&real,INFINITY,&error)==EXR_ARGUMENT && exr_pdf_real(&real,NAN,&error)==EXR_ARGUMENT);
  free(first.data); free(second.data); free(real.data);
}
static void content_operations(void) {
  const char sample[]="% operators\nq 1 0 0 1 10 20 cm BT /F#31 12 Tf [(A\\053) -120 <42>] TJ true false null /tag << /K [1 2] >> DP ET Q";
  const char *bad[]={"1","1 0 R Do","[1 0 R] TJ","<< /Key 1 0 R >> DP","(open Tj","<GG> Tj","[1 2 TJ",">","/Name << DP","BI /W 1 ID x EI"};
  size_t i,step=0; char large[90000],operands[256]; exr_control control={0};
  OK(exr_pdf_content_ops(sample,sizeof(sample)-1,inspect_operation,&step,NULL,&error)); CHECK(step==8);
  step=0; for(i=0;i<sizeof(large);i+=9) memcpy(large+i,"(abc) Tj ",9);
  OK(exr_pdf_content_ops(large,sizeof(large),count_operation,&step,NULL,&error)); CHECK(step==10000);
  step=0; control.context=&step; control.cancelled=cancelled;
  CHECK(exr_pdf_content_ops(large,sizeof(large),count_operation,&step,&control,&error)==EXR_CANCELLED && step==256);
  CHECK(exr_pdf_content_ops(sample,sizeof(sample)-1,stop_operation,NULL,NULL,&error)==EXR_CANCELLED && error.code==EXR_CANCELLED);
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) CHECK(exr_pdf_content_ops(bad[i],strlen(bad[i]),count_operation,&step,NULL,&error)==EXR_FORMAT);
  for(i=0;i<65;i++) { operands[2*i]='1'; operands[2*i+1]=' '; }
  CHECK(exr_pdf_content_ops(operands,130,count_operation,&step,NULL,&error)==EXR_LIMIT);
  memset(operands,'x',128); CHECK(exr_pdf_content_ops(operands,128,count_operation,&step,NULL,&error)==EXR_LIMIT);
  step=0; OK(exr_pdf_content_ops(NULL,0,count_operation,&step,NULL,&error)); CHECK(!step);
  CHECK(exr_pdf_content_ops(NULL,1,count_operation,&step,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_pdf_content_ops(sample,sizeof(sample)-1,NULL,NULL,NULL,&error)==EXR_ARGUMENT);
}
int main(int argc,char **argv) {
  const char *bad[]={"object-header-duplicate","object-header-offset","object-header-order","object-header-tail","object-body","xref-indirect","xref-empty-index","xref-size","xref-nested-hybrid","xref-width","xref-overlap","xref-odd-index","xref-generation","object-stream-number","object-stream-index","object-stream-self","object-stream-missing","prev-cycle","prev-offset","encrypted","hybrid","xref-offset","header","eof","startxref","root-type","root-direct","size","token","root-reference","generation","string","key","hex"};
  const char *streams[]={"invalid-length","cycle-length","bad-flate","unsupported-filter","bad-parameters","unsupported-predictor","trailing"}; size_t i;
  CHECK(argc==2); content_operations(); serialization(); filter_cases(argv[1]); basic(argv[1],"pdf-objects.pdf"); basic(argv[1],"pdf-objects-predictor-one.pdf"); basic(argv[1],"pdf-stream-whitespace.pdf");
  basic(argv[1],"pdf-stream-after-classic.pdf"); incremental(argv[1],"pdf-classic-after-stream.pdf");
  basic(argv[1],"pdf-xref-predictor.pdf"); basic(argv[1],"pdf-hybrid-predictor.pdf"); basic(argv[1],"pdf-xref-stream.pdf"); basic(argv[1],"pdf-object-stream.pdf"); basic(argv[1],"pdf-hybrid.pdf");
  basic(argv[1],"pdf-xref-index.pdf"); basic(argv[1],"pdf-xref-wide.pdf"); basic(argv[1],"pdf-xref-default-type.pdf");
  incremental(argv[1],"pdf-incremental.pdf"); incremental(argv[1],"pdf-incremental-inherit.pdf");
  for(i=0;i<sizeof(bad)/sizeof(*bad);i++) { char name[256]; snprintf(name,sizeof(name),"pdf-bad-%s.pdf",bad[i]); bad_open(argv[1],name,EXR_FORMAT); }
  bad_open(argv[1],"pdf-bad-nesting.pdf",EXR_LIMIT); bad_open(argv[1],"pdf-bad-string-depth.pdf",EXR_LIMIT);
  bad_open(argv[1],"pdf-bad-integer.pdf",EXR_LIMIT);
  for(i=0;i<sizeof(streams)/sizeof(*streams);i++) { char name[256]; snprintf(name,sizeof(name),"pdf-stream-%s.pdf",streams[i]); bad_stream(argv[1],name,EXR_FORMAT); }
  bad_stream(argv[1],"pdf-stream-expansion.pdf",EXR_LIMIT);
  { size_t size; unsigned char *data=read_fixture(argv[1],"pdf-objects.pdf",&size);
    for(i=1;i+6<size;i++) { exr_pdf_file *file=NULL; CHECK(exr_pdf_open(data,i,&file,&error)!=EXR_OK && !file); }
    free(data);
  }
  printf("%u native PDF object checks passed\n",checks); return 0;
}
