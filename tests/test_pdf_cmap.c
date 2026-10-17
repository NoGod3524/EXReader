/* SPDX-License-Identifier: GPL-3.0-only */
#include "../src/pdf_internal.h"
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define START "/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapType 2 def "
#define END " endcmap CMapName currentdict /CMap defineresource pop end end"
static exr_pdf_cmap *parse(const char *text) {
  exr_pdf_cmap *map=NULL; OK(exr_pdf_cmap_parse(text,strlen(text),NULL,&map,&error)); CHECK(map); return map;
}
static void mapped(exr_pdf_cmap *map,const void *data,size_t size,uint32_t code,const void *expected,size_t length) {
  exr_pdf_mapping out; size_t at=0;
  OK(exr_pdf_cmap_next(map,data,size,&at,&out,&error));
  CHECK(at==size && out.code==code && out.code_bytes==size && out.size==length && !memcmp(out.utf8,expected,length) && out.utf8[length]==0);
}
static void bad(const char *body,exr_status expected) {
  char text[8192]; exr_pdf_cmap *map=(exr_pdf_cmap *)(uintptr_t)1;
  snprintf(text,sizeof(text),"%s%s%s",START,body,END);
  CHECK(exr_pdf_cmap_parse(text,strlen(text),NULL,&map,&error)==expected && !map && error.code==expected && error.message[0]);
}
static int cancelled(void *context) { (void)context; return 1; }
int main(void) {
  const char *invalid[]={
    "1 begincodespacerange <00> <7f> endcodespacerange 1 beginbfchar <80> <0041> endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfchar <41> <D800> endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfchar <41> <DC00> endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfchar <41> <D8000041> endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfchar <41> <00> endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange 2 beginbfchar <41> <0041> endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange 2 beginbfchar <41> <0041> <41> <0042> endbfchar",
    "1 begincodespacerange <ff> <00> endcodespacerange",
    "1 begincodespacerange <00> <ffff> endcodespacerange",
    "2 begincodespacerange <00> <ff> <20> <30> endcodespacerange",
    "2 begincodespacerange <00> <ff> <8100> <81ff> endcodespacerange",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfrange <41> <43> [<0041> <0042>] endbfrange",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfrange <41> <41> [<0041> <0042>] endbfrange",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfrange <41> <42> <FFFF> endbfrange",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfrange <41> <42> <D7FF> endbfrange",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 beginbfchar <41> <0041> endbfrange",
    "1 begincodespacerange <00> <ff> endcodespacerange 101 beginbfchar endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange -1 beginbfchar endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange /Other usecmap",
    "1 begincodespacerange <00> <ff> endcodespacerange /CMapType 1 def",
    "1 beginbfchar <41> <0041> endbfchar",
    "1 begincodespacerange <00> <ff> endcodespacerange 1 begincidchar <41> 12 endcidchar"
  };
  exr_pdf_cmap *map; size_t i,at; exr_pdf_mapping out;
  map=parse(START "3 begincodespacerange <00> <7f> <8100> <81ff> <90000000> <900000ff> endcodespacerange "
    "3 beginbfchar <41> <0041> <42> <00660069> <8101> <D83DDE00> endbfchar "
    "2 beginbfrange <60> <62> <0061> <8110> <8112> [<4E00> <4E8C> <4E09>] endbfrange "
    "1 beginbfrange <90000001> <90000003> <00FF> endbfrange "
    "2 beginbfchar <00> <> <43> <0000> endbfchar" END);
  mapped(map,"A",1,65,"A",1); mapped(map,"B",1,66,"fi",2);
  mapped(map,"\x81\x01",2,0x8101,"\xf0\x9f\x98\x80",4);
  mapped(map,"\x61",1,0x61,"b",1); mapped(map,"\x81\x11",2,0x8111,"\xe4\xba\x8c",3);
  mapped(map,"\x90\0\0\x02",4,0x90000002,"\xc4\x80",2);
  mapped(map,"\0",1,0,"",0); mapped(map,"C",1,67,"\0",1); mapped(map,"D",1,68,"\xef\xbf\xbd",3);
  at=0; CHECK(exr_pdf_cmap_next(map,(const unsigned char *)"\x81",1,&at,&out,&error)==EXR_FORMAT && !at && !out.size);
  at=0; CHECK(exr_pdf_cmap_next(map,(const unsigned char *)"\xff",1,&at,&out,&error)==EXR_FORMAT && !at);
  exr_pdf_cmap_free(map);
  map=parse(START "2 begincodespacerange <00> <7f> <80> <ff> endcodespacerange 1 beginbfrange <00> <ff> <0000> endbfrange" END);
  mapped(map,"\xff",1,255,"\xc3\xbf",2); exr_pdf_cmap_free(map);
  map=parse(START "1 begincodespacerange <ffffffff> <ffffffff> endcodespacerange 1 beginbfrange <ffffffff> <ffffffff> [<0041>] endbfrange" END);
  mapped(map,"\xff\xff\xff\xff",4,UINT32_MAX,"A",1); exr_pdf_cmap_free(map);
  map=parse(START "1 begincodespacerange <0000> <17ff> endcodespacerange 1 beginbfrange <0000> <17ff> <D7FF> endbfrange" END);
  at=0; CHECK(exr_pdf_cmap_next(map,(const unsigned char *)"\0\1",2,&at,&out,&error)==EXR_FORMAT && !at && !out.size); exr_pdf_cmap_free(map);
  for(i=0;i<sizeof(invalid)/sizeof(*invalid);i++) bad(invalid[i],EXR_FORMAT);
  { exr_buffer text={0}; char entry[128];
    CHECK(exr_append(&text,START "1 begincodespacerange <00> <ff> endcodespacerange 100 beginbfchar ",strlen(START "1 begincodespacerange <00> <ff> endcodespacerange 100 beginbfchar ")));
    for(i=0;i<100;i++) { int n=snprintf(entry,sizeof(entry),"<%02x> <%04x> ",(unsigned)i,(unsigned)(i+32)); CHECK(exr_append(&text,entry,(size_t)n)); }
    CHECK(exr_append(&text,"endbfchar" END,strlen("endbfchar" END))); map=parse(text.data);
    mapped(map,"\x63",1,99,"\xc2\x83",2); exr_pdf_cmap_free(map); free(text.data);
  }
  { exr_control control={0}; control.cancelled=cancelled; map=(exr_pdf_cmap *)(uintptr_t)1;
    CHECK(exr_pdf_cmap_parse(START END,strlen(START END),&control,&map,&error)==EXR_CANCELLED && !map);
  }
  CHECK(exr_pdf_cmap_parse(NULL,1,NULL,&map,&error)==EXR_ARGUMENT && !map);
  CHECK(exr_pdf_cmap_parse(START END,strlen(START END),NULL,NULL,&error)==EXR_ARGUMENT);
  exr_pdf_cmap_free(NULL); printf("%u native PDF ToUnicode checks passed\n",checks); return 0;
}
