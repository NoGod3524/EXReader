/* SPDX-License-Identifier: MIT
 * Fresh installed-only consumer. The host owns the SDK on this thread; the
 * network thread receives no SDK pointer. All product access is public API. */
#include <catalog.h>
#include <exreader.h>
#include <exr/document.h>
#include <exr/library.h>
#include <exr_sideload.h>
#include <exr_webdav.h>
#include <reader_account_profiles.h>
#include <reader_book_information.h>
#include <reader_bulk.h>
#include <reader_cloud_import.h>
#include <reader_jump_history.h>
#include <reader_keyboard_actions.h>
#include <reader_link_policy.h>
#include <reader_sync_view.h>
#include <chrono>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
namespace fs=std::filesystem;
static std::vector<std::string> passed;
static void need(bool ok,const char *name) {
  std::cout<<(ok?"PASS ":"FAIL ")<<name<<std::endl;
  if(!ok)throw std::runtime_error(name);
  passed.emplace_back(name);
}
static std::string json_string(const std::string &s){
  std::string out;
  for(unsigned char c:s){if(c=='"'||c=='\\'){out+='\\';out+=(char)c;}else if(c<32){out+=' ';}else out+=(char)c;}
  return out;
}
static std::string read(const std::string &p){std::ifstream f(fs::u8path(p),std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
struct Back {
  reader_jh *history; reader_revisions *revisions; exr_document *document;
  bool resolved=false; size_t visible_offset=0;
};
static int back(void *p,uint32_t action,const reader_kbd_event*) {
  auto &b=*static_cast<Back*>(p);
  if(action!=READER_KBD_ACTION_BACK)return 0;
  reader_jh_item item{};reader_jh_error je{};reader_rs_record record{};reader_rs_error re{};exr_anchor_match m{};
  bool ok=reader_jh_peek(b.history,READER_JH_BACK,&item,&je)==READER_JH_OK;
  if(ok)ok=reader_rs_decode(b.revisions,item.wire,item.wire_bytes,&record,&re)==READER_RS_OK;
  if(ok)ok=reader_rs_resolve_reflow(b.document,&record,nullptr,&m,&re)==READER_RS_OK&&m.state==EXR_ANCHOR_FOUND;
  if(ok){b.visible_offset=m.start;ok=reader_jh_complete(b.history,&item,&je)==READER_JH_OK;}
  b.resolved=ok;reader_rs_record_free(&record);reader_jh_item_release(&item);return ok?1:0;
}
int main(int argc,char **argv){
  if(argc!=6){std::cerr<<"usage: reviewed-flow WORK ROOT ORIGINAL SHA REPORT\n";return 2;}
  const std::string work=fs::absolute(fs::u8path(argv[1])).u8string(),root=argv[2],original=argv[3],sha=argv[4],report=argv[5];
  bool accepted=false;std::string error;
  try {
    fs::create_directories(fs::u8path(work));
    const std::string profiles=work+"/profiles",staging=work+"/staging";
    fs::create_directories(fs::u8path(profiles));fs::create_directories(fs::u8path(staging));
    reader_account_profile profile{};profile.struct_size=sizeof profile;
    std::strcpy(profile.profile_id,"a1000000-0000-4000-8000-000000000001");
    std::strcpy(profile.account_id,"b1000000-0000-4000-8000-000000000001");
    std::strcpy(profile.root_url,root.c_str());std::strcpy(profile.display_name,"Reviewed composition");
    reader_account_profiles_error ae{};ae.struct_size=sizeof ae;
    need(reader_account_profiles_add(profiles.c_str(),&profile,nullptr,nullptr,&ae)==READER_ACCOUNT_PROFILES_OK,"profile persists non-secret account identity");
    reader_account_profiles_activation plan{};plan.struct_size=sizeof plan;
    need(reader_account_profiles_prepare_activation(profiles.c_str(),profile.profile_id,nullptr,&plan,&ae)==READER_ACCOUNT_PROFILES_OK,"profile prepares isolated shared product paths");
    need(reader_account_profiles_verify_activation(profiles.c_str(),&plan,nullptr,&ae)==READER_ACCOUNT_PROFILES_OK,"profile verifies activation immediately before session creation");
    reader_session_config sc{};sc.product_path=plan.product_path;sc.private_directory=plan.private_directory;
    sc.original_directory=plan.original_directory;sc.account_id=profile.account_id;sc.dav.root_url=root.c_str();
    sc.dav.authorization=std::getenv("READER_TEST_AUTH");sc.dav.timeout_ms=30000;
    reader_session *session=nullptr;
    need(reader_session_create(&sc,&session)==READER_SESSION_OK,"session owns the profile product without borrowing an SDK handle");

    reader_cloud_staged *staged=nullptr;reader_cloud_error ce{};reader_cloud_status downloaded=READER_CLOUD_ARGUMENT;
    const auto owner_thread=std::this_thread::get_id();bool separate_worker=false;
    std::thread network([&]{
      separate_worker=std::this_thread::get_id()!=owner_thread;
      exr_webdav_client *dav=nullptr;exr_webdav_error de{};
      if(exr_webdav_create(&sc.dav,&dav,&de)!=EXR_DAV_OK)return;
      reader_cloud_request request{};reader_cloud_request_init(&request);
      request.resource="incoming.txt";request.display_name="incoming.txt";request.format=EXR_TXT;request.staging_dir=staging.c_str();
      downloaded=reader_cloud_download(dav,&request,&staged,&ce);exr_webdav_free(dav);
    });network.join();
    need(separate_worker&&downloaded==READER_CLOUD_OK&&staged,"cloud download runs on a distinct SDK-free network worker");
    need(sha==reader_cloud_staged_sha256(staged),"download receipt matches independently hashed fixture bytes");
    const uint64_t bytes=reader_cloud_staged_bytes(staged);
    exr_library *library=nullptr;exr_error se{};
    need(exr_library_open((work+"/sdk.sqlite").c_str(),&library,&se)==EXR_OK,"SDK library is opened only on its owner thread");
    reader_cloud_import_options io{};reader_cloud_import_options_init(&io);io.title="Reviewed composition";
    reader_cloud_import_result imported{};imported.struct_size=sizeof imported;
    need(reader_cloud_import(library,&staged,&io,&imported,&ce)==READER_CLOUD_OK&&imported.committed&&imported.book_id>0&&imported.staging_removed&&staged==nullptr,"cloud staged receipt commits through installed sideload on SDK owner");
    const std::string retained=std::string(plan.original_directory)+"/"+sha+".txt";uint64_t written=0;
    need(exr_sideload_export_original(library,imported.book_id,retained.c_str(),nullptr,&written,&se)==EXR_OK&&written==bytes&&read(retained)==read(original),"SDK public original readback equals the downloaded immutable bytes");
    reader_revisions *revisions=nullptr;reader_revision_error re{};reader_catalog *catalog=nullptr;reader_catalog_error ca{};
    need(reader_revisions_open(plan.product_path,&revisions,&re)==READER_REV_OK&&reader_catalog_open(plan.product_path,&catalog,&ca)==0,"public product handles share the session product path on their owner thread");
    const std::string key="txt:"+sha;
    reader_book_command command{};command.operation=READER_COMMAND_PUT;command.book_key=key.c_str();command.format="txt";
    command.source_sha256=sha.c_str();command.source_bytes=bytes;command.title="Reviewed composition";command.author="Composition";command.sort_title="Reviewed composition";
    reader_command_context cc{revisions,nullptr,nullptr,0};reader_command_result cr{};reader_command_error cerror{};
    need(reader_command_apply_book(&cc,&command,&cr,&cerror)==READER_COMMAND_OK&&cr.applied&&cr.created,"existing typed command creates verified metadata history and outbox");
    reader_catalog_book mapped{};mapped.format="txt";mapped.sha256=sha.c_str();mapped.source_bytes=bytes;mapped.title=command.title;mapped.author=command.author;mapped.sort_title=command.sort_title;mapped.sdk_book_id=imported.book_id;mapped.location_kind="reflow_global";
    need(reader_catalog_attach(catalog,&mapped,&ca)==0,"existing public catalog attaches the durable SDK identity without SQL");
    reader_metadata_owner *metadata=nullptr;reader_metadata_error me{};
    need(reader_metadata_open(plan.product_path,(work+"/pending.json").c_str(),&metadata,&me)==READER_METADATA_OK,"metadata owner opens the same shared product");
    reader_bulk *bulk=nullptr;reader_bulk_error be{};
    need(reader_bulk_open(metadata,plan.product_path,(work+"/bulk.json").c_str(),&bulk,&be)==READER_BULK_OK,"bulk borrows the real metadata owner");
    const char *keys[]={key.c_str()};reader_bulk_request request{};request.struct_size=sizeof request;request.action=READER_BULK_FAVORITE_SET;request.book_keys=keys;request.book_count=1;
    reader_bulk_item_result item{};item.struct_size=sizeof item;reader_bulk_summary summary{};
    need(reader_bulk_run(bulk,&request,&item,1,&summary,&be)==READER_BULK_OK&&summary.complete&&summary.committed==1&&item.committed,"bulk favorite commits on the downloaded mapped book");
    need(reader_bulk_acknowledge(bulk,&be)==READER_BULK_OK,"bulk journal acknowledges only its completed transaction");
    reader_bulk_close(&bulk,&be);reader_metadata_close(&metadata,&me);
    reader_book_information *info=nullptr;reader_book_information_error ie{};reader_book_information_options options{};options.struct_size=sizeof options;options.verify_source=1;
    need(reader_book_information_read(catalog,library,key.c_str(),&options,&info,&ie)==READER_BOOK_INFORMATION_OK,"read-only book information snapshots the same owner and book");
    const auto *view=reader_book_information_get(info);
    need(view&&view->favorite==1&&view->availability==READER_BOOK_INFORMATION_LOCAL_PRESENT&&view->identity==READER_BOOK_INFORMATION_IDENTITY_SHA256&&view->verified_sha256&&sha==view->verified_sha256,"book information proves favorite local mapping and exact original identity");
    reader_sync_view_snapshot *status=nullptr;reader_sync_view_error sve{};reader_sync_view_summary sv{};
    need(reader_sync_view_capture(session,revisions,nullptr,&status,&sve)==READER_SYNC_VIEW_OK&&reader_sync_view_summary_get(status,&sv)==READER_SYNC_VIEW_OK&&sv.outbox_included&&sv.pending_records>=2&&!sv.library_complete,"sync status captures the real shared session and retained book outbox");
    const size_t pending_before=sv.pending_records;reader_sync_view_release(&status);
    exr_document *document=nullptr;
    need(exr_library_document(library,imported.book_id,&document,&se)==EXR_OK,"reading opens the cloud-imported document through the same SDK owner");
    size_t text_bytes=0;const char *text=exr_document_text(document,&text_bytes);
    need(text&&text_bytes>1,"reading obtains the real document text");
    reader_jh *history=nullptr;reader_jh_error je{};
    need(reader_jh_open(nullptr,&history,&je)==READER_JH_OK,"history opens without creating another product mapping");
    exr_anchor first{},last{};
    need(exr_anchor_create(document,0,0,&first,&se)==EXR_OK&&exr_anchor_create(document,text_bytes,text_bytes,&last,&se)==EXR_OK,"reading captures two actual SDK positions");
    const std::string parser=std::string("exreader-sdk-")+exr_version();reader_rs_capture capture{};capture.mode=READER_RS_REFLOW_GLOBAL;capture.anchor=&first;
    reader_jh_position position{key.c_str(),parser.c_str(),READER_JH_PAGE,&capture,0};reader_jh_result jr{};
    need(reader_jh_commit(history,revisions,&position,&jr,&je)==READER_JH_OK&&jr.outcome==READER_JH_ADDED,"history stores the first actual reading capture");
    capture.anchor=&last;position.kind=READER_JH_SEARCH;
    need(reader_jh_commit(history,revisions,&position,&jr,&je)==READER_JH_OK&&jr.outcome==READER_JH_ADDED,"history stores a distinct actual landing");
    reader_preferences prefs=reader_preferences_defaults();uint32_t platform=READER_KBD_PLATFORM_LINUX;
#ifdef _WIN32
    platform=READER_KBD_PLATFORM_WINDOWS;
#elif defined(__APPLE__)
    platform=READER_KBD_PLATFORM_APPLE;
#endif
    auto kc=reader_kbd_config_from_preferences(platform,&prefs,0);reader_kbd *kbd=nullptr;
    need(reader_kbd_create(&kc,&kbd)==READER_KBD_OK,"keyboard uses real installed preferences and public configuration");
    reader_kbd_event event{};event.struct_size=sizeof event;event.phase=READER_KBD_PHASE_DOWN;event.key=READER_KBD_KEY_BROWSER_BACK;
    reader_kbd_context context{};context.struct_size=sizeof context;context.focus=READER_KBD_FOCUS_READER;context.window_active=1;reader_kbd_result kr{};kr.struct_size=sizeof kr;
    Back navigation{history,revisions,document,false,text_bytes};
    need(reader_kbd_dispatch(kbd,&event,&context,back,&navigation,&kr)==READER_KBD_OK&&navigation.resolved&&navigation.visible_offset==0&&kr.action==READER_KBD_ACTION_BACK,"keyboard dispatch resolves history publicly before committing the actual back navigation");
    reader_jh_state state{};
    need(reader_jh_state_get(history,&state,&je)==READER_JH_OK&&state.cursor==0&&state.can_forward,"history cursor moves only after FOUND public resolve");
    reader_link_policy *policy=nullptr;reader_link_error le{};le.struct_size=sizeof le;
    need(reader_link_policy_create(nullptr,&policy,&le)==READER_LINK_OK,"external link policy coexists with the active reader owner");
    reader_link_result link{};link.struct_size=sizeof link;const char *url="https://example.com/book";
    need(reader_link_classify(policy,url,std::strlen(url),nullptr,nullptr,&link,&le)==READER_LINK_OK&&link.action==READER_LINK_ACTION_NEEDS_HOST,"external link is classified for host confirmation without opening a site");
    reader_link_result_free(&link);reader_link_policy_destroy(policy);
    need(reader_sync_view_capture(session,revisions,nullptr,&status,&sve)==READER_SYNC_VIEW_OK&&reader_sync_view_summary_get(status,&sv)==READER_SYNC_VIEW_OK&&sv.pending_records==pending_before,"read-only views and history leave the shared outbox unchanged");reader_sync_view_release(&status);
    reader_kbd_destroy(kbd);reader_jh_close(&history,&je);exr_anchor_free(&first);exr_anchor_free(&last);exr_document_free(document);
    reader_catalog_close(&catalog,&ca);reader_revisions_close(&revisions,&re);exr_library_close(library);
    need(view->favorite==1&&sha==view->verified_sha256,"book information snapshot survives all borrowed owner handles");reader_book_information_free(info);
    need(reader_session_start(session)==READER_SESSION_OK,"shared session starts after local product owners finish");
    reader_session_snapshot observed{};auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(240);
    do{reader_session_observe(session,&observed);if(observed.state==READER_SESSION_FINISHED||observed.state==READER_SESSION_FAILED)break;std::this_thread::sleep_for(std::chrono::milliseconds(20));}while(std::chrono::steady_clock::now()<deadline);
    need(observed.state==READER_SESSION_FINISHED&&observed.completed_shards==256&&observed.pushed>=2,"shared session publishes the same favorite history through a complete bounded sweep");
    need(reader_sync_view_capture(session,nullptr,nullptr,&status,&sve)==READER_SYNC_VIEW_OK&&reader_sync_view_summary_get(status,&sv)==READER_SYNC_VIEW_OK&&sv.sweep_complete&&!sv.library_complete,"read-only status reports a completed sweep without claiming complete library sync");reader_sync_view_release(&status);
    need(reader_session_request_close(session)==READER_SESSION_OK,"shared session close is requested explicitly");
    do{reader_session_observe(session,&observed);if(observed.state==READER_SESSION_CLOSED)break;std::this_thread::sleep_for(std::chrono::milliseconds(20));}while(std::chrono::steady_clock::now()<deadline);
    need(observed.state==READER_SESSION_CLOSED&&reader_session_destroy(&session)==READER_SESSION_OK,"shared session reaches CLOSED before destruction");
    accepted=true;
  }catch(const std::exception &e){error=e.what();}
  std::ofstream out(fs::u8path(report));out<<"{\"accepted\":"<<(accepted?"true":"false")<<",\"checks\":[";
  for(size_t i=0;i<passed.size();i++){if(i)out<<',';out<<"{\"name\":\""<<passed[i]<<"\",\"pass\":true}";}
  out<<"],\"failure\":\""<<json_string(error)<<"\",\"host_ui_accepted\":false,\"performance_accepted\":false}\n";
  return accepted?0:1;
}
