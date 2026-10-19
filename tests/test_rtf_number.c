/* SPDX-License-Identifier: MIT */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define DECIMAL "{\\list\\listid2147483647{\\listlevel\\levelnfc0\\levelstartat3{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'01;}}}"
#define OVERRIDE "{\\listoverride\\listid2147483647\\listoverridecount0\\ls1}"
static exr_status parse(const char *defs,const char *overrides,const char *body,exr_document **out) {
  size_t capacity=strlen(defs)+strlen(overrides)+strlen(body)+128; char *source=malloc(capacity); exr_status status; CHECK(source);
  snprintf(source,capacity,"{\\rtf1{\\*\\listtable%s}{\\*\\listoverridetable%s}%s}",defs,overrides,body);
  status=exr_document_open_memory(EXR_RTF,source,strlen(source),out,&error); free(source); return status;
}
static exr_document *open(const char *defs,const char *overrides,const char *body) { exr_document *d=NULL; OK(parse(defs,overrides,body,&d)); return d; }
static void roundtrip(exr_document *d,const char *dir) {
  exr_document *copy=NULL; void *zip=NULL; size_t size,pa,pb,i; exr_font *font=NULL; exr_layout *a=NULL,*b=NULL; exr_bitmap ba,bb; char path[4096];
  exr_layout_config config=exr_layout_config_defaults(); config.page=(exr_layout_options){240,200,4,14,1.2f,2};
  snprintf(path,sizeof(path),"%s/fonts/primary.ttf",dir); OK(exr_font_open(path,&font,&error));
  OK(exr_document_export_epub(d,NULL,&zip,&size,&error)); OK(exr_document_open_memory(EXR_EPUB,zip,size,&copy,&error)); exr_free(zip); CHECK(!strcmp(exr_document_text(d,NULL),exr_document_text(copy,NULL)));
  OK(exr_layout_create_ex(d,font,&config,&a,&error)); OK(exr_layout_create_ex(copy,font,&config,&b,&error)); exr_layout_pages(a,&pa); exr_layout_pages(b,&pb); CHECK(pa==pb && pa);
  for(i=0;i<pa;i++) { OK(exr_render_page(a,NULL,i,&ba,&error)); OK(exr_render_page(b,NULL,i,&bb,&error)); CHECK(ba.stride==bb.stride && ba.height==bb.height && !memcmp(ba.pixels,bb.pixels,(size_t)ba.stride*ba.height)); exr_bitmap_free(&ba); exr_bitmap_free(&bb); }
  exr_layout_free(a); exr_layout_free(b); exr_font_free(font); exr_document_free(copy);
}
int main(int argc,char **argv) {
  exr_document *d=NULL; const char *text; const exr_node *nodes; size_t i,count,starts=0; char defs[8192],body[4096],overrides[4096];
  CHECK(argc==2); d=open(DECIMAL,OVERRIDE,"\\pard\\ls1 A\\par\\pard\\ls1 B\\par\\pard Plain\\par\\pard\\ls1 C"); text=exr_document_text(d,NULL); CHECK(strstr(text,"3. A") && strstr(text,"4. B") && strstr(text,"5. C"));
  nodes=exr_document_nodes(d,&count); for(i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_LIST) { const char *start=exr_node_attribute(&nodes[i],"start"); CHECK(start && (!strcmp(start,"3") || !strcmp(start,"5"))); starts++; } CHECK(starts==2); roundtrip(d,argv[1]); exr_document_free(d);
  d=open(DECIMAL,OVERRIDE,"\\pard\\ls1{\\listtext 3.\\tab}A\\par\\pard\\ls1 B"); CHECK(strstr(exr_document_text(d,NULL),"3. A") && strstr(exr_document_text(d,NULL),"4. B") && !strstr(exr_document_text(d,NULL),"3.3.")); exr_document_free(d);
  { const unsigned formats[]={1,4,22}; const int start[]={3,26,9}; const char *expected[][2]={{"III. A","IV. B"},{"z. A","aa. B"},{"09. A","10. B"}};
    for(i=0;i<3;i++) { snprintf(defs,sizeof(defs),"{\\list\\listid2147483647{\\listlevel\\levelnfc%u\\levelstartat%d{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'01;}}}",formats[i],start[i]); d=open(defs,OVERRIDE,"\\pard\\ls1 A\\par\\pard\\ls1 B"); CHECK(strstr(exr_document_text(d,NULL),expected[i][0]) && strstr(exr_document_text(d,NULL),expected[i][1])); exr_document_free(d); }
  }
  snprintf(defs,sizeof(defs),"{\\list\\listid2147483647{\\listlevel\\levelnfc0\\levelnfcn1\\levelnfc4\\levelstartat3{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'01;}}}"); d=open(defs,OVERRIDE,"\\pard\\ls1 A"); CHECK(strstr(exr_document_text(d,NULL),"III. A")); exr_document_free(d);
  { const char *multi="{\\list\\listid2147483647{\\listlevel\\levelnfc1\\levelstartat3{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'01;}}{\\listlevel\\levelnfc4\\levelstartat1\\levellegal1{\\leveltext\\'04\\'00.\\'01);}{\\levelnumbers\\'01\\'03;}}}";
    const char *sequence="\\pard\\ls1 Root\\par\\pard\\ls1\\ilvl1 One\\par\\pard\\ls1\\ilvl1 Two\\par\\pard\\ls1 Next\\par\\pard\\ls1\\ilvl1 Again";
    d=open(multi,OVERRIDE,sequence); text=exr_document_text(d,NULL); CHECK(strstr(text,"III. Root") && strstr(text,"3.a) One") && strstr(text,"3.b) Two") && strstr(text,"4.a) Again")); roundtrip(d,argv[1]); exr_document_free(d);
    snprintf(defs,sizeof(defs),"%s",multi); { char *where=strstr(defs,"\\levellegal1"); size_t prefix=(size_t)(where-defs); memmove(defs+prefix+strlen("\\levelnorestart1"),defs+prefix,strlen(defs+prefix)+1); memcpy(defs+prefix,"\\levelnorestart1",strlen("\\levelnorestart1")); }
    d=open(defs,OVERRIDE,sequence); CHECK(strstr(exr_document_text(d,NULL),"4.c) Again")); exr_document_free(d);
  }
  snprintf(overrides,sizeof(overrides),"%s{\\listoverride\\listid2147483647\\listoverridecount1{\\lfolevel\\listoverridestartat\\levelstartat10}\\ls2}{\\listoverride\\listid2147483647\\listoverridecount1{\\lfolevel\\listoverrideformat1{\\listlevel\\levelnfc1\\levelstartat1{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'01;}}}\\ls3}{\\listoverride\\listid2147483647\\listoverridecount1{\\lfolevel\\listoverridestartat\\listoverrideformat1{\\listlevel\\levelnfc4\\levelstartat12{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'01;}}}\\ls4}",OVERRIDE);
  d=open(DECIMAL,overrides,"\\pard\\ls2 A\\par\\pard\\ls2 B\\par\\pard\\ls3 C\\par\\pard\\ls4 D"); text=exr_document_text(d,NULL); CHECK(strstr(text,"10. A") && strstr(text,"11. B") && strstr(text,"III. C") && strstr(text,"l. D")); roundtrip(d,argv[1]); exr_document_free(d);
  d=open("{\\list\\listid2147483647{\\listlevel\\levelnfc23{\\leveltext\\'01\\u8226?;}{\\levelnumbers;}}}",OVERRIDE,"\\pard\\ls1 Bullet"); CHECK(strstr(exr_document_text(d,NULL),"\xe2\x80\xa2 Bullet")); exr_document_free(d);
  d=open("{\\list\\listid2147483647{\\listlevel\\levelnfc255{\\leveltext\\'00;}{\\levelnumbers;}}}",OVERRIDE,"\\pard\\ls1 None"); CHECK(!strcmp(exr_document_text(d,NULL),"None")); exr_document_free(d);
  d=open("{\\list\\listid2147483647{\\listlevel\\levelnfc0{\\leveltext\\'03\\'00;);}{\\levelnumbers\\'01;}}}",OVERRIDE,"\\pard\\ls1 Semi"); CHECK(strstr(exr_document_text(d,NULL),"1;) Semi")); exr_document_free(d);
  { unsigned lengths[]={59,128,255}; size_t k;
    for(k=0;k<3;k++) { unsigned length=lengths[k]; size_t at=(size_t)snprintf(defs,sizeof(defs),"{\\list\\listid2147483647{\\listlevel\\levelnfc0\\levelstartat3{\\leveltext\\'%02x",length); memset(defs+at,'x',length-1); at+=length-1; snprintf(defs+at,sizeof(defs)-at,"\\'00;}{\\levelnumbers\\'%02x;}}}",length); d=open(defs,OVERRIDE,"\\pard\\ls1 Tail"); CHECK(strstr(exr_document_text(d,NULL),"3 Tail")); exr_document_free(d); }
  }
  d=open("{\\list\\listid-2147483648{\\listlevel\\levelnfc0\\levelstartat-1}}","{\\listoverride\\listid-2147483648\\listoverridecount0\\ls1}","\\pard\\ls1 Negative"); CHECK(strstr(exr_document_text(d,NULL),"-1. Negative")); exr_document_free(d);
  { const char *invalid[]={"{\\list\\listid2147483647{\\listlevel{\\leveltext\\'03\\'00;}{\\levelnumbers\\'01;}}}","{\\list\\listid2147483647{\\listlevel{\\leveltext\\'02\\'00.;}{\\levelnumbers;}}}","{\\list\\listid2147483647{\\listlevel{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'02;}}}","{\\list\\listid2147483647{\\listlevel{\\leveltext\\'02\\'00.;}{\\levelnumbers\\'01\\'01;}}}"};
    for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) { exr_status status=parse(invalid[i],OVERRIDE,"\\pard\\ls1 A",&d); if(status!=EXR_FORMAT) fprintf(stderr,"invalid case=%zu status=%d\n",i,status); CHECK(status==EXR_FORMAT && !d); }
  }
  CHECK(parse(DECIMAL DECIMAL,OVERRIDE,"\\pard\\ls1 A",&d)==EXR_FORMAT && !d); CHECK(parse(DECIMAL,OVERRIDE OVERRIDE,"\\pard\\ls1 A",&d)==EXR_FORMAT && !d);
  CHECK(parse("{\\list\\listid2147483647{\\listlevel\\levelnfc5}}",OVERRIDE,"\\pard\\ls1 A",&d)==EXR_FORMAT && !d);
  d=open("{\\list\\listid2147483647{\\listlevel\\levelnfc5}}",OVERRIDE,"\\pard\\ls1{\\listtext 3rd\\tab}A"); CHECK(strstr(exr_document_text(d,NULL),"3rd A")); exr_document_free(d);
  { const char *bad[]={"{\\rtf1 A\\'00B}","{\\rtf1\\unknown2147483648 A}","{\\rtf1\\unknown-2147483649 A}"}; for(i=0;i<3;i++) CHECK(exr_document_open_memory(EXR_RTF,bad[i],strlen(bad[i]),&d,&error)==EXR_FORMAT && !d); }
  snprintf(body,sizeof(body),"\\pard\\ls1 A{\\footnote\\chftn Note}\\par\\pard\\ls1 B"); d=open(DECIMAL,OVERRIDE,body); CHECK(strstr(exr_document_text(d,NULL),"3. A1") && strstr(exr_document_text(d,NULL),"4. B")); exr_document_free(d);
  d=open("{\\list\\listid2147483647{\\listlevel\\levelnfc23}{\\listlevel\\levelnfc0}}",OVERRIDE,"\\pard\\ls1\\ilvl1 Deep");
  nodes=exr_document_nodes(d,&count); starts=0; for(i=0;i<count;i++) if(nodes[i].kind==EXR_NODE_LIST) { CHECK(strstr(nodes[i].name,starts ? "|ol" : "|ul")); starts++; } CHECK(starts==2); exr_document_free(d);
  d=open("{\\list\\listid2147483647{\\listlevel\\levelnfc0\\b\\fs36\\li720\\fi-360}}",OVERRIDE,"\\pard\\ls1\\li0\\fi0 Body");
  nodes=exr_document_nodes(d,&count); starts=0; for(i=0;i<count;i++) { const char *css=exr_node_attribute(&nodes[i],"style"),*hidden=exr_node_attribute(&nodes[i],"aria-hidden"); if(hidden) { CHECK(css && strstr(css,"font-size:24.0000px") && nodes[i].parent<count && strstr(nodes[nodes[i].parent].name,"|strong")); starts++; } if(nodes[i].kind==EXR_NODE_PARAGRAPH) CHECK(css && strstr(css,"margin-left:0.0000px") && strstr(css,"text-indent:0.0000px")); } CHECK(starts==1); roundtrip(d,argv[1]); exr_document_free(d);
  CHECK(parse("{\\list\\listid2147483647{\\listlevel\\levelstartat2147483647}}",OVERRIDE,"\\pard\\ls1 A\\par\\pard\\ls1 B",&d)==EXR_LIMIT && !d);
  CHECK(parse(DECIMAL,"{\\listoverride\\listid2147483647\\listoverridecount1{\\lfolevel\\listoverridestartat}\\ls1}","\\pard\\ls1 A",&d)==EXR_FORMAT && !d);
  { size_t used=0; for(i=0;i<10;i++) used+=(size_t)snprintf(defs+used,sizeof(defs)-used,"{\\listlevel}"); snprintf(body,sizeof(body),"{\\list\\listid2147483647%s}",defs); CHECK(parse(body,OVERRIDE,"\\pard\\ls1 A",&d)==EXR_FORMAT && !d); }
  printf("%u RTF numbering checks passed\n",checks); return 0;
}
