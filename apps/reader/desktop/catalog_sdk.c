/* SPDX-License-Identifier: MIT */
#include "catalog_sdk.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int title_within_limit(const char *text) {
  if(!text) return 0;
  for(size_t i=0;i<=16384;i++) if(!text[i]) return 1;
  return 0;
}
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
typedef struct { BCRYPT_ALG_HANDLE algorithm; BCRYPT_HASH_HANDLE value; } source_hash;
static int hash_begin(source_hash *h) {
  return BCryptOpenAlgorithmProvider(&h->algorithm,BCRYPT_SHA256_ALGORITHM,NULL,0)>=0 &&
    BCryptCreateHash(h->algorithm,&h->value,NULL,0,NULL,0,0)>=0;
}
static int hash_update(source_hash *h,const unsigned char *bytes,size_t size) {
  return BCryptHashData(h->value,(PUCHAR)bytes,(ULONG)size,0)>=0;
}
static int hash_finish(source_hash *h,unsigned char digest[32]) {
  return BCryptFinishHash(h->value,digest,32,0)>=0;
}
static void hash_close(source_hash *h) {
  if(h->value) BCryptDestroyHash(h->value);
  if(h->algorithm) BCryptCloseAlgorithmProvider(h->algorithm,0);
}
static char *title_nfc(const char *text) {
  if(!title_within_limit(text)) return NULL;
  int length=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,NULL,0);
  WCHAR *wide=NULL,*normalized=NULL;char *result=NULL;
  if(length<=0 || length>16385) return NULL;
  wide=calloc((size_t)length,sizeof(*wide));if(!wide) return NULL;
  if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,-1,wide,length)) goto done;
  if(length==1) { result=calloc(1,1);goto done; }
  int capacity=NormalizeString(NormalizationC,wide,length-1,NULL,0);
  if(capacity<0 && GetLastError()==ERROR_INSUFFICIENT_BUFFER) capacity=-capacity;
  for(int attempt=0;attempt<3 && capacity>0 && capacity<=32768;attempt++) {
    free(normalized);normalized=calloc((size_t)capacity+1,sizeof(*normalized));if(!normalized) goto done;
    int used=NormalizeString(NormalizationC,wide,length-1,normalized,capacity);
    if(used<0 && GetLastError()==ERROR_INSUFFICIENT_BUFFER) { capacity=-used;continue; }
    if(used<=0 || used>capacity) goto done;
    normalized[used]=0;
    int bytes=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,normalized,-1,NULL,0,NULL,NULL);
    if(bytes<=0 || bytes>16385) goto done;
    result=malloc((size_t)bytes);
    if(result && !WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,normalized,-1,result,bytes,NULL,NULL)) {
      free(result);result=NULL;
    }
    break;
  }
done:
  free(normalized);free(wide);return result;
}
#else
#include <glib.h>
typedef struct { GChecksum *value; } source_hash;
static int hash_begin(source_hash *h) { h->value=g_checksum_new(G_CHECKSUM_SHA256);return h->value!=NULL; }
static int hash_update(source_hash *h,const unsigned char *bytes,size_t size) {
  g_checksum_update(h->value,bytes,(gssize)size);return 1;
}
static int hash_finish(source_hash *h,unsigned char digest[32]) {
  gsize size=32;g_checksum_get_digest(h->value,digest,&size);return size==32;
}
static void hash_close(source_hash *h) { if(h->value) g_checksum_free(h->value); }
static char *title_nfc(const char *text) {
  if(!title_within_limit(text) || !g_utf8_validate(text,-1,NULL)) return NULL;
  char *normalized=g_utf8_normalize(text,-1,G_NORMALIZE_DEFAULT_COMPOSE),*result=NULL;
  if(normalized) { size_t size=strlen(normalized)+1;result=malloc(size);if(result) memcpy(result,normalized,size); }
  g_free(normalized);return result;
}
#endif

