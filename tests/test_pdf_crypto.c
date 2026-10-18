/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static unsigned char *load(const char *dir,const char *name,size_t *size) {
  char path[4096]; FILE *f; long n; unsigned char *bytes;
  snprintf(path,sizeof(path),"%s/%s.pdf",dir,name); f=fopen(path,"rb"); CHECK(f);
  CHECK(!fseek(f,0,SEEK_END)); n=ftell(f); CHECK(n>0); rewind(f); *size=(size_t)n;
  bytes=malloc(*size); CHECK(bytes && fread(bytes,1,*size,f)==*size); fclose(f); return bytes;
}
static int cancel(void *context) { return *(int *)context; }
static int cancel_later(void *context) { unsigned *count=context; return ++*count>=12; }
static exr_status open_bytes(const void *bytes,size_t size,const char *password,exr_pdf_security_info *info,exr_fixed_document **out) {
  exr_fixed_open_options options={0}; options.struct_size=sizeof(options);
  options.pdf_password=password; options.pdf_password_size=password ? strlen(password) : 0; options.pdf_security=info;
  return exr_fixed_open_memory(EXR_PDF,bytes,size,&options,out,&error);
}
#ifdef EXR_ENABLE_PDF_CRYPTO
static void usable(exr_fixed_document *d) {
  exr_fixed_text *t=NULL; size_t n,count,i,green=0; const char *text; exr_bitmap bitmap={0};
  exr_metadata_entry *entries=NULL; exr_page_annotation *notes=NULL;
  CHECK(exr_fixed_pages(d,&count) && count==2);
  OK(exr_fixed_load_text(d,0,NULL,&t,&error)); text=exr_fixed_text_string(t,&n); CHECK(n==11 && !memcmp(text,"Secret text",n)); exr_fixed_text_free(t);
  OK(exr_fixed_load_metadata(d,NULL,&entries,&count,&error)); CHECK(count==1 && !strcmp(entries[0].value,"Private title")); exr_metadata_free(entries,count);
  OK(exr_fixed_load_annotations(d,0,NULL,&notes,&count,&error)); CHECK(count==1 && !strcmp(notes[0].kind,"Text"));
  for(i=0;i<notes[0].property_count;i++) if(!strcmp(notes[0].properties[i].value,"Private note")) break;
  CHECK(i<notes[0].property_count); exr_page_annotations_free(notes,count);
  OK(exr_fixed_render(d,0,1,NULL,&bitmap,&error));
  for(i=0;i<bitmap.width*bitmap.height;i++) if(bitmap.pixels[i*4]==0 && bitmap.pixels[i*4+1]==255 && bitmap.pixels[i*4+2]==0) green++;
  CHECK(green>=80); exr_bitmap_free(&bitmap);
  /* A failed lazy page drops the parser. Page 0 must reopen with a derived key,
     after the caller's password/input buffers have already gone away. */
  CHECK(exr_fixed_load_text(d,1,NULL,&t,&error)==EXR_FORMAT && !t);
  OK(exr_fixed_load_text(d,0,NULL,&t,&error)); text=exr_fixed_text_string(t,&n); CHECK(n==11 && !memcmp(text,"Secret text",n)); exr_fixed_text_free(t);
}
static void standard(const char *dir,const char *name,unsigned revision,const char *password,int owner) {
  size_t size; unsigned char *bytes=load(dir,name,&size); exr_fixed_document *d=NULL;
  exr_pdf_security_info info={0}; char pw[512]; info.struct_size=sizeof(info);
  if(password) { CHECK(strlen(password)<sizeof(pw)); strcpy(pw,password); }
  { exr_status status=open_bytes(bytes,size,password ? pw : NULL,&info,&d);
    if(status!=EXR_OK) fprintf(stderr,"fixture %s role %s failed\n",name,owner ? "owner" : "user");
    CHECK(status==EXR_OK);
  }
  free(bytes); memset(pw,0xa5,sizeof(pw));
  CHECK(info.encrypted && info.revision==revision && info.owner_authenticated==(unsigned)owner);
  CHECK(info.key_bits==(revision==2 ? 40u : revision<=4 ? 128u : 256u));
  CHECK(info.permissions==0xfffff0c4u); CHECK(info.metadata_encrypted==!strstr(name,"metadata-clear"));
  usable(d); exr_fixed_free(d);
}
static void wrong(const char *dir,const char *name,const char *password,exr_status expected) {
  size_t size; unsigned char *bytes=load(dir,name,&size); exr_fixed_document *d=(exr_fixed_document *)(uintptr_t)1;
  exr_pdf_security_info info={0}; info.struct_size=sizeof(info); info.revision=0xabcdefu;
  CHECK(open_bytes(bytes,size,password,&info,&d)==expected && !d && error.code==expected); CHECK(info.revision==0xabcdefu);
  free(bytes);
}
static void contracts(const char *dir) {
  exr_fixed_open_options options={0}; exr_fixed_document *d=NULL; exr_pdf_security_info info={0};
  size_t n,size; unsigned char *bytes=load(dir,"r6",&size); exr_control control={0}; int stop=1;
  options.struct_size=sizeof(options); options.pdf_password="reader"; options.pdf_password_size=6;
  options.control.cancelled=cancel; options.control.context=&stop;
  CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)==EXR_CANCELLED && !d);
  options.control=control; options.pdf_password=NULL;
  CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)==EXR_ARGUMENT && !d);
  options.pdf_password="x"; options.pdf_password_size=1025;
  CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)==EXR_LIMIT && !d);
  options.pdf_password="reader"; options.pdf_password_size=6; options.pdf_security=&info;
  CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)==EXR_ARGUMENT && !d);
  options.pdf_security=NULL;
  { unsigned polls=0;
    options.control.cancelled=cancel_later; options.control.context=&polls;
    CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)==EXR_CANCELLED && !d && polls==12);
    options.control=control;
  }
  for(n=offsetof(exr_fixed_open_options,pdf_password)+1;n<sizeof(options);n++) {
    if(n==offsetof(exr_fixed_open_options,pdf_password_size) || n==offsetof(exr_fixed_open_options,pdf_security)) continue;
    options.struct_size=n; CHECK(exr_fixed_open_memory(EXR_PDF,bytes,size,&options,&d,&error)==EXR_ARGUMENT && !d);
  }
  { void *output=(void *)(uintptr_t)1; size_t out_size=123;
    CHECK(exr_pdf_annotation_remove(bytes,size,0,"missing",NULL,&output,&out_size,&error)==EXR_FORMAT && !output && !out_size);
  }
  free(bytes);
}
#endif
int main(int argc,char **argv) {
  CHECK(argc==2);
#ifdef EXR_ENABLE_PDF_CRYPTO
  {
    CHECK(exr_pdf_crypto_available());
    unsigned revision; char name[80]; const char *suffixes[]={"-objects","-metadata-clear","-identity","-crypt"}; size_t i;
    for(revision=2;revision<=6;revision++) {
      snprintf(name,sizeof(name),"r%u",revision); standard(argv[1],name,revision,"reader",0); standard(argv[1],name,revision,"owner",1);
      wrong(argv[1],name,NULL,EXR_PASSWORD); wrong(argv[1],name,"incorrect",EXR_PASSWORD);
      snprintf(name,sizeof(name),"r%u-empty",revision); standard(argv[1],name,revision,NULL,0);
      for(i=0;i<4;i++) {
        if(revision<4 && i) continue;
        snprintf(name,sizeof(name),"r%u%s",revision,suffixes[i]); standard(argv[1],name,revision,"reader",0);
      }
    }
  }
  /* RFC 4013 mapping, compatibility composition, Hangul composition, canonical
     combining order and bidirectional owner passwords. UTF-8 escapes keep MSVC exact. */
  standard(argv[1],"r6-unicode",6,"I\xc2\xadX\xe2\x85\xa8\xc2\xaa\xc2\xa0\xe1\x84\x80\xe1\x85\xa1\xe1\x86\xa8\xc3\xa9",0);
  standard(argv[1],"r6-unicode",6,"IXIXa \xea\xb0\x81" "e\xcc\x81",0);
  standard(argv[1],"r6-unicode",6,"\xd8\xa7\xd8\xa8",1);
  standard(argv[1],"r4-incremental",4,"reader",0);
  { char pw[141]; memset(pw,'x',140); pw[140]=0; standard(argv[1],"r6-long",6,pw,0); pw[127]=0; standard(argv[1],"r6-long",6,pw,0); }
  wrong(argv[1],"r6","\x07",EXR_ENCODING); wrong(argv[1],"r6","\xff",EXR_ENCODING);
  wrong(argv[1],"r6","\xd8\xa7" "a\xd8\xa8",EXR_ENCODING); wrong(argv[1],"r6"," \xd8\xa7",EXR_ENCODING);
  wrong(argv[1],"r6","\xf0\x9f\x98\x80",EXR_ENCODING); /* unassigned in Unicode 3.2 */
  wrong(argv[1],"r6-bad-perms","reader",EXR_FORMAT); wrong(argv[1],"unsupported-handler","reader",EXR_UNSUPPORTED);
  { size_t size; unsigned char *bytes=load(argv[1],"r6-bad-padding",&size); exr_fixed_document *d=NULL; exr_fixed_text *t=NULL;
    OK(open_bytes(bytes,size,"reader",NULL,&d)); free(bytes);
    CHECK(exr_fixed_load_text(d,0,NULL,&t,&error)==EXR_FORMAT && !t); exr_fixed_free(d);
  }
  contracts(argv[1]);
#else
  CHECK(!exr_pdf_crypto_available());
  { size_t size; unsigned char *bytes=load(argv[1],"r6",&size); exr_fixed_document *d=NULL;
    CHECK(open_bytes(bytes,size,"reader",NULL,&d)==EXR_UNSUPPORTED && !d); free(bytes);
  }
#endif
  printf("%u PDF authentication checks passed\n",checks); return 0;
}
