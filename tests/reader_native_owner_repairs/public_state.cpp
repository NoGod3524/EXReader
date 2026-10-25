/* Reuse the unchanged public SDK snapshot functions from the complete peer
 * consumer; no SQL connection to the SDK database is introduced. */
#define main original_peer_consumer_main
#include "../reader_windows_raw3/peer-owner/probe.cpp"
#undef main

int main(int argc,char **argv) {
  if(argc!=3) return 2;
  try {
    need(std::getenv("GITHUB_ACTIONS") && std::string(std::getenv("GITHUB_ACTIONS"))=="true","Actions only");
    need(std::getenv("GITHUB_SHA") && std::string(std::getenv("GITHUB_SHA"))==PROBE_SOURCE_SHA,"actual compiled source");
    fs::path profile=fs::u8path(argv[1]),output=fs::u8path(argv[2]);
    auto sdk=sdk_state(profile/"library.sqlite");
    auto product=product_state(profile/"library.sqlite.product.sqlite");
    wchar_t executable[32768];auto size=GetModuleFileNameW(nullptr,executable,32768);
    need(size&&size<32768,"actual executable path");
    auto program=sha(read(fs::path(std::wstring(executable,size))));
    std::ofstream stream(output,std::ios::binary);
    stream<<"{\"source_sha\":"<<quote(PROBE_SOURCE_SHA)<<",\"owner_source_sha256\":"<<quote(PROBE_OWNER_SHA)
      <<",\"program_sha256\":"<<quote(program)<<",\"pid\":"<<GetCurrentProcessId()
      <<",\"sdk_public_state\":"<<quote(sdk)<<",\"product_readonly_state\":"<<quote(product)<<"}\n";
    stream.flush();need(bool(stream),"state report write");
    return 0;
  } catch(const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
