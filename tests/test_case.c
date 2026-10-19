/* SPDX-License-Identifier: MIT */
#include "../src/case_internal.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
static size_t scalars(const char *text,uint32_t *out) {
  size_t n=0;char *end;
  while(*text) { unsigned long cp=strtoul(text,&end,16);if(end==text) break;CHECK(n<64 && cp<=0x10ffff);out[n++]=(uint32_t)cp;text=end; }
  return n;
}
static void mapped(const char *input,unsigned mode,const char *language,const char *expected) {
  uint32_t text[64],want[64],actual[192];size_t count=scalars(input,text),n=scalars(expected,want),i,at=0;
  for(i=0;i<count;i++) at+=exr_case_map(text,count,i,mode,language,actual+at);
  CHECK(at==n && !memcmp(actual,want,n*sizeof(*want)));
}
static void contexts(void) {
  mapped("41 3A3",EXR_CASE_LOWER,"","61 3C2");mapped("41 3A3 42",EXR_CASE_LOWER,"","61 3C3 62");
  mapped("41 301 3A3 301",EXR_CASE_LOWER,"","61 301 3C2 301");mapped("41 3A3 301 42",EXR_CASE_LOWER,"","61 3C3 301 62");
  mapped("345 3A3",EXR_CASE_LOWER,"","345 3C3");mapped("41 3A3 345",EXR_CASE_LOWER,"","61 3C2 345");
  mapped("49 307",EXR_CASE_LOWER,"tr","69");mapped("49 323 307",EXR_CASE_LOWER,"az-AZ","69 323");
  mapped("49 301 307",EXR_CASE_LOWER,"tr","131 301 307");mapped("49 34F 307",EXR_CASE_LOWER,"tr","131 34F 307");
  mapped("130 49 69 131",EXR_CASE_LOWER,"tr-TR","69 131 69 131");mapped("69 131",EXR_CASE_UPPER,"az","130 49");
  mapped("130 49 69 131",EXR_CASE_LOWER,"en","69 307 69 69 131");
  mapped("49 323 301",EXR_CASE_LOWER,"lt","69 307 323 301");mapped("4A 34F 301",EXR_CASE_LOWER,"lt","6A 34F 301");
  mapped("12E 301",EXR_CASE_LOWER,"lt-LT","12F 307 301");mapped("CC CD 128",EXR_CASE_LOWER,"lt","69 307 300 69 307 301 69 307 303");
  mapped("69 323 307",EXR_CASE_UPPER,"lt","49 323");mapped("69 301 307",EXR_CASE_TITLE,"lt","49 301 307");
  mapped("DF FB03",EXR_CASE_UPPER,"de","53 53 46 46 49");mapped("DF FB03",EXR_CASE_TITLE,"de","53 73 46 66 69");
  mapped("41 3A3",EXR_CASE_LITERAL,"tr","41 3A3");
}
static void classification(void) {
  const char *inputs[]={"41 41","61 61","41 61","41 41 61","61 41","4E2D","1C5 61","1C5","345"};
  unsigned expected[]={EXR_CASE_UPPER,EXR_CASE_LOWER,EXR_CASE_TITLE,EXR_CASE_LITERAL,EXR_CASE_LITERAL,EXR_CASE_LITERAL,EXR_CASE_TITLE,EXR_CASE_TITLE,EXR_CASE_LOWER};size_t i;
  for(i=0;i<sizeof(inputs)/sizeof(*inputs);i++) { uint32_t text[64];size_t n=scalars(inputs[i],text),first;CHECK(exr_case_word(text,n,&first)==expected[i]);CHECK(i==5 ? first==SIZE_MAX : first==0); }
}
static int batch(void) {
  char line[1024];
  while(fgets(line,sizeof(line),stdin)) {
    char *mode=strtok(line,";"),*lang=strtok(NULL,";"),*input=strtok(NULL,";\r\n");uint32_t text[64],out[3];size_t n,i;int first=1;
    CHECK(mode && lang && input);n=scalars(input,text);CHECK(atoi(mode)==EXR_CASE_LOWER || atoi(mode)==EXR_CASE_UPPER);
    for(i=0;i<n;i++) { unsigned j,k=exr_case_map(text,n,i,(unsigned)atoi(mode),lang,out);for(j=0;j<k;j++) { printf(first ? "%X" : " %X",out[j]);first=0; } }
    putchar('\n');
  }
  CHECK(!ferror(stdin));return 0;
}
int main(int argc,char **argv) {
  FILE *file;char line[256];size_t records=0;unsigned long previous=0;if(argc==2 && !strcmp(argv[1],"--batch-map")) return batch();CHECK(argc==2);file=fopen(argv[1],"rb");CHECK(file);
  while(fgets(line,sizeof(line),file)) {
    char *cp,*lower,*title,*upper;if(line[0]=='#') continue;
    cp=strtok(line,";");lower=strtok(NULL,";");title=strtok(NULL,";");upper=strtok(NULL,";\r\n");CHECK(cp && lower && title && upper);
    { unsigned long value=strtoul(cp,NULL,16);CHECK(value>previous);previous=value; }
    mapped(cp,EXR_CASE_LOWER,"",lower);mapped(cp,EXR_CASE_TITLE,"",title);mapped(cp,EXR_CASE_UPPER,"",upper);records++;
  }
  CHECK(!ferror(file) && records==3037);fclose(file);contexts();classification();printf("%u Unicode case checks passed (%zu default mappings)\n",checks,records);return 0;
}
