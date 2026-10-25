#include <reader_metadata.h>
#include <filesystem>
#include <string>
int main(int argc,char **argv) {
  if(argc!=3)return 1;
  reader_metadata_owner *owner=nullptr;reader_metadata_error error{};
#ifdef EXR_READER_METADATA_RAW3
  if(std::string(READER_METADATA_VERSION)!="0.2.0")return 2;
  if(reader_metadata_open(argv[1],argv[2],&owner,&error)!=READER_METADATA_ARGUMENT||owner||
     std::filesystem::exists(argv[1]))return 3;
  if(reader_metadata_open_raw_v3(argv[1],argv[2],&owner,&error)!=READER_METADATA_OK||!owner)return 4;
#else
  if(std::string(READER_METADATA_VERSION)!="0.1.0")return 5;
  if(reader_metadata_open(argv[1],argv[2],&owner,&error)!=READER_METADATA_OK||!owner)return 6;
#endif
  return reader_metadata_close(&owner,&error)!=READER_METADATA_OK||owner ? 7:0;
}
