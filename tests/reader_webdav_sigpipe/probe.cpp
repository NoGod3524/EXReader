/* SPDX-License-Identifier: MIT */
#include <exr_webdav.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <string>
#include <thread>
#ifndef _WIN32
#include <pthread.h>
#include <signal.h>
#endif
namespace fs=std::filesystem;
#ifndef _WIN32
static volatile sig_atomic_t handled=0;
static void handler(int){handled=1;}
static bool same_mask(const sigset_t &a,const sigset_t &b){for(int n=1;n<NSIG;n++){if(sigismember(&a,n)!=sigismember(&b,n))return false;}return true;}
#endif
struct callback_state {std::atomic<bool> ready{false},done{false};bool test_other=false;};
static int observe_guard(void *opaque){
  auto &state=*(callback_state *)opaque;
#ifndef _WIN32
  if(state.test_other){sigset_t current{};if(!pthread_sigmask(SIG_SETMASK,nullptr,&current)&&sigismember(&current,SIGPIPE)==1){
    state.ready.store(true);while(!state.done.load())std::this_thread::yield();
  }}
#else
  (void)state;
#endif
  return 0;
}
int main(int argc,char **argv){
  if(argc!=5||!std::getenv("GITHUB_ACTIONS")||std::strcmp(std::getenv("GITHUB_ACTIONS"),"true"))return 2;
  const std::string mode=argv[1],url=argv[2];const fs::path directory=fs::u8path(argv[3]);
  if(mode!="default"&&mode!="handler"&&mode!="pending"&&mode!="blocked")return 2;
  callback_state state;state.test_other=mode=="handler";std::atomic<bool> finished{false};bool masks=true,disposition=true,preserved=true,other=true;
#ifndef _WIN32
  struct sigaction initial{},before{},after{};sigset_t original{},saved{},post{},pipe{};
  if(sigaction(SIGPIPE,nullptr,&initial)||pthread_sigmask(SIG_SETMASK,nullptr,&original))return 3;
  sigemptyset(&pipe);sigaddset(&pipe,SIGPIPE);
  if(mode=="default"&&initial.sa_handler!=SIG_DFL)return 4;
  if(mode=="handler") {struct sigaction action{};action.sa_handler=handler;sigemptyset(&action.sa_mask);if(sigaction(SIGPIPE,&action,nullptr))return 5;}
  if(mode=="pending"||mode=="blocked") {if(pthread_sigmask(SIG_BLOCK,&pipe,nullptr))return 6;if(mode=="pending"&&raise(SIGPIPE))return 7;}
  if(pthread_sigmask(SIG_SETMASK,nullptr,&saved)||sigaction(SIGPIPE,nullptr,&before))return 8;
#endif
  fs::create_directories(directory);exr_webdav_config cfg{};cfg.root_url=url.c_str();cfg.timeout_ms=5000;
  exr_webdav_client *client=nullptr;exr_webdav_error error{};exr_webdav_download result{};
  auto status=exr_webdav_create(&cfg,&client,&error);
  std::thread worker;
#ifndef _WIN32
  if(mode=="handler")worker=std::thread([&]{while(!state.ready.load()&&!finished.load())std::this_thread::yield();if(state.ready.load())pthread_kill(pthread_self(),SIGPIPE);state.done.store(true);});
#endif
  exr_webdav_control control{};control.context=&state;control.cancelled=observe_guard;
  if(status==EXR_DAV_OK)status=exr_webdav_download_file(client,argv[4],directory.u8string().c_str(),"output.epub",&control,&result,&error);
  exr_webdav_free(client);finished.store(true);if(worker.joinable())worker.join();
#ifndef _WIN32
  if(pthread_sigmask(SIG_SETMASK,nullptr,&post)||sigaction(SIGPIPE,nullptr,&after))return 9;
  masks=same_mask(saved,post);disposition=before.sa_handler==after.sa_handler&&before.sa_flags==after.sa_flags&&same_mask(before.sa_mask,after.sa_mask);
  sigset_t pending{};if(sigpending(&pending))return 10;
  if(mode=="pending"){preserved=sigismember(&pending,SIGPIPE)==1;int received=0;if(preserved&&sigwait(&pipe,&received))return 11;preserved=preserved&&received==SIGPIPE;}
  else preserved=sigismember(&pending,SIGPIPE)!=1;
  if(mode=="handler")other=handled==1;
  if(sigaction(SIGPIPE,&initial,nullptr)||pthread_sigmask(SIG_SETMASK,&original,nullptr))return 12;
#endif
  bool clean=fs::is_empty(directory),failed=status!=EXR_DAV_OK&&!result.published&&result.bytes==0;
  bool ok=failed&&clean&&masks&&disposition&&preserved&&other;
  std::cout<<"{\"ok\":"<<(ok?"true":"false")<<",\"status\":"<<(int)status<<",\"published\":"<<result.published
    <<",\"bytes\":"<<result.bytes<<",\"temporary_files_removed\":"<<(clean?"true":"false")
    <<",\"thread_mask_preserved\":"<<(masks?"true":"false")<<",\"process_handler_preserved\":"<<(disposition?"true":"false")
    <<",\"pending_signal_contract\":"<<(preserved?"true":"false")<<",\"other_thread_handler_live\":"<<(other?"true":"false")<<"}"<<std::endl;
  return ok?0:1;
}
