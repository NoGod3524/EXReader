/* A legitimate independent offline native writer followed by public local revision append.
 * Input is an untouched host-produced pre-conflict catalog; no SQL, invented
 * wire, or application lock modification. Used only on isolated Actions data. */
#include <reader_metadata.h>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
static void need(bool value,const char *message){if(!value)throw std::runtime_error(message);}
int main(int argc,char **argv){try {
  need(argc==5,"seed catalog, target catalog, book key, output directory required");
  std::filesystem::create_directories(argv[4]);
  std::string db=std::string(argv[4])+"/writer.sqlite",pending=db+".pending";
  need(!std::filesystem::exists(db),"writer output must be new");
  std::filesystem::copy_file(argv[1],db);
  reader_metadata_owner *owner=nullptr;reader_metadata_error error{};reader_metadata_result result{};
  need(reader_metadata_open(db.c_str(),pending.c_str(),&owner,&error)==READER_METADATA_OK,"open independent offline writer");
  reader_metadata_snapshot *snapshot=nullptr;
  need(reader_metadata_prepare_book(owner,argv[3],&snapshot,&error)==READER_METADATA_OK,"seed is host-produced unique-head book");
  auto view=reader_metadata_snapshot_view(snapshot);need(view&&view->head_count==1,"seed has exactly one observed parent");
  std::string parent=view->heads[0];reader_book_command input=view->book;
  input.title="Independent native API offline version";input.sort_title=input.title;
  need(reader_metadata_stage_book(owner,snapshot,&input,&result,&error)==READER_METADATA_OK,"stage ordinary offline edit");
  need(reader_metadata_finish_pending(owner,&result,&error)==READER_METADATA_OK&&result.committed&&!result.pending,"commit legitimate offline revision");
  std::string revision=result.command.revision_id;
  reader_metadata_snapshot_free(snapshot);need(reader_metadata_close(&owner,&error)==READER_METADATA_OK,"close offline writer");
  reader_revisions *source=nullptr,*target=nullptr;reader_revision_error re{};reader_revision_info info{};char *wire=nullptr;size_t bytes=0;int created=0;
  need(reader_revisions_open(db.c_str(),&source,&re)==READER_REV_OK,"open native source revisions");
  need(reader_revision_get(source,revision.c_str(),&wire,&bytes,&info,&re)==READER_REV_OK,"read exact API-created wire");

  need(reader_revisions_open(argv[2],&target,&re)==READER_REV_OK,"open second native receiver connection");
  need(reader_revision_local(target,wire,bytes,&info,&created,&re)==READER_REV_OK&&created,"append exact real offline revision and outbox while GTK preview remains open");
  reader_revision_state graph{};
  need(reader_revision_heads(target,"book",argv[3],nullptr,nullptr,&graph,&re)==READER_REV_OK,"inspect resulting graph");
  need(graph.heads==3&&!graph.projection_safe&&!graph.missing_parents&&!graph.foreign_parents,"three complete sibling heads retained");
  reader_revision_bytes_free(wire);
  need(reader_revisions_close(&source,&re)==READER_REV_OK,"close source revisions");
  need(reader_revisions_close(&target,&re)==READER_REV_OK,"close target revisions");
  std::cout<<"{\"writer\":\"installed native metadata API; public local revision append\",\"revision\":\""<<revision<<"\",\"parent\":\""<<parent<<"\",\"sha256\":\""<<info.sha256<<"\",\"heads\":"<<graph.heads<<",\"metadata_version\":\""<<READER_METADATA_VERSION<<"\",\"commands_version\":\""<<READER_COMMANDS_VERSION<<"\",\"revisions_version\":\""<<READER_REVISIONS_VERSION<<"\"}\n";
  return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