static exr_status fail(exr_error *error,exr_status code,const char *message) {
  if(error) { error->code=code;snprintf(error->message,sizeof(error->message),"%s",message); }
  return code;
}
static int cancelled(const exr_control *control) {
  return control && control->cancelled && control->cancelled(control->context);
}
static const char *format_name(exr_format format) {
  switch(format) {
    case EXR_EPUB:return "epub";case EXR_PDF:return "pdf";case EXR_CBZ:return "cbz";
    case EXR_TXT:return "txt";case EXR_HTML:return "html";case EXR_FB2:return "fb2";
    case EXR_DOCX:return "docx";case EXR_RTF:return "rtf";case EXR_MOBI:return "mobi";
    default:return NULL;
  }
}
exr_status reader_catalog_sdk_original_identity(exr_library *library,int64_t id,const exr_control *control,
                                 char hex[65],uint64_t *bytes,exr_error *error) {
  if(error) memset(error,0,sizeof(*error));
  if(hex) hex[0]=0;
  if(bytes) *bytes=0;
  if(!library || id<=0 || !hex || !bytes) return fail(error,EXR_ARGUMENT,"Missing stored original identity output");
  exr_source source={0};source_hash hash={0};unsigned char digest[32],*buffer=NULL;
  exr_status status=exr_library_source(library,id,&source,error);uint64_t offset=0;
  if(status!=EXR_OK) return status;
  if(!source.read_at || source.size==0 || source.size>INT64_MAX) {
    status=fail(error,EXR_LIMIT,"Invalid stored original size/provider");goto done;
  }
  buffer=malloc(65536);
  if(!buffer) { status=fail(error,EXR_MEMORY,"Source hash buffer allocation failed");goto done; }
  if(!hash_begin(&hash)) { status=fail(error,EXR_IO,"Native SHA-256 initialization failed");goto done; }
  while(offset<source.size) {
    if(cancelled(control)) { status=fail(error,EXR_CANCELLED,"Source identity check cancelled");goto done; }
    size_t request=(size_t)(source.size-offset<65536 ? source.size-offset:65536);
    size_t received=source.read_at(source.context,offset,buffer,request);
    if(received==0 || received>request) { status=fail(error,EXR_IO,"Stored original read failed");goto done; }
    if(!hash_update(&hash,buffer,received)) { status=fail(error,EXR_IO,"Native SHA-256 update failed");goto done; }
    offset+=(uint64_t)received;
  }
  if(cancelled(control)) { status=fail(error,EXR_CANCELLED,"Source identity check cancelled");goto done; }
  if(!hash_finish(&hash,digest)) { status=fail(error,EXR_IO,"Native SHA-256 finalization failed");goto done; }
  for(size_t i=0;i<32;i++) { static const char alphabet[]="0123456789abcdef";hex[i*2]=alphabet[digest[i]>>4];hex[i*2+1]=alphabet[digest[i]&15]; }
  hex[64]=0;*bytes=source.size;
done:
  free(buffer);hash_close(&hash);
  if(source.release) source.release(source.context);
  return status;
}
exr_status reader_catalog_sdk_attach(reader_catalog *catalog,exr_library *library,const exr_book *book,
                                    const exr_control *control,char *key,exr_error *error) {
  char hex[65];uint64_t bytes=0;char *normalized=NULL;const char *location="reflow_global";
  if(error) memset(error,0,sizeof(*error));
  if(key) key[0]=0;
  if(!catalog || !library || !book || book->id<=0) return fail(error,EXR_ARGUMENT,"Missing product/SDK book identity");
  const char *format=format_name(book->format);
  if(!format) return fail(error,EXR_UNSUPPORTED,"Unsupported product book format");
  if(cancelled(control)) return fail(error,EXR_CANCELLED,"Source identity check cancelled");
  exr_status status=reader_catalog_sdk_original_identity(library,book->id,control,hex,&bytes,error);
  if(status!=EXR_OK) return status;
  if(book->format==EXR_PDF || book->format==EXR_CBZ) location="fixed_page";
  else if(book->format==EXR_EPUB) {
    exr_library_epub_info info={0};info.struct_size=sizeof(info);
    status=exr_library_epub_info_get(library,book->id,&info,error);
    if(status!=EXR_OK) return status;
    location=info.bounded_storage ? "epub_chapter":"reflow_global";
  }
  normalized=title_nfc(book->title ? book->title:"");
  if(!normalized) return fail(error,EXR_ENCODING,"Product title NFC conversion failed");
  if(cancelled(control)) { free(normalized);return fail(error,EXR_CANCELLED,"Product mapping cancelled before transaction"); }
  reader_catalog_book record={format,hex,book->title?book->title:"",book->author?book->author:"",
    normalized,location,bytes,book->id,book->favorite};
  reader_catalog_error product_error={0};int result=reader_catalog_attach(catalog,&record,&product_error);
  free(normalized);
  if(result!=0) return fail(error,EXR_DATABASE,product_error.message);
  if(key) snprintf(key,READER_BOOK_KEY_CAPACITY,"%s:%s",format,hex);
  return EXR_OK;
}
exr_status reader_catalog_sdk_repair(reader_catalog *catalog,exr_library *library,const exr_book *books,
                                    size_t count,const exr_control *control,size_t *failed,exr_error *error) {
  exr_status first=EXR_OK;if(error) memset(error,0,sizeof(*error));if(failed) *failed=0;
#ifdef _WIN32
  int repair_prepared=0;
#endif
  if(!catalog || !library || (!books && count)) return fail(error,EXR_ARGUMENT,"Missing catalog repair input");
  for(size_t i=0;i<count;i++) {
    int present=0;reader_catalog_error product_error={0};exr_error current={0};exr_status status;
    if(cancelled(control)) return fail(error,EXR_CANCELLED,"Catalog startup repair cancelled");
    if(reader_catalog_has_local(catalog,books[i].id,&present,&product_error)!=0)
      status=fail(&current,EXR_DATABASE,product_error.message);
    else if(present) continue;
    else {
#ifdef _WIN32
      if(!repair_prepared) { reader_catalog_prepare_repair(catalog);repair_prepared=1; }
#endif
      status=reader_catalog_sdk_attach(catalog,library,&books[i],control,NULL,&current);
    }
    if(cancelled(control)) return fail(error,EXR_CANCELLED,"Catalog repair cancelled at publication boundary");
    if(status==EXR_OK) continue;
    if(failed) ++*failed;
    if(status==EXR_CANCELLED) { if(error) *error=current;return status; }
    if(first==EXR_OK) { first=status;if(error) *error=current; }
  }
  if(cancelled(control)) return fail(error,EXR_CANCELLED,"Catalog repair cancelled after final book");
  return first;
}
