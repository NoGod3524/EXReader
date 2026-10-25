/* Installed native session family used by the GTK account UI. */
#include <reader_session.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>
int main(int argc,char **argv) {
  if(argc!=4 || !std::getenv("GTK_RAW3_DAV_URL") || !std::getenv("GTK_RAW3_DAV_AUTH"))return 2;
  reader_session_config config{};config.product_path=argv[1];config.private_directory=argv[2];config.original_directory=argv[3];
  config.account_id="12345678-1234-4abc-8def-1234567890ab";
  config.dav.root_url=std::getenv("GTK_RAW3_DAV_URL");config.dav.authorization=std::getenv("GTK_RAW3_DAV_AUTH");
  reader_session *session=nullptr;reader_session_snapshot value{};
  if(reader_session_create_raw_v3(&config,&session)!=READER_SESSION_OK || reader_session_start(session)!=READER_SESSION_OK)return 3;
  auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(180);
  do {
    if(reader_session_observe(session,&value)!=READER_SESSION_OK)return 4;
    if(value.state==READER_SESSION_FINISHED || value.state==READER_SESSION_FAILED)break;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }while(std::chrono::steady_clock::now()<deadline);
  bool accepted=value.state==READER_SESSION_FINISHED && value.status==READER_SESSION_OK &&
    value.completed_shards==256 && value.completed_sweeps==1 && !value.full_library_complete;
  auto pulled=value.pulled,originals=value.originals_verified;
  reader_session_request_close(session);
  do {
    reader_session_observe(session,&value);if(value.state==READER_SESSION_CLOSED)break;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }while(std::chrono::steady_clock::now()<deadline);
  accepted=accepted && value.state==READER_SESSION_CLOSED && reader_session_destroy(&session)==READER_SESSION_OK && !session;
  std::printf("{\"accepted\":%s,\"completed_shards\":256,\"completed_sweeps\":1,\"pulled\":%llu,\"originals_verified\":%llu,\"actual_gtk_ui_executed\":false}\n",
    accepted ? "true":"false",static_cast<unsigned long long>(pulled),static_cast<unsigned long long>(originals));
  return accepted ? 0:1;
}
