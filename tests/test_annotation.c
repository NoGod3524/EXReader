/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error; static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
#define HEAD "{\"@context\":\"http://www.w3.org/ns/anno.jsonld\",\"type\":\"Annotation\","
#define BODY "\"body\":{\"type\":\"TextualBody\",\"value\":\"note\"},"
#define TARGET "\"target\":{\"source\":\"urn:book:chapter\",\"selector\":{\"type\":\"TextQuoteSelector\",\"exact\":\"target\"}}}"
static const char valid[]=HEAD BODY TARGET;
static void bad(const char *json) {
  exr_text_annotation a={0}; CHECK(exr_text_annotation_import(json,strlen(json),&a,&error)!=EXR_OK);
  CHECK(!a.source && !a.text && !a.id && !a.anchor.exact); exr_text_annotation_free(&a);
}
int main(void) {
  exr_document *doc=NULL; exr_text_annotation input={0},a={0}; exr_anchor_match match; char *json=NULL,*again=NULL,*large; size_t size,n,i;
  const char text[]="Before \"target\" \xc3\xa9 \xf0\x9f\x98\x80 after";
  OK(exr_document_open_memory(EXR_TXT,text,strlen(text),&doc,&error));
  OK(exr_anchor_create(doc,7,15,&input.anchor,&error));
  input.id="urn:annotation:1"; input.source="https://example.org/book/chapter.xhtml"; input.text="comment\t\n\r\b\f\\\" \xf0\x9f\x98\x80";
  OK(exr_text_annotation_export(&input,&json,&size,&error)); CHECK(size==strlen(json) && strstr(json,"TextQuoteSelector") && !strstr(json,"start"));
  OK(exr_text_annotation_import(json,size,&a,&error)); CHECK(!strcmp(a.id,input.id) && !strcmp(a.source,input.source) && !strcmp(a.text,input.text) && !strcmp(a.anchor.exact,input.anchor.exact));
  CHECK(a.anchor.start==SIZE_MAX && a.anchor.end==SIZE_MAX && !a.anchor.chapter);
  OK(exr_anchor_resolve(doc,&a.anchor,&match,&error)); CHECK(match.state==EXR_ANCHOR_FOUND && match.start==7 && match.end==15);
  OK(exr_text_annotation_export(&a,&again,&n,&error)); CHECK(n==size && !memcmp(again,json,n)); exr_free(again); exr_free(json); exr_text_annotation_free(&a); exr_anchor_free(&input.anchor); exr_document_free(doc);
  /* Reordered fields, escaped keys, surrogate pairs and unknown metadata. */
  OK(exr_text_annotation_import(valid,sizeof(valid)-1,&a,&error)); CHECK(!strcmp(a.text,"note") && !strcmp(a.anchor.exact,"target")); exr_text_annotation_free(&a);
  { const char escaped[]=HEAD "\"extra\":{\"values\":[true,false,null,-0.2e+3,{},[]]},\"target\":{\"selector\":{\"exact\":\"\\uD83D\\uDE00\",\"type\":\"TextQuoteSelector\"},\"source\":\"urn:book\"},\"body\":{\"v\\u0061lue\":\"\\u4e2d\\u6587\\/\",\"type\":\"TextualBody\"}}";
    OK(exr_text_annotation_import(escaped,sizeof(escaped)-1,&a,&error)); CHECK(!strcmp(a.anchor.exact,"\xf0\x9f\x98\x80") && !strcmp(a.text,"\xe4\xb8\xad\xe6\x96\x87/")); exr_text_annotation_free(&a);
  }
  for(i=1;i<sizeof(valid)-1;i++) { CHECK(exr_text_annotation_import(valid,i,&a,&error)!=EXR_OK); CHECK(!a.source && !a.anchor.exact); }
  bad(HEAD BODY TARGET "trailing"); bad(HEAD "\"type\":\"Annotation\"," BODY TARGET);
  bad(HEAD "\"body\":{\"type\":\"TextualBody\",\"value\":\"\\uD800\"}," TARGET);
  bad(HEAD "\"body\":{\"type\":\"TextualBody\",\"value\":\"\\uDC00\"}," TARGET);
  bad(HEAD "\"body\":{\"type\":\"TextualBody\",\"value\":\"\\u0000\"}," TARGET);
  bad(HEAD "\"body\":{\"type\":\"TextualBody\",\"value\":\"\xff\"}," TARGET);
  bad(HEAD "\"body\":{\"type\":\"TextualBody\",\"format\":\"text/html\",\"value\":\"note\"}," TARGET);
  bad(HEAD "\"body\":[] ," TARGET); bad(HEAD BODY "\"target\":[]}");
  bad(HEAD BODY "\"target\":{\"source\":\"x\",\"scope\":\"other\",\"selector\":{\"type\":\"TextQuoteSelector\",\"exact\":\"x\"}}}");
  bad(HEAD BODY "\"target\":{\"source\":\"x\",\"selector\":{\"type\":\"TextQuoteSelector\",\"exact\":\"x\",\"refinedBy\":{}}}}");
  bad(HEAD BODY "\"target\":{\"@context\":{},\"source\":\"x\",\"selector\":{\"type\":\"TextQuoteSelector\",\"exact\":\"x\"}}}");
  bad(HEAD BODY "\"target\":{\"source\":\"\",\"selector\":{\"type\":\"TextQuoteSelector\",\"exact\":\"x\"}}}");
  bad(HEAD BODY "\"target\":{\"source\":\"x\",\"selector\":{\"type\":\"TextPositionSelector\",\"start\":1,\"end\":2}}}");
  bad(HEAD "\"extra\":01," BODY TARGET); bad(HEAD "\"extra\":1.," BODY TARGET); bad(HEAD "\"extra\":1e+," BODY TARGET); bad(HEAD "\"extra\":[1,]," BODY TARGET);
  large=malloc(1024*1024+2); CHECK(large); memset(large,'x',1024*1024+1); large[1024*1024+1]=0;
  CHECK(exr_text_annotation_import(large,1024*1024+1,&a,&error)==EXR_LIMIT && !a.text);
  input.anchor=(exr_anchor){0}; input.anchor.start=input.anchor.end=SIZE_MAX; input.anchor.exact="quote"; input.text=large;
  CHECK(exr_text_annotation_export(&input,&json,&size,&error)==EXR_ARGUMENT && !json && !size);
  large[200000]=0; memset(large,'\n',200000); input.text=large;
  CHECK(exr_text_annotation_export(&input,&json,&size,&error)==EXR_LIMIT && !json && !size);
  large[0]=0; input.text=large; OK(exr_text_annotation_export(&input,&json,&size,&error)); exr_free(json);
  { size_t at=(size_t)sprintf(large,HEAD "\"extra\":"); for(i=0;i<40;i++) large[at++]='['; large[at++]='0'; for(i=0;i<40;i++) large[at++]=']'; strcpy(large+at,"," BODY TARGET); bad(large); }
  free(large); CHECK(exr_text_annotation_import(NULL,1,&a,&error)==EXR_ARGUMENT); exr_text_annotation_free(NULL);
  printf("%u annotation exchange checks passed\n",checks); return 0;
}
