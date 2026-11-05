/* SPDX-License-Identifier: MIT
 * Public SDK only. TSV: id, text hex, repeat, feature, cancel call,
 * cancel progress byte, feature count override. Same font for every row.
 */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <math.h>
typedef struct {
  uint64_t calls, progress_calls, completed, total, cancel_call, cancel_byte;
  unsigned stage, returned_true;
  uint64_t progress_hash;
} control_state;
static uint64_t mix(uint64_t h,const void *data,size_t size) {
  const unsigned char *p=(const unsigned char *)data;
  while(size--) { h^=*p++; h*=UINT64_C(1099511628211); } return h;
}
static int cancelled(void *p) {
  control_state *s=(control_state *)p; int yes; s->calls++;
  yes=(s->cancel_call && s->calls>=s->cancel_call) ||
      (s->cancel_byte!=UINT64_MAX && s->completed>=s->cancel_byte);
  if(yes) s->returned_true++;
  return yes;
}
static void progress(void *p,exr_stage stage,uint64_t completed,uint64_t total) {
  control_state *s=(control_state *)p; uint64_t n=(uint64_t)stage;
  s->progress_calls++; s->stage=(unsigned)stage; s->completed=completed; s->total=total;
  s->progress_hash=mix(s->progress_hash,&n,sizeof(n));
  s->progress_hash=mix(s->progress_hash,&completed,sizeof(completed));
  s->progress_hash=mix(s->progress_hash,&total,sizeof(total));
}
static int nibble(char c) {
  if(c>='0' && c<='9') return c-'0';
  if(c>='a' && c<='f') return c-'a'+10;
  if(c>='A' && c<='F') return c-'A'+10;
  return -1;
}
static unsigned char *load(const char *path,size_t *size) {
  FILE *f=fopen(path,"rb"); long length; unsigned char *data;
  if(!f || fseek(f,0,SEEK_END) || (length=ftell(f))<0) return NULL;
  rewind(f); *size=(size_t)length; data=(unsigned char *)malloc(*size?*size:1);
  if(!data || fread(data,1,*size,f)!=*size) { fclose(f); free(data); return NULL; }
  fclose(f); return data;
}
static void glyph_json(const exr_shaped_glyph *g) {
  printf("[%" PRIu32 ",%zu,%zu,%.9g,%.9g,%.9g,%.9g,%u]",g->glyph,g->start,g->end,
    (double)g->advance_x,(double)g->advance_y,(double)g->offset_x,(double)g->offset_y,g->flags);
}
int main(int argc,char **argv) {
  exr_font *font=NULL; exr_font_input input={0}; exr_error error={0};
  unsigned char *data; size_t font_size; exr_status created; FILE *requests;
  char *line=(char *)malloc(2*1024*1024);
  if(argc!=3 || !line) { fprintf(stderr,"usage: acceptance FONT REQUESTS.tsv\n"); return 2; }
  data=load(argv[1],&font_size); if(!data) return 3;
  input.data=data; input.size=font_size; created=exr_font_create(&input,1,&font,&error); free(data);
  requests=fopen(argv[2],"rb"); if(!requests) { exr_font_free(font); free(line); return 4; }
  while(fgets(line,2*1024*1024,requests)) {
    char *v[7],*p=line; size_t i,n,repeat,size; char *text;
    exr_shape_options options=exr_shape_defaults(); exr_shape_feature features[257];
    exr_shaped_glyph *out=(exr_shaped_glyph *)(uintptr_t)1; size_t count=999;
    control_state s={0}; exr_status status=created; unsigned finite=1,cleared=1;
    uint64_t hashes[8];
    for(i=0;i<7;i++) { v[i]=p; p=strchr(p,'\t'); if(i<6 && !p) return 5; if(p) *p++=0; }
    v[6][strcspn(v[6],"\r\n")]=0;
    n=strlen(v[1]); if(n%2 || strlen(v[3])!=4) return 6;
    repeat=(size_t)strtoull(v[2],NULL,10); n/=2;
    if(!repeat || n>SIZE_MAX/repeat || n*repeat>128*1024*1024) return 7;
    size=n*repeat; text=(char *)malloc(size?size:1); if(!text) return 8;
    for(i=0;i<n;i++) { int a=nibble(v[1][i*2]),b=nibble(v[1][i*2+1]); if(a<0 || b<0) return 9; text[i]=(char)((a<<4)|b); }
    for(i=1;i<repeat;i++) memcpy(text+i*n,text,n);
    s.cancel_call=strtoull(v[4],NULL,10); s.cancel_byte=!strcmp(v[5],"-1")?UINT64_MAX:strtoull(v[5],NULL,10);
    s.progress_hash=UINT64_C(1469598103934665603);
    options.font_size=20; options.direction=EXR_DIRECTION_LTR; options.script=EXR_TAG('l','a','t','n');
    for(i=0;i<257;i++) { features[i].tag=EXR_TAG('c','0','0','1'+(i%7)); features[i].value=0; }
    for(i=0;i<7;i++) if(features[i].tag==EXR_TAG(v[3][0],v[3][1],v[3][2],v[3][3])) features[i].value=1;
    options.features=features; options.feature_count=strtoull(v[6],NULL,10); if(!options.feature_count) options.feature_count=7;
    if(options.feature_count>257) return 10;
    options.control.cancelled=cancelled; options.control.progress=progress; options.control.context=&s;
    memset(&error,0,sizeof(error));
    if(created==EXR_OK) status=exr_shape(font,0,text,size,&options,&out,&count,&error);
    else { out=NULL; count=0; error.code=created; }
    if(status!=EXR_OK) cleared=(!out && count==0);
    for(i=0;i<8;i++) hashes[i]=UINT64_C(1469598103934665603);
    if(status==EXR_OK) for(i=0;i<count;i++) {
      uint64_t gid=out[i].glyph,start=out[i].start,end=out[i].end,flags=out[i].flags;
      hashes[0]=mix(hashes[0],&gid,sizeof(gid)); hashes[1]=mix(hashes[1],&start,sizeof(start)); hashes[2]=mix(hashes[2],&end,sizeof(end));
      hashes[3]=mix(hashes[3],&out[i].advance_x,sizeof(float)); hashes[4]=mix(hashes[4],&out[i].advance_y,sizeof(float));
      hashes[5]=mix(hashes[5],&out[i].offset_x,sizeof(float)); hashes[6]=mix(hashes[6],&out[i].offset_y,sizeof(float)); hashes[7]=mix(hashes[7],&flags,sizeof(flags));
      if(!isfinite(out[i].advance_x)||!isfinite(out[i].advance_y)||!isfinite(out[i].offset_x)||!isfinite(out[i].offset_y)) finite=0;
    }
    printf("{\"id\":\"%s\",\"create_status\":%d,\"status\":%d,\"error_code\":%d,\"count\":%zu,\"cleared\":%u,\"finite\":%u,\"cancel_calls\":%" PRIu64 ",\"cancel_true\":%u,\"progress_calls\":%" PRIu64 ",\"progress_completed\":%" PRIu64 ",\"progress_total\":%" PRIu64 ",\"progress_stage\":%u,\"progress_hash\":\"%016" PRIx64 "\",\"hashes\":[",v[0],created,status,error.code,count,cleared,finite,s.calls,s.returned_true,s.progress_calls,s.completed,s.total,s.stage,s.progress_hash);
    for(i=0;i<8;i++) printf("%s\"%016" PRIx64 "\"",i?",":"",hashes[i]);
    printf("],\"glyphs\":[");
    if(status==EXR_OK && count<=4096) for(i=0;i<count;i++) { if(i) putchar(','); glyph_json(&out[i]); }
    printf("]}\n"); fflush(stdout);
    if(out && out!=(exr_shaped_glyph *)(uintptr_t)1) exr_free(out);
    free(text);
  }
  fclose(requests); free(line); exr_font_free(font); return 0;
}
