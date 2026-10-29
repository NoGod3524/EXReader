/* Installed public package probe. No source-tree/private headers. */
#include <reader_sync.h>
#include <opds_sha256_stream.h>
#include <cstring>
#include <cstdio>
int main(){
  opds_sha256_stream *hash=nullptr;char out[65]{};
  if(opds_sha256_stream_create(&hash)!=OPDS_SHA256_STREAM_OK)return 1;
  if(opds_sha256_stream_update(hash,"abc",3)!=OPDS_SHA256_STREAM_OK)return 2;
  if(opds_sha256_stream_finish_hex(hash,out)!=OPDS_SHA256_STREAM_OK)return 3;
  opds_sha256_stream_destroy(&hash);
  if(std::strcmp(out,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"))return 4;
  reader_sync *sync=nullptr;reader_sync_error error{};reader_sync_report report{};
  if(reader_sync_create(nullptr,&sync,&error)!=READER_SYNC_ARGUMENT||sync)return 5;
  if(reader_sync_step(nullptr,0,"",1,nullptr,&report,&error)!=READER_SYNC_ARGUMENT)return 6;
#ifdef EXR_READER_SELECTOR_BYTES_CANDIDATE
  if(reader_sync_create_raw_v3(nullptr,&sync,&error)!=READER_SYNC_ARGUMENT||sync)return 7;
  if(reader_sync_step_raw_v3(nullptr,0,"",1,nullptr,&report,&error)!=READER_SYNC_ARGUMENT)return 8;
#endif
  reader_sync_free(sync);
  std::puts("SYNC_INSTALLED_LINK_PROBE_OK");return 0;
}
