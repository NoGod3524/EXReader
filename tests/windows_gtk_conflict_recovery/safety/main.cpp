/* Actions-only API tests on a COPY of the actual GTK-produced conflict DB.
 * This never supplies revisions or databases to the real-host relay. */
#include <reader_metadata.h>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
static void need(bool value,const char *message){if(!value)throw std::runtime_error(message);}
int main(int argc,char **argv){try {
  need(argc==4,"source product db, book key, output directory required");
  std::filesystem::create_directories(argv[3]);
  for(int scenario=0;scenario<4;scenario++) {
    std::string db=std::string(argv[3])+"/case-"+std::to_string(scenario)+".sqlite",pending=db+".pending";
    std::filesystem::copy_file(argv[1],db,std::filesystem::copy_options::overwrite_existing);
    reader_metadata_owner *owner=nullptr;reader_metadata_error error{};reader_metadata_result result{};
    need(reader_metadata_open(db.c_str(),pending.c_str(),&owner,&error)==READER_METADATA_OK,"open metadata");
    reader_metadata_snapshot *snapshot=nullptr;
    need(reader_metadata_prepare_book(owner,argv[2],&snapshot,&error)==READER_METADATA_CONFLICT,"actual conflict required");
    auto view=reader_metadata_snapshot_view(snapshot);need(view&&view->head_count==2,"exact two real heads");
    reader_book_command input=view->book;input.title="Explicit safety merge";input.sort_title=input.title;
    need(reader_metadata_stage_book(owner,snapshot,&input,&result,&error)==READER_METADATA_CONFLICT,"ordinary edit must remain rejected");
    need(!std::filesystem::exists(pending),"rejected ordinary edit must not stage");
    if(scenario==0) {
      input.source_bytes++;
      need(reader_metadata_stage_book_resolution(owner,snapshot,&input,&result,&error)==READER_METADATA_ARGUMENT,"wrong original identity must reject");
      need(!std::filesystem::exists(pending),"wrong identity must not stage");
    } else {
      if(scenario==3) {
        reader_revisions *other=nullptr;reader_revision_error e{};reader_command_error ce{};reader_command_result cr{};
        need(reader_revisions_open(db.c_str(),&other,&e)==READER_REV_OK,"other native writer open");
        reader_command_context context{other,nullptr,view->heads,view->head_count};
        reader_book_command newer=view->book;newer.title="Concurrent explicit merge";newer.sort_title=newer.title;
        need(reader_command_apply_book(&context,&newer,&cr,&ce)==READER_COMMAND_OK,"newer complete-head command");
        need(reader_revisions_close(&other,&e)==READER_REV_OK,"close writer");
      }
      need(reader_metadata_stage_book_resolution(owner,snapshot,&input,&result,&error)==READER_METADATA_OK,"explicit intent staging");
      if(scenario==1) {
        need(reader_metadata_abandon_pending(owner,&error)==READER_METADATA_OK,"abandon only uncommitted resolution");
        need(!std::filesystem::exists(pending),"abandoned intent cleared");
      } else if(scenario==2) {
        need(reader_metadata_apply_pending(owner,&result,&error)==READER_METADATA_OK&&result.committed&&result.command.created,"first atomic resolution");
        need(reader_metadata_apply_pending(owner,&result,&error)==READER_METADATA_OK&&result.committed&&!result.command.created&&!result.command.applied,"exact retry does not duplicate");
        need(reader_metadata_finish_pending(owner,&result,&error)==READER_METADATA_OK&&!result.pending,"finish retained intent");
      } else {
        need(reader_metadata_finish_pending(owner,&result,&error)==READER_METADATA_CONFLICT&&!result.committed,"stale full heads reject instead of overwriting");
        need(std::filesystem::exists(pending),"stale intent retained for explicit recovery");
      }
    }
    reader_metadata_snapshot_free(snapshot);need(reader_metadata_close(&owner,&error)==READER_METADATA_OK,"close metadata");
    std::cout<<"{\"scenario\":"<<scenario<<",\"passed\":true}\n";
  }
  return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
