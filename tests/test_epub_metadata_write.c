/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define DCT "http://purl.org/dc/terms/"
#define OPF "http://www.idpf.org/2007/opf"
#define DC "http://purl.org/dc/elements/1.1/"
static const char opf[]=
  "<?xml version='1.0' encoding='UTF-8'?><p:package xmlns:p='" OPF "' xmlns:d='" DC "' xmlns:q='urn:vendor:' version='3.0' unique-identifier='uid'>"
  "<p:metadata><!--keep--><?vendor preserved?><d:identifier id='uid'>urn:original:book</d:identifier>"
  "<d:title id='t1' xml:lang='en'>Old title</d:title><d:title id='t2'>Other title</d:title><d:language>en</d:language>"
  "<p:meta id='ref2' refines='#ref%31' property='q:extra'>old deep refinement</p:meta><p:meta id='ref1' refines='book.opf#t%31' property='title-type'>main</p:meta>"
  "<d:creator id='a1'>Original author</d:creator><p:meta refines='#a1' property='role' scheme='marc:relators'>aut</p:meta>"
  "<d:subject>old subject</d:subject><q:complex q:type='q:Class' xml:space='preserve'><q:child><![CDATA[A<B&C]]></q:child></q:complex>"
  "<p:meta name='cover' content='cover'/></p:metadata><p:manifest>"
  "<p:item id='c1' href='chapter.xhtml' media-type='application/xhtml+xml'/><p:item id='cover' href='images/cover.png' media-type='image/png' properties='remote-resources cover-image svg'/>"
  "<p:item id='css' href='style.css' media-type='text/css'/></p:manifest><p:spine><p:itemref idref='c1'/></p:spine></p:package>";
static const char plain[]=
  "<package xmlns='" OPF "' xmlns:d='" DC "' version='2.0' unique-identifier='uid'><metadata>"
  "<d:identifier id='uid'>urn:original:book</d:identifier><d:title>Old title</d:title><d:language>en</d:language></metadata>"
  "<manifest><item id='c1' href='chapter.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref idref='c1'/></spine></package>";
