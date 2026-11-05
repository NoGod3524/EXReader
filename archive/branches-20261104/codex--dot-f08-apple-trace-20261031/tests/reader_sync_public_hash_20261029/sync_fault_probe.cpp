/* Real Android-compiled source-adapter controls, NOT installed Sync runtime.
 * Never define __ANDROID__ artificially. The production TU is included exactly
 * to reach its private digest adapter without changing any production hooks. */
#ifndef __ANDROID__
#error This adapter fixture requires the actual Android toolchain
#endif
#define opds_sha256_stream_create fixture_create
#define opds_sha256_stream_update fixture_update
#define opds_sha256_stream_finish_hex fixture_finish
#define opds_sha256_stream_destroy fixture_destroy
#include SYNC_SOURCE
#undef opds_sha256_stream_create
#undef opds_sha256_stream_update
#undef opds_sha256_stream_finish_hex
#undef opds_sha256_stream_destroy
#include <type_traits>
#include <cstdio>
extern "C" {
opds_sha256_stream_status opds_sha256_stream_create(opds_sha256_stream **);
opds_sha256_stream_status opds_sha256_stream_update(opds_sha256_stream *,const void *,size_t);
opds_sha256_stream_status opds_sha256_stream_finish_hex(opds_sha256_stream *,char [65]);
void opds_sha256_stream_destroy(opds_sha256_stream **);
}
static int fault=0,live=0,destroyed=0;
extern "C" opds_sha256_stream_status fixture_create(opds_sha256_stream **out){
  *out=nullptr;if(fault==1)return OPDS_SHA256_STREAM_MEMORY;
  auto status=opds_sha256_stream_create(out);if(*out)++live;
  return fault==6&&*out?OPDS_SHA256_STREAM_MEMORY:status;
}
extern "C" opds_sha256_stream_status fixture_update(opds_sha256_stream *context,const void *p,size_t n){
  return fault==2?OPDS_SHA256_STREAM_STATE:opds_sha256_stream_update(context,p,n);
}
extern "C" opds_sha256_stream_status fixture_finish(opds_sha256_stream *context,char out[65]){
  if(fault==3){out[0]=0;return OPDS_SHA256_STREAM_STATE;}
  auto status=opds_sha256_stream_finish_hex(context,out);
  if(fault==4)out[64]='x';
  if(fault==5)out[12]='G';
  return status;
}
extern "C" void fixture_destroy(opds_sha256_stream **context){
  if(context&&*context){--live;++destroyed;}opds_sha256_stream_destroy(context);
}
static_assert(!std::is_copy_constructible<digest>::value,"digest must not copy an owner");
static_assert(!std::is_move_constructible<digest>::value,"digest must not move an owner");
int main(){
  const size_t lengths[]={0,3,55,56,63,64,65,65535,65536,65537};
  std::printf("{");bool first=true;
  for(size_t n:lengths){
    std::vector<unsigned char> input(n);for(size_t i=0;i<n;++i)input[i]=(unsigned char)(i%251);
    if(n==3){input[0]='a';input[1]='b';input[2]='c';}
    std::string actual;
    {digest hash;for(size_t offset=0;offset<n;){size_t count=std::min(size_t(65536),n-offset);hash.append(input.data()+offset,count);offset+=count;}
      if(n==0)hash.append(nullptr,0);actual=hash.finish();}
    if(live)return 10;
    std::printf("%s\"%zu\":\"%s\"",first?"":",",n,actual.c_str());first=false;
  }
  std::puts("}");
  for(int selected=1;selected<=6;++selected){
    fault=selected;const int before=destroyed;reader_sync_error error{};
    auto status=call(&error,[]{digest hash;hash.append("abc",3);(void)hash.finish();});
    if(status!=READER_SYNC_IO||error.code!=READER_SYNC_IO||live)return 20+selected;
    if(destroyed-before!=(selected==1?0:1))return 30+selected;
  }
  fault=0;
  reader_sync_error error{};
  auto repeated=call(&error,[]{digest hash;hash.append("abc",3);(void)hash.finish();(void)hash.finish();});
  if(repeated!=READER_SYNC_IO||live)return 40;
  auto invalid=call(&error,[]{digest hash;hash.append(nullptr,1);});
  if(invalid!=READER_SYNC_IO||live)return 41;
  for(uint64_t size:{UINT64_C(0),UINT64_C(128)*1024*1024+1}){
    auto status=call(&error,[&]{(void)hash_file("/path-not-opened-for-size-refusal",size,nullptr);});
    if(status!=READER_SYNC_HASH||live)return 42;
  }
  std::puts("SYNC_ANDROID_ADAPTER_FAULTS_OK");return 0;
}
