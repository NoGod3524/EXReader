/* SPDX-License-Identifier: MIT */
#include "pdf_crypto.h"
void exr_pdf_secret_clear(void *data,size_t size) {
  volatile unsigned char *p=data; while(size--) *p++=0;
}
#ifdef EXR_ENABLE_PDF_CRYPTO
#include <mbedtls/aes.h>
#include <mbedtls/md5.h>
#include <mbedtls/sha256.h>
#include <mbedtls/sha512.h>
#include <mbedtls/constant_time.h>
#include "pdf_saslprep_data.h"

static unsigned prep_flag(uint32_t cp) {
  size_t lo=0,hi=sizeof(prep_flags)/sizeof(*prep_flags);
  while(lo<hi) { size_t m=lo+(hi-lo)/2; if(cp<prep_flags[m].first) hi=m; else if(cp>prep_flags[m].last) lo=m+1; else return prep_flags[m].flags; }
  return 0;
}
static unsigned combining(uint32_t cp) {
  size_t lo=0,hi=sizeof(prep_combining)/sizeof(*prep_combining);
  while(lo<hi) { size_t m=lo+(hi-lo)/2; if(cp<prep_combining[m].cp) hi=m; else if(cp>prep_combining[m].cp) lo=m+1; else return prep_combining[m].value; }
  return 0;
}
static uint32_t compose(uint32_t a,uint32_t b) {
  size_t lo=0,hi=sizeof(prep_compose)/sizeof(*prep_compose);
  if(a>=0x1100 && a<0x1113 && b>=0x1161 && b<0x1176) return 0xac00+(a-0x1100)*588+(b-0x1161)*28;
  if(a>=0xac00 && a<=0xd7a3 && (a-0xac00)%28==0 && b>0x11a7 && b<0x11c3) return a+b-0x11a7;
  while(lo<hi) {
    size_t m=lo+(hi-lo)/2;
    if(a<prep_compose[m].first || (a==prep_compose[m].first && b<prep_compose[m].second)) hi=m;
    else if(a>prep_compose[m].first || b>prep_compose[m].second) lo=m+1;
    else return prep_compose[m].result;
  }
  return 0;
}
/* RFC 4013 stored-string profile, Unicode 3.2 NFKC, then ISO 32000's
   127-byte truncation. No locale/system Unicode dependency. */
static exr_status prepare(const unsigned char *input,size_t size,unsigned char output[127],size_t *length,exr_error *e) {
  uint32_t *cp; size_t count=0,at=0,i,j,n=0,starter=0,work=0; unsigned last=0,bidi=0;
  exr_status status=EXR_OK; *length=0;
  cp=malloc((size+1)*18*sizeof(*cp)); if(!cp) return exr_fail(e,EXR_MEMORY,"PDF password normalization allocation failed");
  while(at<size) {
    uint32_t c,parts[3]; unsigned f; const uint32_t *d=&c; size_t dn=1,lo=0,hi=sizeof(prep_decomp)/sizeof(*prep_decomp);
    if(!exr_next((const char *)input,size,&at,&c)) { status=exr_fail(e,EXR_ENCODING,"PDF password is not UTF-8"); goto done; }
    f=prep_flag(c); if(f&1) continue; if(f&2) c=32;
    if(c>=0xac00 && c<=0xd7a3) {
      uint32_t s=c-0xac00; parts[0]=0x1100+s/588; parts[1]=0x1161+(s%588)/28; parts[2]=0x11a7+s%28; d=parts; dn=s%28 ? 3 : 2;
    } else while(lo<hi) {
      size_t m=lo+(hi-lo)/2;
      if(c<prep_decomp[m].cp) hi=m; else if(c>prep_decomp[m].cp) lo=m+1;
      else { d=prep_scalars+prep_decomp[m].offset; dn=prep_decomp[m].length; break; }
    }
    for(i=0;i<dn;i++) {
      unsigned cc=combining(d[i]); j=count++;
      while(j && cc && combining(cp[j-1])>cc) {
        if(++work>1048576) { status=exr_fail(e,EXR_LIMIT,"PDF password normalization work budget exceeded"); goto done; }
        cp[j]=cp[j-1]; j--;
      }
      cp[j]=d[i];
    }
  }
  for(i=0;i<count;i++) {
    unsigned cc=combining(cp[i]); uint32_t composed=n && (!last || last<cc) ? compose(cp[starter],cp[i]) : 0;
    if(composed) cp[starter]=composed;
    else { if(!cc) starter=n; cp[n++]=cp[i]; last=cc; }
  }
  for(i=0;i<n;i++) {
    unsigned f=prep_flag(cp[i]); char bytes[4]; size_t k=0; uint32_t c=cp[i];
    if(f&4) { status=exr_fail(e,EXR_ENCODING,"PDF password contains a prohibited SASLprep character"); goto done; }
    bidi|=f&(8|16);
    if(c<128) bytes[k++]=(char)c;
    else if(c<0x800) { bytes[k++]=(char)(0xc0|(c>>6)); bytes[k++]=(char)(0x80|(c&63)); }
    else if(c<0x10000) { bytes[k++]=(char)(0xe0|(c>>12)); bytes[k++]=(char)(0x80|((c>>6)&63)); bytes[k++]=(char)(0x80|(c&63)); }
    else { bytes[k++]=(char)(0xf0|(c>>18)); bytes[k++]=(char)(0x80|((c>>12)&63)); bytes[k++]=(char)(0x80|((c>>6)&63)); bytes[k++]=(char)(0x80|(c&63)); }
    for(j=0;j<k && *length<127;j++) output[(*length)++]=(unsigned char)bytes[j];
  }
  if((bidi&8) && ((bidi&16) || !(prep_flag(cp[0])&8) || !(prep_flag(cp[n-1])&8)))
    status=exr_fail(e,EXR_ENCODING,"PDF password violates SASLprep bidirectional rules");
done:
  exr_pdf_secret_clear(cp,(size+1)*18*sizeof(*cp)); free(cp); return status;
}

