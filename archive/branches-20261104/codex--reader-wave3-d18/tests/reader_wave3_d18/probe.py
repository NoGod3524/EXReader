"""Reuse the unchanged public SDK snapshot routine from the existing peer observer.
Only the portability prelude and detailed JSON main are new. No SDK SQL queries.
"""
import subprocess
from common import ROOT, OUT, identity, digest, write

def build(sdk):
    identity()
    original=ROOT/'tests/reader_windows_raw3/peer-owner/probe.cpp'
    text=original.read_text()
    fields=text[text.index('struct Field {'):text.index('struct Input {')]
    library=text[text.index('struct Library {'):text.index('struct Source {')]
    snapshot=text[text.index('void append(std::string'):text.index('/* Product DB only.')]
    assert snapshot.count('return sha(state);')==1
    snapshot=snapshot.replace('return sha(state);','captured=state; return sha(state);')
    prelude=r'''
#include <exreader.h>
#include <CommonCrypto/CommonDigest.h>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <algorithm>
#include <cstdlib>
namespace fs=std::filesystem;
std::string captured;
void need(bool ok,const std::string &s){if(!ok)throw std::runtime_error(s);}
std::string sha(const std::string &s){unsigned char d[CC_SHA256_DIGEST_LENGTH];CC_SHA256(s.data(),(CC_LONG)s.size(),d);std::string h;const char*x="0123456789abcdef";for(auto b:d){h+=x[b>>4];h+=x[b&15];}return h;}
std::string quote(const std::string&s){std::string r="\"";const char*h="0123456789abcdef";for(unsigned char c:s){if(c=='"'||c=='\\'){r+='\\';r+=char(c);}else if(c<32){r+="\\u00";r+=h[c>>4];r+=h[c&15];}else r+=char(c);}return r+'"';}
'''
    main=r'''
int main(int argc,char**argv){try{
 need(argc==2,"snapshot path required");need(std::getenv("GITHUB_ACTIONS")&&std::string(std::getenv("GITHUB_ACTIONS"))=="true","Actions only");
 auto state=sdk_state(fs::path(argv[1]));Library library{fs::path(argv[1])};exr_book *books=nullptr;size_t n=0;exr_error e{};
 need(exr_library_books(library.p,nullptr,&books,&n,&e)==EXR_OK,e.message);
 std::cout<<"{\"sdk_version\":"<<quote(exr_version())<<",\"sdk_sha256\":"<<quote(state)<<",\"sdk_serialized\":"<<quote(captured)<<",\"book_count\":"<<n<<",\"originals\":[";
 for(size_t i=0;i<n;i++){exr_source source{};need(exr_library_source(library.p,books[i].id,&source,&e)==EXR_OK,e.message);need(source.size<=128*1024*1024,"bounded original");std::string bytes((size_t)source.size,'\0');size_t at=0;while(at<bytes.size()){size_t k=source.read_at(source.context,at,&bytes[at],std::min<size_t>(65536,bytes.size()-at));need(k>0&&k<=bytes.size()-at,"source read");at+=k;}if(source.release)source.release(source.context);if(i)std::cout<<',';std::cout<<"{\"id\":"<<books[i].id<<",\"format\":"<<books[i].format<<",\"position\":"<<books[i].position<<",\"bytes\":"<<bytes.size()<<",\"sha256\":"<<quote(sha(bytes))<<"}";}
 exr_books_free(books,n);std::cout<<"]}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
'''
    source=OUT/'public-state.cpp';source.write_text(prelude+fields+library+snapshot+main)
    program=OUT/'public-state'
    subprocess.run(['xcrun','clang++','-std=c++17','-O2','-I'+str(sdk/'include'),str(source),'-L'+str(sdk/'lib'),'-lexreader','-Wl,-rpath,'+str(sdk/'lib'),'-o',str(program)],check=True)
    write(OUT/'public-state-identity.json',dict(**identity(),source_sha256=digest(source),program_sha256=digest(program),reused_source=str(original.relative_to(ROOT)),reused_source_sha256=digest(original),reads='SDK public APIs only on backup; never writes to live library'))
    return program