static const char chapter[]="<html xmlns='http://www.w3.org/1999/xhtml'><head><title>Chapter</title></head><body><p>Body &amp; preserved text.</p></body></html>";
static unsigned char *cover_bytes; static size_t cover_size;
static const char *extra_content="untouched";
static void *book(const void *package,size_t package_size,const char *extra,int duplicate,size_t *size) {
  mz_zip_archive z={0}; void *bytes=NULL; CHECK(mz_zip_writer_init_heap(&z,0,0));
  CHECK(mz_zip_writer_add_mem(&z,"mimetype","application/epub+zip",20,0));
  CHECK(mz_zip_writer_add_mem(&z,"OPS/",NULL,0,0));
  { const char c[]="<container xmlns='urn:oasis:names:tc:opendocument:xmlns:container'><rootfiles><rootfile full-path='OPS/book.opf' media-type='application/oebps-package+xml'/></rootfiles></container>";
    CHECK(mz_zip_writer_add_mem(&z,"META-INF/container.xml",c,sizeof(c)-1,6)); }
  CHECK(mz_zip_writer_add_mem(&z,"OPS/book.opf",package,package_size,6));
  CHECK(mz_zip_writer_add_mem(&z,"OPS/chapter.xhtml",chapter,sizeof(chapter)-1,6));
  CHECK(mz_zip_writer_add_mem(&z,"OPS/style.css","p{color:red}",12,6));
  CHECK(mz_zip_writer_add_mem(&z,"OPS/images/cover.png",cover_bytes,cover_size,6));
  CHECK(mz_zip_writer_add_mem(&z,"vendor.bin","\0\xff\x01original",11,6));
  if(extra) CHECK(mz_zip_writer_add_mem(&z,extra,extra_content,strlen(extra_content),6));
  if(duplicate) CHECK(mz_zip_writer_add_mem(&z,"OPS/chapter.xhtml","conflict",8,0));
  CHECK(mz_zip_writer_finalize_heap_archive(&z,&bytes,size)); mz_zip_writer_end(&z); return bytes;
}
static void *member(const void *book_bytes,size_t book_size,const char *name,size_t *size,unsigned flags) {
  mz_zip_archive z={0}; void *bytes; int index; CHECK(mz_zip_reader_init_mem(&z,book_bytes,book_size,0));
  index=mz_zip_reader_locate_file(&z,name,NULL,MZ_ZIP_FLAG_CASE_SENSITIVE); CHECK(index>=0);
  bytes=mz_zip_reader_extract_to_heap(&z,(mz_uint)index,size,flags); CHECK(bytes); mz_zip_reader_end(&z);
  { unsigned char *terminated=malloc(*size+1); CHECK(terminated); memcpy(terminated,bytes,*size); terminated[*size]=0; mz_free(bytes); bytes=terminated; }
  return bytes;
}
static void preserved(const void *before,size_t before_size,const void *after,size_t after_size,const char *name) {
  size_t a,b; void *x=member(before,before_size,name,&a,MZ_ZIP_FLAG_COMPRESSED_DATA),*y=member(after,after_size,name,&b,MZ_ZIP_FLAG_COMPRESSED_DATA);
  CHECK(a==b && !memcmp(x,y,a)); mz_free(x); mz_free(y);
}
static int cancel(void *context) { return *(int *)context; }
static void progress(void *context,exr_stage stage,uint64_t completed,uint64_t total) { (void)stage; (void)total; if(completed) *(int *)context=1; }
static char *replace(const char *input,const char *before,const char *after) {
  const char *at=strstr(input,before); size_t n=strlen(input),a=strlen(before),b=strlen(after),prefix; char *out; CHECK(at); prefix=(size_t)(at-input); out=malloc(n-a+b+1); CHECK(out);
  memcpy(out,input,prefix); memcpy(out+prefix,after,b); memcpy(out+prefix+b,at+a,n-prefix-a+1); return out;
}
static void change_tests(const char *directory) {
  size_t size,n,k; void *input=book(opf,sizeof(opf)-1,NULL,0,&size),*output=NULL; char *xml; exr_document *doc=NULL;
  exr_metadata_entry changes[]={{DCT "title","新书名😀<&\r\n"},{DCT "creator","New author"},{DCT "subject",NULL},{DCT "description",""}};
  OK(exr_epub_metadata_write(input,size,changes,4,NULL,NULL,&output,&n,&error)); CHECK(output && n);
  xml=member(output,n,"OPS/book.opf",&k,0); CHECK(strstr(xml,"新书名😀&lt;&amp;&#13;&#10;") && strstr(xml,"New author"));
  CHECK(!strstr(xml,"Old title") && !strstr(xml,"Other title") && !strstr(xml,"old subject") && !strstr(xml,"old deep refinement"));
  CHECK(!strstr(xml,"title-type") && !strstr(xml,"marc:relators") && strstr(xml,"id=\"t1\"") && strstr(xml,"urn:original:book"));
  CHECK(strstr(xml,"xmlns:q=\"urn:vendor:\"") && strstr(xml,"q:type=\"q:Class\"") && strstr(xml,"A&lt;B&amp;C") && strstr(xml,"<!--keep-->") && strstr(xml,"<?vendor preserved?>"));
  CHECK(strstr(xml,"<dc:description") && strstr(xml,"</dc:description>")); mz_free(xml);
  preserved(input,size,output,n,"OPS/chapter.xhtml"); preserved(input,size,output,n,"OPS/style.css"); preserved(input,size,output,n,"vendor.bin"); preserved(input,size,output,n,"OPS/images/cover.png");
  OK(exr_document_open_memory(EXR_EPUB,output,n,&doc,&error)); CHECK(!strcmp(exr_document_title(doc),changes[0].value)); exr_document_free(doc);
  { char path[4096]; FILE *f; snprintf(path,sizeof(path),"%s/metadata-written.epub",directory); f=fopen(path,"wb"); CHECK(f && fwrite(output,1,n,f)==n && !fclose(f)); }
  exr_free(output); output=NULL;
  OK(exr_epub_metadata_write(input,size,NULL,0,NULL,NULL,&output,&n,&error)); CHECK(output!=input && n==size && !memcmp(input,output,n)); exr_free(output);
  { int stop=1; exr_control c={0}; c.context=&stop; c.cancelled=cancel;
    CHECK(exr_epub_metadata_write(input,size,changes,4,NULL,&c,&output,&n,&error)==EXR_CANCELLED && !output && !n);
    stop=0; c.progress=progress; CHECK(exr_epub_metadata_write(input,size,changes,4,NULL,&c,&output,&n,&error)==EXR_CANCELLED && !output && !n);
  }
  mz_free(input);
}
static void covers(void) {
  size_t size,n,k; void *input=book(opf,sizeof(opf)-1,NULL,0,&size),*output=NULL; exr_epub_cover cover={sizeof(cover),cover_bytes,cover_size,"image/png"}; char *xml;
  OK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)); xml=member(output,n,"OPS/book.opf",&k,0);
  CHECK(strstr(xml,"properties=\"remote-resources svg cover-image\"") && strstr(xml,"name=\"cover\" content=\"cover\"")); mz_free(xml);
  preserved(input,size,output,n,"OPS/chapter.xhtml"); mz_free(input); input=output; size=n; output=NULL;
  cover.data=NULL; cover.size=0; cover.media_type=NULL;
  OK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)); xml=member(output,n,"OPS/book.opf",&k,0);
  CHECK(!strstr(xml,"cover-image") && !strstr(xml,"name=\"cover\"") && strstr(xml,"properties=\"remote-resources svg\"")); mz_free(xml);
  preserved(input,size,output,n,"OPS/images/cover.png"); mz_free(input); exr_free(output);
  input=book(plain,sizeof(plain)-1,NULL,0,&size); cover.data=cover_bytes; cover.size=cover_size; cover.media_type="image/png";
  OK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)); xml=member(output,n,"OPS/book.opf",&k,0);
  CHECK(strstr(xml,"exreader-cover-0.png") && strstr(xml,"name=\"cover\" content=\"exreader-cover-0\"") && !strstr(xml,"cover-image")); mz_free(xml);
  { void *image=member(output,n,"OPS/exreader-cover-0.png",&k,0); CHECK(k==cover_size && !memcmp(image,cover_bytes,k)); mz_free(image); }
  { mz_zip_archive z={0}; mz_zip_archive_file_stat st; CHECK(mz_zip_reader_init_mem(&z,output,n,0) && mz_zip_reader_file_stat(&z,0,&st)); CHECK(!strcmp(st.m_filename,"mimetype") && !st.m_method && !st.m_local_header_ofs); mz_zip_reader_end(&z); }
  mz_free(input); exr_free(output);
}
static void boundaries(void) {
  size_t i,size,n; void *input,*output=NULL; exr_metadata_entry change={DCT "title","Name"};
  const char *blocked[]={"META-INF/signatures.xml","META-INF/rights.xml","../outside","OPS/../outside"};
  for(i=0;i<sizeof(blocked)/sizeof(*blocked);i++) { input=book(opf,sizeof(opf)-1,blocked[i],0,&size); CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_FORMAT && !output && !n); mz_free(input); }
  input=book(opf,sizeof(opf)-1,NULL,1,&size); CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_FORMAT && !output && !n); mz_free(input);
  input=book(opf,sizeof(opf)-1,"META-INF/encryption.xml",0,&size);
  OK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)); preserved(input,size,output,n,"META-INF/encryption.xml"); exr_free(output);
  { exr_epub_cover cover={sizeof(cover),cover_bytes,cover_size,"image/png"}; CHECK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)==EXR_FORMAT && !output && !n); }
  { exr_epub_cover cover={sizeof(cover),NULL,0,NULL}; OK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)); preserved(input,size,output,n,"META-INF/encryption.xml"); exr_free(output); }
  mz_free(input);
  extra_content="<encryption xmlns='urn:oasis:names:tc:opendocument:xmlns:container' xmlns:e='http://www.w3.org/2001/04/xmlenc#'><e:EncryptedData><e:CipherData><e:CipherReference URI='OPS/font.otf'/></e:CipherData></e:EncryptedData></encryption>";
  input=book(opf,sizeof(opf)-1,"META-INF/encryption.xml",0,&size);
  { exr_epub_cover cover={sizeof(cover),cover_bytes,cover_size,"image/png"}; OK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)); preserved(input,size,output,n,"META-INF/encryption.xml"); exr_free(output); }
  mz_free(input);
  extra_content="<encryption xmlns='urn:oasis:names:tc:opendocument:xmlns:container' xmlns:e='http://www.w3.org/2001/04/xmlenc#'><e:EncryptedData><e:CipherData><e:CipherReference URI='OPS/images/co%76er.png'/></e:CipherData></e:EncryptedData></encryption>";
  input=book(opf,sizeof(opf)-1,"META-INF/encryption.xml",0,&size);
  { exr_epub_cover cover={sizeof(cover),cover_bytes,cover_size,"image/png"}; CHECK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)==EXR_FORMAT && !output && !n); }
  mz_free(input); extra_content="untouched"; input=book(opf,sizeof(opf)-1,NULL,0,&size);
  { exr_metadata_entry duplicate[2]={change,change}; CHECK(exr_epub_metadata_write(input,size,duplicate,2,NULL,NULL,&output,&n,&error)==EXR_ARGUMENT && !output && !n); }
  change.key=DCT "identifier"; CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_ARGUMENT && !output && !n);
  change.key=DCT "title"; change.value=NULL; CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_ARGUMENT && !output && !n);
  change.value=" \t\r\n"; CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_ARGUMENT && !output && !n);
  change.key=DCT "language"; change.value=""; CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_ARGUMENT && !output && !n);
  change.key=DCT "title";
  change.value="\xff"; CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_ENCODING && !output && !n);
  change.value="\x01"; CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_ENCODING && !output && !n);
  { exr_epub_cover cover={sizeof(cover),"bad",3,"image/png"}; CHECK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)==EXR_FORMAT && !output && !n); }
  mz_free(input);
  change.value="Name";
  { char *xml=replace(opf,"version='3.0'","xml:base='elsewhere.opf' version='3.0'");
    input=book(xml,strlen(xml),NULL,0,&size); free(xml); CHECK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)==EXR_FORMAT && !output && !n); mz_free(input);
  }
  { const char *reserved[]={"book.opf","../mimetype","../META-INF/container.xml"};
    for(i=0;i<sizeof(reserved)/sizeof(*reserved);i++) { char *xml=replace(opf,"images/cover.png",reserved[i]); exr_epub_cover cover={sizeof(cover),cover_bytes,cover_size,"image/png"};
      input=book(xml,strlen(xml),NULL,0,&size); free(xml); CHECK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)==EXR_FORMAT && !output && !n); mz_free(input);
    }
  }
  { char *xml=replace(opf,"<p:item id='css'","<p:item id='alias' href='images/cover.png' media-type='image/jpeg'/><p:item id='css'"); exr_epub_cover cover={sizeof(cover),cover_bytes,cover_size,"image/png"};
    input=book(xml,strlen(xml),NULL,0,&size); free(xml); OK(exr_epub_metadata_write(input,size,NULL,0,&cover,NULL,&output,&n,&error)); xml=member(output,n,"OPS/book.opf",&size,0);
    CHECK(strstr(xml,"id=\"alias\"") && !strstr(xml,"image/jpeg")); mz_free(xml); mz_free(input); exr_free(output);
  }
  { unsigned char *utf16=malloc(2+2*(sizeof(plain)-1)); CHECK(utf16); utf16[0]=255; utf16[1]=254;
    for(i=0;i<sizeof(plain)-1;i++) { utf16[2+2*i]=(unsigned char)plain[i]; utf16[3+2*i]=0; }
    input=book(utf16,2+2*(sizeof(plain)-1),NULL,0,&size); free(utf16); change.value="UTF16输入";
    OK(exr_epub_metadata_write(input,size,&change,1,NULL,NULL,&output,&n,&error)); { char *xml=member(output,n,"OPS/book.opf",&size,0); CHECK(strstr(xml,"encoding=\"UTF-8\"") && strstr(xml,"UTF16输入")); mz_free(xml); }
    mz_free(input); exr_free(output);
  }
}
int main(int argc,char **argv) {
  char path[4096]; FILE *f; long length; unsigned char rgba[16]={255,0,0,255,0,255,0,255,0,0,255,255,255,255,0,255}; exr_bitmap bitmap={2,2,8,rgba,4};
  CHECK(argc==2); snprintf(path,sizeof(path),"%s/epub-metadata-cover.png",argv[1]); OK(exr_bitmap_write_png(&bitmap,path,&error)); f=fopen(path,"rb"); CHECK(f && !fseek(f,0,SEEK_END)); length=ftell(f); CHECK(length>0); rewind(f); cover_size=(size_t)length; cover_bytes=malloc(cover_size); CHECK(cover_bytes && fread(cover_bytes,1,cover_size,f)==cover_size && !fclose(f));
  change_tests(argv[1]); covers(); boundaries(); free(cover_bytes); printf("%u EPUB original metadata/cover writing checks passed\n",checks); return 0;
}