static const unsigned char padding[32]={0x28,0xbf,0x4e,0x5e,0x4e,0x75,0x8a,0x41,0x64,0,0x4e,0x56,0xff,0xfa,1,8,0x2e,0x2e,0,0xb6,0xd0,0x68,0x3e,0x80,0x2f,0x0c,0xa9,0xfe,0x64,0x53,0x69,0x7a};
/* The following ARC4 key schedule and byte loop adapt Mbed TLS 2.28.10
   library/arc4.c, Copyright The Mbed TLS Contributors, Apache-2.0 selected.
   Only for decrypting legacy PDF R2-4; no encryption/writing API. */
static exr_status rc4(const unsigned char *key,size_t key_size,unsigned char *data,size_t size,const exr_control *control,exr_error *e) {
  unsigned char m[256]; unsigned x=0,y=0,a,b,j=0; size_t i; exr_status status=EXR_OK;
  for(i=0;i<256;i++) m[i]=(unsigned char)i;
  for(i=0;i<256;i++) { a=m[i]; j=(j+a+key[i%key_size])&255; m[i]=m[j]; m[j]=(unsigned char)a; }
  for(i=0;i<size;i++) {
    if(!(i&65535) && (status=exr_control_cancel(control,e))!=EXR_OK) break;
    x=(x+1)&255; a=m[x]; y=(y+a)&255; b=m[y]; m[x]=(unsigned char)b; m[y]=(unsigned char)a;
    data[i]^=m[(a+b)&255];
  }
  exr_pdf_secret_clear(m,sizeof(m)); return status;
}
typedef struct { const void *data; size_t size; } crypt_part;
static int md5_parts(const crypt_part *parts,size_t count,unsigned char out[16]) {
  mbedtls_md5_context ctx; size_t i; int result; mbedtls_md5_init(&ctx); result=mbedtls_md5_starts(&ctx);
  for(i=0;i<count && !result;i++) result=mbedtls_md5_update(&ctx,parts[i].data,parts[i].size);
  if(!result) result=mbedtls_md5_finish(&ctx,out);
  mbedtls_md5_free(&ctx); return result;
}
static void pad(const unsigned char *password,size_t size,unsigned char out[32]) {
  if(size>32) size=32;
  if(size) memcpy(out,password,size);
  memcpy(out+size,padding,32-size);
}
static int legacy_user(exr_pdf_crypt *c,const unsigned char *password,size_t size,const unsigned char owner[32],
  const unsigned char user[32],const unsigned char *id,size_t id_size) {
  unsigned char p[32],permissions[4],hash[16],test[32],key[16],ff[4]={255,255,255,255}; unsigned i,j; int result;
  crypt_part parts[5]; pad(password,size,p);
  for(i=0;i<4;i++) permissions[i]=(unsigned char)(c->permissions>>(8*i));
  parts[0]=(crypt_part){p,32}; parts[1]=(crypt_part){owner,32}; parts[2]=(crypt_part){permissions,4};
  parts[3]=(crypt_part){id,id_size}; parts[4]=(crypt_part){ff,c->revision>=4 && !c->metadata ? 4 : 0};
  result=md5_parts(parts,5,hash);
  for(i=0;i<50 && c->revision>=3 && !result;i++) result=mbedtls_md5(hash,c->length,hash);
  if(result) goto done;
  memcpy(c->key,hash,c->length);
  if(c->revision==2) { memcpy(test,padding,32); rc4(c->key,c->length,test,32,NULL,NULL); }
  else {
    parts[0]=(crypt_part){padding,32}; parts[1]=(crypt_part){id,id_size}; result=md5_parts(parts,2,test);
    if(result) goto done;
    for(i=0;i<20;i++) { for(j=0;j<c->length;j++) key[j]=c->key[j]^(unsigned char)i; rc4(key,c->length,test,16,NULL,NULL); }
  }
  result=mbedtls_ct_memcmp(test,user,c->revision==2 ? 32 : 16) ? 1 : 0;
done:
  exr_pdf_secret_clear(p,sizeof(p)); exr_pdf_secret_clear(hash,sizeof(hash)); exr_pdf_secret_clear(test,sizeof(test)); exr_pdf_secret_clear(key,sizeof(key));
  return result;
}
static exr_status legacy_auth(exr_pdf_crypt *c,const unsigned char *password,size_t size,const unsigned char *o,const unsigned char *u,
  const unsigned char *id,size_t id_size,exr_error *e) {
  unsigned char p[32],hash[16],key[16],decoded[32]; unsigned i,j; int result;
  /* Try owner first when the same password authenticates both roles. */
  pad(password,size,p); result=mbedtls_md5(p,32,hash);
  for(i=0;i<50 && c->revision>=3 && !result;i++) result=mbedtls_md5(hash,16,hash);
  memcpy(decoded,o,32);
  if(!result) for(i=c->revision==2 ? 1 : 20;i>0;i--) {
    for(j=0;j<c->length;j++) key[j]=hash[j]^(unsigned char)(i-1);
    rc4(key,c->length,decoded,32,NULL,NULL);
  }
  if(!result && !legacy_user(c,decoded,32,o,u,id,id_size)) c->owner=1;
  else result=legacy_user(c,password,size,o,u,id,id_size);
  exr_pdf_secret_clear(p,sizeof(p)); exr_pdf_secret_clear(hash,sizeof(hash)); exr_pdf_secret_clear(key,sizeof(key)); exr_pdf_secret_clear(decoded,sizeof(decoded));
  return result ? exr_fail(e,EXR_PASSWORD,"PDF password required or incorrect") : EXR_OK;
}
static int aes_cbc(const unsigned char *key,unsigned bits,int encrypt,unsigned char iv[16],unsigned char *data,size_t size) {
  mbedtls_aes_context ctx; int result; mbedtls_aes_init(&ctx);
  result=encrypt ? mbedtls_aes_setkey_enc(&ctx,key,bits) : mbedtls_aes_setkey_dec(&ctx,key,bits);
  if(!result) result=mbedtls_aes_crypt_cbc(&ctx,encrypt ? MBEDTLS_AES_ENCRYPT : MBEDTLS_AES_DECRYPT,size,iv,data,data);
  mbedtls_aes_free(&ctx); return result;
}
static exr_status modern_hash(unsigned revision,const unsigned char *password,size_t size,const unsigned char salt[8],
  const unsigned char *user,unsigned char out[32],const exr_control *control,exr_error *e) {
  unsigned char block[64*(127+64+48)],k[64],iv[16]; size_t us=user ? 48 : 0,n=size+8+us,kn=32,round,i; int result;
  exr_status status=EXR_OK;
  memcpy(block,password,size); memcpy(block+size,salt,8); if(us) memcpy(block+size+8,user,us);
  result=mbedtls_sha256(block,n,k,0);
  if(revision>=6) for(round=0;!result && round<288;round++) {
    unsigned sum=0; status=exr_control_cancel(control,e); if(status!=EXR_OK) goto done;
    n=size+kn+us; memcpy(block,password,size); memcpy(block+size,k,kn); if(us) memcpy(block+size+kn,user,us);
    for(i=1;i<64;i++) memcpy(block+i*n,block,n);
    memcpy(iv,k+16,16); result=aes_cbc(k,128,1,iv,block,n*64); if(result) break;
    for(i=0;i<16;i++) sum+=block[i];
    if(sum%3==0) { kn=32; result=mbedtls_sha256(block,n*64,k,0); }
    else { kn=sum%3==1 ? 48 : 64; result=mbedtls_sha512(block,n*64,k,kn==48); }
    if(round>=63 && block[n*64-1]<=round+1-32) break;
  }
  if(!result) memcpy(out,k,32); else status=exr_fail(e,EXR_FORMAT,"PDF password digest failed");
done:
  exr_pdf_secret_clear(block,sizeof(block)); exr_pdf_secret_clear(k,sizeof(k)); exr_pdf_secret_clear(iv,sizeof(iv)); return status;
}
static exr_status modern_auth(exr_pdf_crypt *c,const unsigned char *password,size_t size,const unsigned char *o,const unsigned char *u,
  const unsigned char *oe,const unsigned char *ue,const unsigned char *perms,const exr_control *control,exr_error *e) {
  unsigned char prepared[127],hash[32],iv[16]={0},plain[16]; size_t n=0; unsigned role,i; exr_status status;
  status=prepare(password,size,prepared,&n,e); if(status!=EXR_OK) goto done;
  for(role=0;role<2;role++) {
    const unsigned char *entry=role ? u : o,*extra=role ? NULL : u;
    status=modern_hash(c->revision,prepared,n,entry+32,extra,hash,control,e); if(status!=EXR_OK) goto done;
    if(mbedtls_ct_memcmp(hash,entry,32)) continue;
    status=modern_hash(c->revision,prepared,n,entry+40,extra,hash,control,e); if(status!=EXR_OK) goto done;
    memcpy(c->key,role ? ue : oe,32);
    if(aes_cbc(hash,256,0,iv,c->key,32)) { status=exr_fail(e,EXR_FORMAT,"PDF encryption key unwrap failed"); goto done; }
    {
      mbedtls_aes_context ctx; int result; mbedtls_aes_init(&ctx); result=mbedtls_aes_setkey_dec(&ctx,c->key,256);
      if(!result) result=mbedtls_aes_crypt_ecb(&ctx,MBEDTLS_AES_DECRYPT,perms,plain);
      mbedtls_aes_free(&ctx);
      if(result) { status=exr_fail(e,EXR_FORMAT,"PDF permissions decryption failed"); goto done; }
    }
    for(i=0;i<4;i++) if(plain[i]!=(unsigned char)(c->permissions>>(8*i)) || plain[i+4]!=255) break;
    if(i!=4 || plain[8]!=(c->metadata ? 'T' : 'F') || memcmp(plain+9,"adb",3)) { status=exr_fail(e,EXR_FORMAT,"PDF encrypted permissions do not match the security dictionary"); goto done; }
    c->owner=!role; status=EXR_OK; goto done;
  }
  status=exr_fail(e,EXR_PASSWORD,"PDF password required or incorrect");
done:
  exr_pdf_secret_clear(prepared,sizeof(prepared)); exr_pdf_secret_clear(hash,sizeof(hash)); exr_pdf_secret_clear(plain,sizeof(plain)); exr_pdf_secret_clear(iv,sizeof(iv)); return status;
}

