// SPDX-License-Identifier: MIT
// Independent public SDK observer. Never SQL-open the SDK or call a mutator.
#include <exreader.h>
#include <CommonCrypto/CommonDigest.h>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
static void need(bool b,const char *s){if(!b)throw std::runtime_error(s);}
static std::string hex(const void *p,size_t n){const auto *b=(const unsigned char*)p;const char*h="0123456789abcdef";std::string r;for(size_t i=0;i<n;i++){r+=h[b[i]>>4];r+=h[b[i]&15];}return r;}
static std::string field(const char*p){return p?"text:"+hex(p,strlen(p)):"NULL";}
static std::string anchor(const exr_anchor&a){return std::to_string(a.start)+":"+std::to_string(a.end)+":"+field(a.exact)+":"+field(a.prefix)+":"+field(a.suffix)+":"+field(a.chapter);}
int main(int argc,char**argv){exr_library*l=nullptr;try{
 need(argc==2,"existing SDK path argument");need(std::filesystem::is_regular_file(argv[1]),"SDK must already exist");exr_error e{};need(exr_library_open(argv[1],&l,&e)==EXR_OK,e.message);
 exr_book*books=nullptr;size_t count=0;need(exr_library_books(l,nullptr,&books,&count,&e)==EXR_OK,e.message);
 std::cout<<"{\"sdk_version\":\""<<exr_version()<<"\",\"books\":[";
 for(size_t i=0;i<count;i++){const auto&b=books[i];need(b.format==EXR_EPUB,"D17 real EPUB scope only");exr_library_epub_info info{};info.struct_size=sizeof(info);need(exr_library_epub_info_get(l,b.id,&info,&e)==EXR_OK&&info.bounded_storage,"bounded EPUB public mode");
 exr_source src{};need(exr_library_source(l,b.id,&src,&e)==EXR_OK,e.message);CC_SHA256_CTX ctx;CC_SHA256_Init(&ctx);std::vector<unsigned char> buf(65536);uint64_t at=0;while(at<src.size){size_t request=static_cast<size_t>(std::min<uint64_t>(buf.size(),src.size-at));size_t n=src.read_at(src.context,at,buf.data(),request);need(n>0&&n<=request,"stored original short read");CC_SHA256_Update(&ctx,buf.data(),(CC_LONG)n);at+=n;}unsigned char digest[32];CC_SHA256_Final(digest,&ctx);auto size=src.size;src.release(src.context);
 exr_epub_location progress{};int present=0;need(exr_library_epub_progress_get(l,b.id,&progress,&present,&e)==EXR_OK,e.message);std::string p=std::to_string(present)+":"+std::to_string(progress.part)+":"+field(progress.path)+":"+anchor(progress.selector);exr_epub_location_free(&progress);
 exr_epub_note*notes=nullptr;size_t n=0;need(exr_library_epub_notes(l,b.id,&notes,&n,&e)==EXR_OK,e.message);std::string ns;for(size_t j=0;j<n;j++){auto&x=notes[j];ns+=std::to_string(x.id)+":"+std::to_string(x.book_id)+":"+std::to_string(x.location.part)+":"+field(x.text)+":"+field(x.location.path)+":"+anchor(x.location.selector)+";";}exr_epub_notes_free(notes,n);
 if(i)std::cout<<',';std::cout<<"{\"id\":"<<b.id<<",\"format\":"<<b.format<<",\"position\":"<<b.position<<",\"status\":"<<b.status<<",\"favorite\":"<<b.favorite<<",\"title\":\""<<field(b.title)<<"\",\"author\":\""<<field(b.author)<<"\",\"tags\":\""<<field(b.tags)<<"\",\"original_bytes\":"<<size<<",\"original_sha256\":\""<<hex(digest,32)<<"\",\"progress\":\""<<p<<"\",\"notes\":\""<<ns<<"\",\"note_count\":"<<n<<"}";
 }exr_books_free(books,count);exr_library_close(l);std::cout<<"]}\n";return 0;
 }catch(const std::exception&e){exr_library_close(l);std::cerr<<e.what()<<'\n';return 1;}}
