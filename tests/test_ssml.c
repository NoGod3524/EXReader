/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <expat.h>
#include <miniz.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do {checks++;if(!(x)){fprintf(stderr,"line %d: %s (%s)\n",__LINE__,#x,error.message);exit(1);}} while(0)
#define OK(x) CHECK((x)==EXR_OK)
static exr_publication *publication(const char *xml) {
  exr_publication *p=NULL;mz_zip_archive z={0};void *bytes=NULL;size_t size=0;
  const char *mime="application/epub+zip";
  const char *container="<container xmlns='urn:oasis:names:tc:opendocument:xmlns:container'><rootfiles><rootfile full-path='book.opf' media-type='application/oebps-package+xml'/></rootfiles></container>";
  const char *opf="<package xmlns='http://www.idpf.org/2007/opf' version='3.0' unique-identifier='id'><metadata xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:identifier id='id'>ssml</dc:identifier><dc:title>SSML</dc:title><dc:language>zh</dc:language></metadata><manifest><item id='a' href='a.xhtml' media-type='application/xhtml+xml'/></manifest><spine><itemref idref='a'/></spine></package>";
  CHECK(mz_zip_writer_init_heap(&z,0,0));
  CHECK(mz_zip_writer_add_mem(&z,"mimetype",mime,strlen(mime),0));
  CHECK(mz_zip_writer_add_mem(&z,"META-INF/container.xml",container,strlen(container),0));
  CHECK(mz_zip_writer_add_mem(&z,"book.opf",opf,strlen(opf),0));
  CHECK(mz_zip_writer_add_mem(&z,"a.xhtml",xml,strlen(xml),0));
  CHECK(mz_zip_writer_finalize_heap_archive(&z,&bytes,&size));mz_zip_writer_end(&z);
  OK(exr_publication_open_memory(EXR_EPUB,bytes,size,&p,&error));mz_free(bytes);return p;
}
static size_t scalars(const char *text,size_t size) {
  size_t i,n=0;for(i=0;i<size;i++) n+=((unsigned char)text[i]&0xc0)!=0x80;return n;
}
typedef struct {char text[50000];size_t size;int p,s,breaks;} decoded;
static void XMLCALL chars(void *ctx,const XML_Char *s,int n) {
  decoded *d=ctx;CHECK(d->size+(size_t)n<sizeof(d->text));memcpy(d->text+d->size,s,(size_t)n);d->size+=(size_t)n;d->text[d->size]=0;
}
static void XMLCALL element(void *ctx,const XML_Char *name,const XML_Char **attrs) {
  decoded *d=ctx;(void)attrs;if(!strcmp(name,"p")) d->p++;if(!strcmp(name,"s")) d->s++;if(!strcmp(name,"break")) d->breaks++;
}
static decoded parse(const exr_ssml_chunk *chunk) {
  decoded d={0};XML_Parser parser=XML_ParserCreate(NULL);CHECK(parser);
  XML_SetUserData(parser,&d);XML_SetCharacterDataHandler(parser,chars);XML_SetStartElementHandler(parser,element);
  CHECK(XML_Parse(parser,chunk->ssml,(int)chunk->size,1)==XML_STATUS_OK);XML_ParserFree(parser);
  CHECK(scalars(d.text,d.size)==chunk->characters);CHECK((size_t)d.s==chunk->sentence_count);
  return d;
}
static void structure(void) {
  const char *xml="<html lang='zh'><body><p>甲。乙！丙？丁；A.B!C? &amp;&lt;&gt;😀</p><p lang='en'>Hello. <span xml:lang='zh-CN'>中文。</span> End!</p></body></html>";
  exr_publication *p=publication(xml);exr_ssml_chunk c={0};
  OK(exr_document_ssml(p,(exr_ssml_position){0,0,0},0,&c,0,NULL,&error));
  decoded d=parse(&c);CHECK(d.p==2);CHECK(d.s>=10);CHECK(d.breaks>=1);
  CHECK(strstr(c.ssml,"xml:lang=\"zh-CN\""));CHECK(strstr(c.ssml,"xml:lang=\"en-US\""));
  CHECK(strstr(d.text,"&<>😀"));CHECK(!strstr(c.ssml,"font"));CHECK(strstr(c.ssml,"time=\"300ms\""));
  for(size_t i=0;i<c.sentence_count;i++) CHECK(c.sentences[i].ssml_start<c.sentences[i].ssml_end);
  exr_ssml_chunk_free(&c);exr_publication_free(p);
}
static void chunks(void) {
  char *xml=calloc(1,40000);CHECK(xml);strcpy(xml,"<html><body><p>");
  for(int i=0;i<4000;i++) strcat(xml,"甲😀");
  strcat(xml,"</p></body></html>");
  exr_publication *p=publication(xml);exr_ssml_position at={0,0,0};size_t total=0;
  for(int i=0;i<10;i++) {
    exr_ssml_chunk c={0};OK(exr_document_ssml(p,at,800,&c,0,NULL,&error));decoded d=parse(&c);
    CHECK(c.characters==800);CHECK(d.size==2800);CHECK(!memcmp(d.text,xml+15+total,d.size));
    CHECK(c.sentences[0].range.start.offset==total);total+=d.size;
    CHECK(c.sentences[c.sentence_count-1].range.end.offset==total);at=c.next;
    CHECK(c.end==(i==9));exr_ssml_chunk_free(&c);
  }
  CHECK(total==28000);exr_publication_free(p);free(xml);
  p=publication("<html><body><p>甲😀。&amp;</p><p>乙。</p></body></html>");at=(exr_ssml_position){0,0,0};char all[128]="";
  for(int i=0;i<30;i++) {
    exr_ssml_chunk c={0};OK(exr_document_ssml(p,at,1,&c,0,NULL,&error));decoded d=parse(&c);strcat(all,d.text);at=c.next;
    int end=c.end;CHECK(c.characters<=1);exr_ssml_chunk_free(&c);if(end) break;CHECK(i<29);
  }
  CHECK(!strcmp(all,"甲😀。&乙。"));exr_publication_free(p);
}
static void omissions(void) {
  const char *xml="<html xmlns:epub='http://www.idpf.org/2007/ops' lang='en'><body><p>A<img src='x'/><img src='y'/>B<a epub:type='noteref' href='#n'>99</a>C.</p><table><tr><td>secret table</td></tr></table><aside id='n' role='doc-footnote'>secret note</aside><p>D.</p></body></html>";
  exr_publication *p=publication(xml);exr_ssml_chunk c={0};
  OK(exr_document_ssml(p,(exr_ssml_position){0,0,0},0,&c,0,NULL,&error));decoded d=parse(&c);
  CHECK(!strcmp(d.text,"ABC.D."));exr_ssml_chunk_free(&c);
  char all[256]="";exr_ssml_position at={0,0,0};
  for(int i=0;i<30;i++) {
    OK(exr_document_ssml(p,at,8,&c,7,NULL,&error));d=parse(&c);strcat(all,d.text);at=c.next;
    CHECK(c.characters<=8);int end=c.end;exr_ssml_chunk_free(&c);if(end) break;CHECK(i<29);
  }
  CHECK(!strcmp(all,"AImage.Image.BNote.C.Table.Note.D."));exr_publication_free(p);
}
static int cancel(void *ctx) {(void)ctx;return 1;}
typedef struct {const char *text[4];int loads;} text_source;
static exr_status load_text(void *context,size_t part,exr_document **out,exr_error *e) {
  text_source *source=context;source->loads++;
  if(part==2) {
    exr_node_input nodes[]={{EXR_NODE_DOCUMENT,SIZE_MAX,NULL,NULL,NULL,0},{EXR_NODE_CHAPTER,0,NULL,NULL,NULL,0}};
    exr_chapter_input chapter={"empty","empty.txt",1,1};
    exr_document_input input={"Empty",nodes,2,&chapter,1,NULL,0};
    return exr_document_create(&input,out,e);
  }
  return exr_document_open_memory(EXR_TXT,source->text[part],strlen(source->text[part]),out,e);
}
static void parts(void) {
  text_source source={{"A\001B.\n\nC.","must not speak this","\n","末尾。"},0};
  exr_part entries[]={{"a","a.txt","",1},{"aux","aux.txt","",0},{"empty","empty.txt","",1},{"b","b.txt","",1}};
  exr_publication_input in={0};exr_publication *p=NULL;exr_ssml_chunk c={0};
  in.parts=entries;in.part_count=4;in.load=load_text;in.context=&source;OK(exr_publication_create(&in,&p,&error));
  OK(exr_document_ssml(p,(exr_ssml_position){0,0,0},3,&c,0,NULL,&error));decoded d=parse(&c);
  CHECK(!strcmp(d.text,"AB."));CHECK(strstr(c.ssml,"300ms"));CHECK(source.loads==1);
  exr_ssml_position at=c.next;exr_ssml_chunk_free(&c);
  OK(exr_document_ssml(p,at,800,&c,0,NULL,&error));d=parse(&c);CHECK(!strcmp(d.text,"C."));
  CHECK(c.next.part==2 && !c.end);CHECK(source.loads==2);at=c.next;exr_ssml_chunk_free(&c);
  OK(exr_document_ssml(p,at,800,&c,0,NULL,&error));d=parse(&c);CHECK(!strcmp(d.text,"末尾。"));
  CHECK(c.end && c.next.part==4);CHECK(source.loads==4);exr_ssml_chunk_free(&c);exr_publication_free(p);
}
static void contracts(void) {
  exr_publication *p=publication("<html><body><p>中文。</p></body></html>");exr_ssml_chunk c={0};
  CHECK(exr_document_ssml(NULL,(exr_ssml_position){0,0,0},0,&c,0,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_document_ssml(p,(exr_ssml_position){0,1,0},0,&c,0,NULL,&error)==EXR_ARGUMENT);
  CHECK(!c.ssml && !c.sentence_count);
  CHECK(exr_document_ssml(p,(exr_ssml_position){0,1000,0},0,&c,0,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_document_ssml(p,(exr_ssml_position){0,0,1000},0,&c,0,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_document_ssml(p,(exr_ssml_position){0,0,0},65537,&c,0,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_document_ssml(p,(exr_ssml_position){0,0,0},0,&c,8,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_document_ssml(p,(exr_ssml_position){0,0,0},1,&c,1,NULL,&error)==EXR_ARGUMENT);
  exr_control control={0};control.cancelled=cancel;
  CHECK(exr_document_ssml(p,(exr_ssml_position){0,0,0},0,&c,0,&control,&error)==EXR_CANCELLED);
  CHECK(!c.ssml);OK(exr_document_ssml(p,(exr_ssml_position){1,0,0},0,&c,0,NULL,&error));
  decoded d=parse(&c);CHECK(!d.size && c.end);exr_ssml_chunk_free(&c);exr_publication_free(p);
}
int main(int argc,char **argv) {
  CHECK(argc==2);
  if(!strcmp(argv[1],"structure")) structure();else if(!strcmp(argv[1],"chunks")) chunks();
  else if(!strcmp(argv[1],"omissions")) omissions();else if(!strcmp(argv[1],"contracts")) contracts();
  else if(!strcmp(argv[1],"parts")) parts();else return 2;
  printf("SSML %s: %u checks passed\n",argv[1],checks);return 0;
}
