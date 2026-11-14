/* SPDX-License-Identifier: MIT */
#include "ppt_internal.h"

#define CFB_FREE UINT32_C(0xffffffff)
#define CFB_END UINT32_C(0xfffffffe)
#define CFB_FAT UINT32_C(0xfffffffd)
#define CFB_DIF UINT32_C(0xfffffffc)
typedef struct {
  const unsigned char *data;
  size_t size,sector_size,sectors,fat_count,mini_count;
  uint32_t *fat,*mini;
  unsigned char *roles,*directory,*root;
  size_t directory_size,root_size;
  unsigned major;
  const exr_control *control;
} cfb;
static unsigned u16(const unsigned char *p) { return p[0]|((unsigned)p[1]<<8); }
static uint32_t u32(const unsigned char *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint64_t stream_size(const cfb *c,const unsigned char *p) {
  uint64_t n=u32(p+120);
  return c->major==3 ? n : n|((uint64_t)u32(p+124)<<32);
}
static exr_status bad(exr_error *e,size_t offset,const char *what) {
  return exr_fail(e,EXR_FORMAT,"CFB %s at offset %zu",what,offset);
}
static exr_status sector(cfb *c,uint32_t id,const unsigned char **out,exr_error *e) {
  uint64_t offset=((uint64_t)id+1)*c->sector_size;
  if(id>=c->sectors || offset>c->size || c->sector_size>c->size-offset)
    return exr_fail(e,EXR_FORMAT,"CFB truncated/invalid sector at offset %llu",(unsigned long long)offset);
  *out=c->data+(size_t)offset;
  return exr_control_cancel(c->control,e);
}
/* Each regular sector has one owner. This also bounds cycles and rejects
   streams aliased onto directory, DIFAT or FAT sectors. */
static exr_status claim(cfb *c,uint32_t id,unsigned role,const unsigned char **p,exr_error *e) {
  exr_status s=sector(c,id,p,e);
  if(s!=EXR_OK) return s;
  if(c->roles[id]) return bad(e,((size_t)id+1)*c->sector_size,"overlapping or cyclic chain");
  c->roles[id]=(unsigned char)role;
  return EXR_OK;
}
static exr_status chain(cfb *c,uint32_t id,size_t length,int directory,unsigned char **out,size_t *out_size,exr_error *e) {
  unsigned char *bytes=NULL;size_t used=0,capacity=0,steps=0;
  exr_status s=EXR_OK;
  *out=NULL;*out_size=0;
  if(length>EXR_PPT_MAX_STREAM) return exr_fail(e,EXR_LIMIT,"CFB stream exceeds 256 MiB");
  if(!directory && length) {
    bytes=malloc(length);
    if(!bytes) return exr_fail(e,EXR_MEMORY,"CFB stream allocation failed");
  }
  while(id!=CFB_END) {
    const unsigned char *p=NULL;size_t take;
    if(++steps>c->sectors || (!directory && used==length)) { s=bad(e,used,"invalid chain length");break; }
    s=claim(c,id,1,&p,e);if(s!=EXR_OK) break;
    if(id>=c->fat_count) { s=bad(e,((size_t)id+1)*c->sector_size,"missing FAT entry");break; }
    take=directory ? c->sector_size : (length-used<c->sector_size ? length-used : c->sector_size);
    if(directory && (used>EXR_PPT_MAX_STREAM-take || !exr_grow((void **)&bytes,&capacity,used+take,1))) {
      s=exr_fail(e,used>EXR_PPT_MAX_STREAM-take ? EXR_LIMIT : EXR_MEMORY,"CFB directory exceeds allocation budget");break;
    }
    memcpy(bytes+used,p,take);used+=take;id=c->fat[id];
  }
  if(s==EXR_OK && !directory && used!=length) s=bad(e,used,"truncated stream chain");
  if(s!=EXR_OK) { free(bytes);return s; }
  *out=bytes;*out_size=used;return EXR_OK;
}
static exr_status load_fat(cfb *c,const unsigned char *h,exr_error *e) {
  uint32_t nf=u32(h+44),nd=u32(h+72),dif=u32(h+68),*ids=NULL;
  size_t i,j,n=0,entries=c->sector_size/4;exr_status s=EXR_OK;
  if(!nf || nf>c->sectors || nd>c->sectors) return bad(e,44,"invalid FAT/DIFAT count");
  if(nf>EXR_PPT_MAX_STREAM/(entries*sizeof(*c->fat))) return exr_fail(e,EXR_LIMIT,"CFB FAT exceeds 256 MiB budget");
  ids=malloc((size_t)nf*sizeof(*ids));
  c->fat=malloc((size_t)nf*entries*sizeof(*c->fat));
  if(!ids || !c->fat) { s=exr_fail(e,EXR_MEMORY,"CFB FAT allocation failed");goto done; }
  c->fat_count=(size_t)nf*entries;
  for(i=0;i<109;i++) {
    uint32_t id=u32(h+76+4*i);
    if(id==CFB_FREE) continue;
    if(n==nf) { s=bad(e,76+4*i,"excess FAT sector");goto done; }
    ids[n++]=id;
  }
  for(i=0;i<nd;i++) {
    const unsigned char *p=NULL;
    s=claim(c,dif,3,&p,e);if(s!=EXR_OK) goto done;
    for(j=0;j<entries-1;j++) {
      uint32_t id=u32(p+4*j);
      if(id==CFB_FREE) continue;
      if(n==nf) { s=bad(e,((size_t)dif+1)*c->sector_size+4*j,"excess DIFAT entry");goto done; }
      ids[n++]=id;
    }
    dif=u32(p+c->sector_size-4);
  }
  if((nd && dif!=CFB_END) || (!nd && dif!=CFB_END && dif!=CFB_FREE) || n!=nf) {
    s=bad(e,68,"invalid DIFAT termination/count");goto done;
  }
  for(i=0;i<n;i++) {
    const unsigned char *p=NULL;
    s=claim(c,ids[i],2,&p,e);if(s!=EXR_OK) goto done;
    for(j=0;j<entries;j++) c->fat[i*entries+j]=u32(p+4*j);
  }
  if(c->fat_count<c->sectors) { s=bad(e,44,"FAT does not cover file");goto done; }
  for(i=0;i<n;i++) if(c->fat[ids[i]]!=CFB_FAT) { s=bad(e,44,"invalid FAT sector marker");goto done; }
  for(i=0;i<c->sectors;i++) if(c->roles[i]==3 && c->fat[i]!=CFB_DIF) { s=bad(e,68,"invalid DIFAT sector marker");break; }
done:
  free(ids);return s;
}
static exr_status small_stream(cfb *c,uint32_t id,size_t length,unsigned char **out,size_t *size,exr_error *e) {
  unsigned char *bytes=NULL,*seen=NULL;size_t used=0;exr_status s=EXR_OK;
  *out=NULL;*size=0;
  if(length) {
    bytes=malloc(length);seen=calloc(c->root_size/64+1,1);
    if(!bytes || !seen) { s=exr_fail(e,EXR_MEMORY,"CFB mini stream allocation failed");goto done; }
  }
  while(id!=CFB_END) {
    uint64_t offset=(uint64_t)id*64;size_t take=length-used<64 ? length-used : 64;
    if(!take || id>=c->mini_count || offset>=c->root_size || take>c->root_size-offset || seen[id]) {
      s=exr_fail(e,EXR_FORMAT,"CFB truncated/cyclic mini stream at offset %llu",(unsigned long long)offset);break;
    }
    s=exr_control_cancel(c->control,e);if(s!=EXR_OK) break;
    seen[id]=1;memcpy(bytes+used,c->root+(size_t)offset,take);used+=take;id=c->mini[id];
  }
  if(s==EXR_OK && used!=length) s=bad(e,used,"truncated mini stream");
done:
  free(seen);
  if(s!=EXR_OK) { free(bytes);return s; }
  *out=bytes;*size=used;return EXR_OK;
}
static int name_is(const unsigned char *p,const char *name) {
  size_t i,n=strlen(name);
  if(u16(p+64)!=2*(n+1)) return 0;
  for(i=0;i<n;i++) if(u16(p+2*i)!=(unsigned char)name[i]) return 0;
  return !u16(p+2*n);
}
/* Only the root's child tree denotes top-level streams. Embedded OLE storages
   can contain their own identically named streams and must not be selected. */
static exr_status find_streams(cfb *c,uint32_t *ppt,uint32_t *summary,uint32_t *pictures,exr_error *e) {
  size_t count=c->directory_size/128,top=0,i;uint32_t *stack;
  unsigned char *seen;uint64_t total=0;exr_status s=EXR_OK;
  *ppt=*summary=*pictures=CFB_FREE;
  if(!count || c->directory[66]!=5) return bad(e,0,"missing root directory");
  for(i=0;i<count;i++) {
    const unsigned char *p=c->directory+128*i;unsigned type=p[66],n=u16(p+64);
    if(!(i&1023)) { s=exr_control_cancel(c->control,e);if(s!=EXR_OK) return s; }
    if(!type) continue;
    if((type!=1 && type!=2 && type!=5) || n<2 || n>64 || (n&1) || u16(p+n-2)) return bad(e,128*i,"invalid directory entry");
    if(type==2) {
      uint64_t size=stream_size(c,p);
      if(size>EXR_PPT_MAX_STREAM || total>EXR_PPT_MAX_STREAM-size) return exr_fail(e,EXR_LIMIT,"CFB total stream size exceeds 256 MiB");
      total+=size;
    }
  }
  stack=malloc(count*sizeof(*stack));seen=calloc(count,1);
  if(!stack || !seen) { free(stack);free(seen);return exr_fail(e,EXR_MEMORY,"CFB directory tree allocation failed"); }
  stack[top++]=u32(c->directory+76);
  while(top) {
    uint32_t id=stack[--top],left,right;const unsigned char *p;
    if(id==CFB_FREE) continue;
    if(id>=count || !id || seen[id]) { s=bad(e,(size_t)id*128,"invalid/cyclic directory tree");break; }
    seen[id]=1;p=c->directory+128*id;
    if(p[66]!=1 && p[66]!=2) { s=bad(e,128*id,"invalid directory child");break; }
    if(p[66]==2 && name_is(p,"PowerPoint Document")) {
      if(*ppt!=CFB_FREE) { s=bad(e,128*id,"duplicate PowerPoint stream");break; }
      *ppt=id;
    }
    if(p[66]==2 && name_is(p,"\005SummaryInformation")) {
      if(*summary!=CFB_FREE) { s=bad(e,128*id,"duplicate SummaryInformation stream");break; }
      *summary=id;
    }
    if(p[66]==2 && name_is(p,"Pictures")) {
      if(*pictures!=CFB_FREE) { s=bad(e,128*id,"duplicate Pictures stream");break; }
      *pictures=id;
    }
    left=u32(p+68);right=u32(p+72);
    if(top+2>count) { s=bad(e,128*id,"cyclic directory siblings");break; }
    if(left!=CFB_FREE) stack[top++]=left;
    if(right!=CFB_FREE) stack[top++]=right;
  }
  free(stack);free(seen);return s;
}
void exr_ppt_streams_free(exr_ppt_streams *s) {
  free(s->document);free(s->summary);free(s->pictures);memset(s,0,sizeof(*s));
}
exr_status exr_ppt_cfb(const void *data,size_t size,const exr_control *control,exr_ppt_streams *out,exr_error *e) {
  static const unsigned char signature[8]={0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1};
  cfb c={0};const unsigned char *h=data;uint32_t ppt,summary,pictures;unsigned shift;
  unsigned char *mini_bytes=NULL;size_t mini_size=0,i;exr_status s;
  memset(out,0,sizeof(*out));c.data=data;c.size=size;c.control=control;
  if(!data || size<8 || memcmp(data,signature,8)) return bad(e,0,"invalid signature");
  if(size<512) return bad(e,size,"truncated header");
  shift=u16(h+30);c.major=u16(h+26);
  if((shift!=9 && shift!=12) || (c.major!=3 && c.major!=4) || (c.major==3 && shift!=9) ||
     (c.major==4 && shift!=12) || u16(h+28)!=0xfffe || u16(h+32)!=6 || u32(h+56)!=4096)
    return bad(e,26,"unsupported header geometry");
  c.sector_size=(size_t)1<<shift;
  if(size<c.sector_size || size%c.sector_size) return bad(e,size,"truncated sector");
  c.sectors=size/c.sector_size-1;
  if(c.sectors>EXR_PPT_MAX_STREAM/4) return exr_fail(e,EXR_LIMIT,"CFB FAT exceeds 256 MiB budget");
  c.roles=calloc(c.sectors ? c.sectors : 1,1);
  if(!c.roles) return exr_fail(e,EXR_MEMORY,"CFB sector allocation failed");
  s=load_fat(&c,h,e);if(s!=EXR_OK) goto done;
  s=chain(&c,u32(h+48),0,1,&c.directory,&c.directory_size,e);if(s!=EXR_OK) goto done;
  if(c.major==4 && c.directory_size/c.sector_size!=u32(h+40)) { s=bad(e,40,"directory sector count mismatch");goto done; }
  s=find_streams(&c,&ppt,&summary,&pictures,e);if(s!=EXR_OK) goto done;
  if(ppt==CFB_FREE) { s=exr_fail(e,EXR_FORMAT,"不是 PowerPoint 97-2003 文档: missing PowerPoint Document stream");goto done; }
  if(stream_size(&c,c.directory)>EXR_PPT_MAX_STREAM) { s=exr_fail(e,EXR_LIMIT,"CFB root mini stream exceeds 256 MiB");goto done; }
  s=chain(&c,u32(c.directory+116),(size_t)stream_size(&c,c.directory),0,&c.root,&c.root_size,e);if(s!=EXR_OK) goto done;
  if(u32(h+64)>EXR_PPT_MAX_STREAM/c.sector_size) { s=exr_fail(e,EXR_LIMIT,"CFB mini FAT exceeds 256 MiB");goto done; }
  s=chain(&c,u32(h+60),(size_t)u32(h+64)*c.sector_size,0,&mini_bytes,&mini_size,e);if(s!=EXR_OK) goto done;
  c.mini_count=mini_size/4;c.mini=malloc(mini_size ? mini_size : 1);
  if(!c.mini) { s=exr_fail(e,EXR_MEMORY,"CFB mini FAT allocation failed");goto done; }
  for(i=0;i<c.mini_count;i++) c.mini[i]=u32(mini_bytes+4*i);
  for(i=0;i<3;i++) {
    uint32_t id=i==2 ? pictures : i ? summary : ppt;const unsigned char *p;size_t length;
    unsigned char **bytes=i==2 ? &out->pictures : i ? &out->summary : &out->document;
    size_t *n=i==2 ? &out->pictures_size : i ? &out->summary_size : &out->document_size;
    if(id==CFB_FREE) continue;
    p=c.directory+128*id;length=(size_t)stream_size(&c,p);
    s=length<4096 ? small_stream(&c,u32(p+116),length,bytes,n,e) : chain(&c,u32(p+116),length,0,bytes,n,e);
    if(s!=EXR_OK) goto done;
  }
done:
  free(c.fat);free(c.mini);free(c.roles);free(c.directory);free(c.root);free(mini_bytes);
  if(s!=EXR_OK) exr_ppt_streams_free(out);
  return s;
}
