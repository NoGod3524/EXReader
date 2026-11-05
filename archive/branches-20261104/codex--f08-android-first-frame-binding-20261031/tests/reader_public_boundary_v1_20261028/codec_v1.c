/* SPDX-License-Identifier: MIT */
#include <reader_selector_bytes_v1.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)){fprintf(stderr,"FAIL %u line %d: %s\n",checks,__LINE__,#x);return 1;} } while(0)
int main(void) {
  size_t n=99;
  char out[256], decoded[256];
  const char bytes[]={'a',0,'b'};
  const char *invalid[]={"!!==","AA A","AA\nA","AA-_","A===","AA=A","AAA","AAAA=","AB==","AAB="};
  size_t i;
  CHECK(!strcmp(READER_REV_SELECTOR_BYTES_API_VERSION,"1.0.0"));
  memset(out,'!',sizeof(out));memset(decoded,'!',sizeof(decoded));
  CHECK(reader_revision_selector_encode_v1(bytes,3,NULL,0,&n)==READER_SELECTOR_V1_OK&&n==4);
  CHECK(reader_revision_selector_encode_v1(bytes,3,out,3,&n)==READER_SELECTOR_V1_BUFFER&&n==4&&out[0]=='!');
  CHECK(reader_revision_selector_encode_v1(bytes,3,out,4,&n)==READER_SELECTOR_V1_OK&&n==4&&!memcmp(out,"YQBi",4)&&out[4]=='!');
  CHECK(reader_revision_selector_decode_v1(out,4,3,3,3,decoded,3,&n)==READER_SELECTOR_V1_OK&&n==3&&!memcmp(decoded,bytes,3)&&decoded[3]=='!');
  CHECK(reader_revision_selector_decode_v1(out,4,3,3,2,decoded,3,&n)==READER_SELECTOR_V1_FORMAT&&n==0);
  CHECK(reader_revision_selector_decode_v1(out,4,3,2,3,decoded,3,&n)==READER_SELECTOR_V1_LIMIT&&n==0);
  CHECK(reader_revision_selector_decode_v1(out,4,3,3,3,NULL,0,&n)==READER_SELECTOR_V1_OK&&n==3);
  memset(decoded,'!',sizeof(decoded));
  CHECK(reader_revision_selector_decode_v1(out,4,3,3,3,decoded,2,&n)==READER_SELECTOR_V1_BUFFER&&n==3&&decoded[0]=='!');
  CHECK(reader_revision_selector_encode_v1(NULL,0,NULL,0,&n)==READER_SELECTOR_V1_OK&&n==0);
  CHECK(reader_revision_selector_encode_v1(NULL,0,out,0,&n)==READER_SELECTOR_V1_OK&&n==0);
  CHECK(reader_revision_selector_decode_v1(NULL,0,0,0,0,decoded,0,&n)==READER_SELECTOR_V1_OK&&n==0);
  CHECK(reader_revision_selector_decode_v1(NULL,0,1,1,1,NULL,0,&n)==READER_SELECTOR_V1_FORMAT&&n==0);
  CHECK(reader_revision_selector_encode_v1(NULL,1,out,sizeof(out),&n)==READER_SELECTOR_V1_ARGUMENT&&n==0);
  CHECK(reader_revision_selector_decode_v1(NULL,4,1,1,1,decoded,sizeof(decoded),&n)==READER_SELECTOR_V1_ARGUMENT&&n==0);
  CHECK(reader_revision_selector_encode_v1(bytes,3,NULL,1,&n)==READER_SELECTOR_V1_ARGUMENT&&n==0);
  CHECK(reader_revision_selector_decode_v1("YQ==",4,1,1,1,NULL,1,&n)==READER_SELECTOR_V1_ARGUMENT&&n==0);
  CHECK(reader_revision_selector_encode_v1(bytes,3,out,sizeof(out),NULL)==READER_SELECTOR_V1_ARGUMENT);
  CHECK(reader_revision_selector_encode_v1(bytes,SIZE_MAX,NULL,0,&n)==READER_SELECTOR_V1_LIMIT&&n==0);
  CHECK(reader_revision_selector_decode_v1("",0,SIZE_MAX,SIZE_MAX,SIZE_MAX,NULL,0,&n)==READER_SELECTOR_V1_LIMIT&&n==0);
  for(i=0;i<sizeof(invalid)/sizeof(invalid[0]);++i){
    CHECK(reader_revision_selector_decode_v1(invalid[i],strlen(invalid[i]),1,128,32,decoded,sizeof(decoded),&n)!=READER_SELECTOR_V1_OK&&n==0&&decoded[0]=='!');
  }
  { const char *bad_utf8[]={"/w==","wIA=","7aCA","9JCAgA==","4g=="};
    const size_t sizes[]={1,2,3,4,1};
    for(i=0;i<5;++i)CHECK(reader_revision_selector_decode_v1(bad_utf8[i],strlen(bad_utf8[i]),sizes[i],128,32,decoded,sizeof(decoded),&n)==READER_SELECTOR_V1_FORMAT&&n==0);
  }
  CHECK(reader_revision_selector_decode_v1("AA==",4,1,1,1,decoded,1,&n)==READER_SELECTOR_V1_OK&&n==1&&decoded[0]==0);
  { char context[129];memset(context,'a',sizeof(context));
    CHECK(reader_revision_selector_encode_v1(context,33,out,sizeof(out),&n)==READER_SELECTOR_V1_OK);
    CHECK(reader_revision_selector_decode_v1(out,n,33,128,32,decoded,sizeof(decoded),&n)==READER_SELECTOR_V1_FORMAT&&n==0);
    CHECK(reader_revision_selector_encode_v1(context,129,out,sizeof(out),&n)==READER_SELECTOR_V1_OK);
    CHECK(reader_revision_selector_decode_v1(out,n,129,128,SIZE_MAX,decoded,sizeof(decoded),&n)==READER_SELECTOR_V1_LIMIT&&n==0);
  }
  printf("PUBLIC_CODEC_V1 checks=%u passed=true\n",checks);return 0;
}