static exr_status get(exr_pdf_file *f,uint32_t d,const char *name,uint32_t *out,exr_error *e) { return exr_pdf_resolve(f,exr_pdf_get(f,d,name),out,e); }
static int named(exr_pdf_file *f,uint32_t value,const char *name) {
  const exr_pdf_value *v=exr_pdf_value_at(f,value); size_t n; const unsigned char *p=exr_pdf_bytes(f,value,&n);
  return v && v->kind==EXR_PDF_NAME && p && n==strlen(name) && !memcmp(p,name,n);
}
static int number(exr_pdf_file *f,uint32_t d,const char *name,int64_t fallback,int64_t *out,exr_error *e) {
  uint32_t id; const exr_pdf_value *v; if(get(f,d,name,&id,e)!=EXR_OK) return 0;
  v=exr_pdf_value_at(f,id); if(!v) { *out=fallback; return 1; } if(v->kind!=EXR_PDF_INT) return 0; *out=v->u.integer; return 1;
}
static int entry(exr_pdf_file *f,uint32_t d,const char *name,unsigned char *out,size_t size,exr_error *e) {
  uint32_t id; const exr_pdf_value *v; const unsigned char *p; size_t n;
  if(get(f,d,name,&id,e)!=EXR_OK) return 0;
  v=exr_pdf_value_at(f,id); p=exr_pdf_bytes(f,id,&n);
  if(!v || v->kind!=EXR_PDF_STRING || !p || n!=size) return 0;
  memcpy(out,p,n); return 1;
}
exr_status exr_pdf_crypt_filter(exr_pdf_file *f,uint32_t dict,uint32_t name,const exr_pdf_crypt *c,exr_crypt_method *method,exr_error *e) {
  uint32_t cf,id,type,event; char key[128]; const unsigned char *p; size_t n; int64_t length;
  const exr_pdf_value *v=exr_pdf_value_at(f,name); exr_status status;
  *method=EXR_CRYPT_IDENTITY;
  if(!v || v->kind==EXR_PDF_NULL || named(f,name,"Identity")) return EXR_OK;
  if(v->kind!=EXR_PDF_NAME) goto bad;
  p=exr_pdf_bytes(f,name,&n); if(n>=sizeof(key) || memchr(p,0,n)) goto bad;
  memcpy(key,p,n); key[n]=0;
  status=get(f,dict,"CF",&cf,e); if(status!=EXR_OK) return status;
  status=get(f,cf,key,&id,e); if(status!=EXR_OK) return status;
  v=exr_pdf_value_at(f,id); if(!v || v->kind!=EXR_PDF_DICT) goto bad;
  status=get(f,id,"CFM",&type,e); if(status!=EXR_OK) return status;
  if(type==EXR_PDF_NONE || named(f,type,"None")) return EXR_OK;
  if(named(f,type,"V2") && c->version==4) *method=EXR_CRYPT_RC4;
  else if(named(f,type,"AESV2") && c->version==4 && c->length==16) *method=EXR_CRYPT_AES128;
  else if(named(f,type,"AESV3") && c->version==5 && c->length==32) *method=EXR_CRYPT_AES256;
  else return exr_fail(e,EXR_UNSUPPORTED,"Unsupported PDF crypt filter method");
  if(!number(f,id,"Length",c->length,&length,e) || length!=(int64_t)c->length) goto bad;
  status=get(f,id,"AuthEvent",&event,e); if(status!=EXR_OK) return status;
  if(event!=EXR_PDF_NONE && !named(f,event,"DocOpen")) return exr_fail(e,EXR_UNSUPPORTED,"PDF EFOpen crypt filters require an embedded-file authentication session");
  return EXR_OK;
bad:
  return e && e->code!=EXR_OK ? e->code : exr_fail(e,EXR_FORMAT,"Invalid PDF crypt filter dictionary");
}
exr_status exr_pdf_crypt_init(exr_pdf_file *f,uint32_t dict,uint32_t id,const void *password,size_t size,const exr_pdf_crypt *saved,
  const exr_control *control,exr_pdf_crypt *out,exr_error *e) {
  int64_t version,revision,length,permissions; uint32_t value; const exr_pdf_value *v;
  unsigned char o[48],u[48],oe[32],ue[32],perms[16]; const unsigned char *identifier=NULL; size_t id_size=0;
  exr_pdf_crypt c={0}; exr_status status;
  status=get(f,dict,"Filter",&value,e); if(status!=EXR_OK) goto done;
  if(!named(f,value,"Standard")) { status=exr_fail(e,EXR_UNSUPPORTED,"Unsupported PDF security handler (Standard required)"); goto done; }
  if(!number(f,dict,"V",0,&version,e) || !number(f,dict,"R",0,&revision,e) ||
     !number(f,dict,"Length",version==5 ? 256 : 40,&length,e) || !number(f,dict,"P",INT64_MAX,&permissions,e)) goto bad;
  if(!((version==1 && revision==2) || (version==2 && (revision==2 || revision==3)) ||
       (version==4 && revision==4) || (version==5 && (revision==5 || revision==6)))) {
    status=exr_fail(e,EXR_UNSUPPORTED,"Unsupported PDF Standard security version/revision"); goto done;
  }
  if(revision==2) length=40;
  if(length<40 || length%8 || (version==5 ? length!=256 : length>128) || permissions<INT32_MIN || permissions>UINT32_MAX) goto bad;
  c.version=(unsigned)version; c.revision=(unsigned)revision; c.length=(unsigned)length/8; c.permissions=(uint32_t)permissions; c.metadata=1;
  status=get(f,dict,"EncryptMetadata",&value,e); if(status!=EXR_OK) goto done;
  v=exr_pdf_value_at(f,value); if(v) { if(v->kind!=EXR_PDF_BOOL) goto bad; c.metadata=v->u.number!=0; }
  if(!entry(f,dict,"O",o,revision>=5 ? 48 : 32,e) || !entry(f,dict,"U",u,revision>=5 ? 48 : 32,e)) goto bad;
  c.strings=c.streams=c.embedded=EXR_CRYPT_RC4;
  if(version>=4) {
    status=get(f,dict,"StrF",&value,e); if(status==EXR_OK) status=exr_pdf_crypt_filter(f,dict,value,&c,&c.strings,e); if(status!=EXR_OK) goto done;
    status=get(f,dict,"StmF",&value,e); if(status==EXR_OK) status=exr_pdf_crypt_filter(f,dict,value,&c,&c.streams,e); if(status!=EXR_OK) goto done;
    status=get(f,dict,"EFF",&value,e); if(status!=EXR_OK) goto done;
    if(value==EXR_PDF_NONE) c.embedded=c.streams;
    else { status=exr_pdf_crypt_filter(f,dict,value,&c,&c.embedded,e); if(status!=EXR_OK) goto done; }
  }
  if(saved && saved->revision) { c=*saved; status=EXR_OK; goto success; }
  if(revision>=5) {
    if(!entry(f,dict,"OE",oe,32,e) || !entry(f,dict,"UE",ue,32,e) || !entry(f,dict,"Perms",perms,16,e)) goto bad;
    status=modern_auth(&c,password,size,o,u,oe,ue,perms,control,e);
  } else {
    status=exr_pdf_resolve(f,id,&value,e); if(status!=EXR_OK) goto done;
    v=exr_pdf_value_at(f,value); if(!v || v->kind!=EXR_PDF_ARRAY) goto bad;
    value=v->first; status=exr_pdf_resolve(f,value,&value,e); if(status!=EXR_OK) goto done;
    v=exr_pdf_value_at(f,value); identifier=exr_pdf_bytes(f,value,&id_size); if(!v || v->kind!=EXR_PDF_STRING || !identifier || !id_size) goto bad;
    status=legacy_auth(&c,password,size,o,u,identifier,id_size,e);
  }
  if(status!=EXR_OK) goto done;
success:
  *out=c; goto done;
bad:
  status=e && e->code!=EXR_OK ? e->code : exr_fail(e,EXR_FORMAT,"Invalid PDF Standard security dictionary");
done:
  exr_pdf_secret_clear(&c,sizeof(c)); exr_pdf_secret_clear(o,sizeof(o)); exr_pdf_secret_clear(u,sizeof(u));
  exr_pdf_secret_clear(oe,sizeof(oe)); exr_pdf_secret_clear(ue,sizeof(ue)); exr_pdf_secret_clear(perms,sizeof(perms)); return status;
}
exr_status exr_pdf_crypt_bytes(const exr_pdf_crypt *c,exr_crypt_method method,uint32_t object,unsigned generation,
  unsigned char *data,size_t *size,const exr_control *control,exr_error *e) {
  unsigned char key[32]={0},object_key[25],hash[16],iv[16]; size_t kn=c->length,at=0,n=*size; exr_status status=EXR_OK;
  if(method==EXR_CRYPT_IDENTITY) return EXR_OK;
  memcpy(key,c->key,kn);
  if(method!=EXR_CRYPT_AES256) {
    unsigned i; memcpy(object_key,key,kn);
    for(i=0;i<3;i++) object_key[kn+i]=(unsigned char)(object>>(8*i));
    object_key[kn+3]=(unsigned char)generation; object_key[kn+4]=(unsigned char)(generation>>8);
    if(method==EXR_CRYPT_AES128) memcpy(object_key+kn+5,"sAlT",4);
    if(mbedtls_md5(object_key,kn+5+(method==EXR_CRYPT_AES128 ? 4 : 0),hash)) { status=exr_fail(e,EXR_FORMAT,"PDF object key digest failed"); goto done; }
    kn=kn+5<16 ? kn+5 : 16; memcpy(key,hash,kn);
  }
  if(method==EXR_CRYPT_RC4) status=rc4(key,kn,data,n,control,e);
  else {
    mbedtls_aes_context ctx; int result; unsigned padding_byte;
    if(n<32 || n%16) { status=exr_fail(e,EXR_FORMAT,"Invalid encrypted PDF AES payload size"); goto done; }
    memcpy(iv,data,16); mbedtls_aes_init(&ctx); result=mbedtls_aes_setkey_dec(&ctx,key,(unsigned)kn*8);
    at=16;
    while(!result && at<n) {
      size_t chunk=n-at<65536 ? n-at : 65536;
      status=exr_control_cancel(control,e); if(status!=EXR_OK) break;
      result=mbedtls_aes_crypt_cbc(&ctx,MBEDTLS_AES_DECRYPT,chunk,iv,data+at,data+at); at+=chunk;
    }
    mbedtls_aes_free(&ctx); if(status!=EXR_OK) goto done;
    if(result) { status=exr_fail(e,EXR_FORMAT,"PDF AES payload decryption failed"); goto done; }
    padding_byte=data[n-1];
    if(!padding_byte || padding_byte>16) { status=exr_fail(e,EXR_FORMAT,"Invalid encrypted PDF AES padding"); goto done; }
    for(at=n-padding_byte;at<n;at++) if(data[at]!=padding_byte) { status=exr_fail(e,EXR_FORMAT,"Invalid encrypted PDF AES padding"); goto done; }
    *size=n-16-padding_byte; memmove(data,data+16,*size); exr_pdf_secret_clear(data+*size,n-*size);
  }
done:
  if(status!=EXR_OK) exr_pdf_secret_clear(data,n);
  exr_pdf_secret_clear(key,sizeof(key)); exr_pdf_secret_clear(object_key,sizeof(object_key)); exr_pdf_secret_clear(hash,sizeof(hash)); exr_pdf_secret_clear(iv,sizeof(iv)); return status;
}
#else
exr_status exr_pdf_crypt_init(exr_pdf_file *f,uint32_t dict,uint32_t id,const void *password,size_t size,const exr_pdf_crypt *saved,const exr_control *control,exr_pdf_crypt *out,exr_error *e) {
  (void)f; (void)dict; (void)id; (void)password; (void)size; (void)saved; (void)control; (void)out;
  return exr_fail(e,EXR_UNSUPPORTED,"PDF password support is disabled (EXR_ENABLE_PDF_CRYPTO)");
}
exr_status exr_pdf_crypt_filter(exr_pdf_file *f,uint32_t dict,uint32_t name,const exr_pdf_crypt *c,exr_crypt_method *method,exr_error *e) {
  (void)f; (void)dict; (void)name; (void)c; (void)method; return exr_fail(e,EXR_UNSUPPORTED,"PDF crypto disabled");
}
exr_status exr_pdf_crypt_bytes(const exr_pdf_crypt *c,exr_crypt_method method,uint32_t object,unsigned generation,unsigned char *data,size_t *size,const exr_control *control,exr_error *e) {
  (void)c; (void)method; (void)object; (void)generation; (void)data; (void)size; (void)control; return exr_fail(e,EXR_UNSUPPORTED,"PDF crypto disabled");
}
#endif
