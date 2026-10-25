/* SPDX-License-Identifier: MIT */
/* SDK-only half of the reading-state bridge. Only copied selector values leave. */
#include <exr_sideload.h>
#include <exreader.h>
#include <exr/layout.h>
#include <jni.h>
#include <string>
#include <vector>
#include <fstream>
#include <iterator>
#include <cstring>
#include <stdexcept>
namespace {
void sdk(exr_status code){if(code!=EXR_OK)throw std::runtime_error("public SDK refused reading probe");}
std::string argument(JNIEnv *env,jstring value){const char *s=env->GetStringUTFChars(value,nullptr);if(!s)throw std::bad_alloc();std::string copy(s);env->ReleaseStringUTFChars(value,s);return copy;}
std::string quote(const std::string &s){const char *hex="0123456789abcdef";std::string out="\"";for(unsigned char ch:s){if(ch=='"'||ch=='\\')out+='\\';if(ch<32){out+="\\u00";out+=hex[ch>>4];out+=hex[ch&15];}else out+=(char)ch;}return out+'"';}
jbyteArray output(JNIEnv *env,const std::string &s){jbyteArray out=env->NewByteArray((jsize)s.size());if(out)env->SetByteArrayRegion(out,0,(jsize)s.size(),(const jbyte *)s.data());return out;}
struct library {exr_library *p=nullptr;explicit library(const std::string &path){sdk(exr_library_open(path.c_str(),&p,nullptr));}~library(){exr_library_close(p);}};
struct document {exr_document *p=nullptr;~document(){exr_document_free(p);}};
struct publication {exr_publication *p=nullptr;~publication(){exr_publication_free(p);}};
struct font {exr_font *p=nullptr;~font(){exr_font_free(p);}};
struct pager {exr_pager *p=nullptr;~pager(){exr_pager_free(p);}};
struct fixed {exr_fixed_document *p=nullptr;~fixed(){exr_fixed_free(p);}};
struct anchor {exr_anchor p{};~anchor(){exr_anchor_free(&p);}};
struct fixed_anchor {exr_fixed_anchor p{};~fixed_anchor(){exr_fixed_anchor_free(&p);}};
struct fixed_text {exr_fixed_text *p=nullptr;~fixed_text(){exr_fixed_text_free(p);}};
void open_publication(exr_library *lib,int64_t id,publication &pub){exr_source source{};sdk(exr_library_source(lib,id,&source,nullptr));exr_status code=exr_publication_open_source(&source,&pub.p,nullptr);if(code!=EXR_OK)source.release(source.context);sdk(code);}
std::string text_fields(const exr_anchor &a){return "\"start\":"+std::to_string(a.start)+",\"end\":"+std::to_string(a.end)+",\"exact\":"+quote(a.exact?a.exact:"")+",\"prefix\":"+quote(a.prefix?a.prefix:"")+",\"suffix\":"+quote(a.suffix?a.suffix:"")+",\"chapter\":"+(a.chapter?quote(a.chapter):"null");}
size_t locate(const std::string &text,const std::string &needle,size_t occurrence=0){size_t at=0;for(size_t n=0;n<=occurrence;n++){at=text.find(needle,at);if(at==std::string::npos)throw std::runtime_error("fixture quote missing");if(n<occurrence)at+=needle.size();}return at;}
}
extern "C" JNIEXPORT jbyteArray JNICALL Java_org_exreader_sessionprobe_NativeSdk_readingCapture(JNIEnv *env,jclass,jstring database,jlongArray books,jstring font_path){
  try{
    jlong id[5];if(env->GetArrayLength(books)!=5)throw std::runtime_error("five routes required");env->GetLongArrayRegion(books,0,5,id);
    library lib(argument(env,database));std::vector<std::string> rows;
    auto add_text=[&](const std::string &name,const char *role,const char *kind,int mode,int route,size_t part,const char *path,const exr_anchor &a){
      rows.push_back("{\"id\":"+quote(name)+",\"role\":"+quote(role)+",\"kind\":"+quote(kind)+",\"mode\":"+std::to_string(mode)+",\"route\":"+std::to_string(route)+",\"part\":"+std::to_string(part)+",\"part_path\":"+quote(path?path:"")+","+text_fields(a)+"}");
    };
    {
      document doc;sdk(exr_library_document(lib.p,id[0],&doc.p,nullptr));size_t size=0;const char *bytes=exr_document_text(doc.p,&size);std::string text(bytes,size);
      auto add=[&](const char *name,const char *kind,size_t start,size_t end){anchor a;sdk(exr_anchor_create(doc.p,start,end,&a.p,nullptr));add_text(name,"txt",kind,1,0,0,nullptr,a.p);};
      add("txt-progress-start","progress",0,0);size_t emoji=locate(text,"🙂");add("txt-progress-multibyte","progress",emoji,emoji);add("txt-progress-end","progress",size,size);
      size_t point=locate(text,"Tail alpha");add("txt-bookmark","annotation",point,point);add("txt-highlight","annotation",emoji,emoji+std::strlen("🙂"));size_t ambiguous=locate(text,"AMBIGUOUS TARGET",1);add("txt-ambiguous","annotation",ambiguous,ambiguous+std::strlen("AMBIGUOUS TARGET"));
    }
    {
      document doc;sdk(exr_library_document(lib.p,id[4],&doc.p,nullptr));size_t size=0;const char *text=exr_document_text(doc.p,&size);size_t at=locate(std::string(text,size),"第二章节独有文字");
      for(int point=0;point<2;point++){anchor a;sdk(exr_anchor_create(doc.p,at,at+(point?0:std::strlen("第二章节独有文字")),&a.p,nullptr));if(!a.p.chapter||!a.p.chapter[0])throw std::runtime_error("global EPUB scope missing");add_text(point?"epub-global-progress":"epub-global-highlight","epub",point?"progress":"annotation",1,4,0,nullptr,a.p);}
    }
    {
      font f;sdk(exr_font_open(argument(env,font_path).c_str(),&f.p,nullptr));publication pub;open_publication(lib.p,id[1],pub);size_t count=0;const exr_part *parts=exr_publication_parts(pub.p,&count);if(count!=3)throw std::runtime_error("repeated spine fixture missing");
      for(size_t part=0;part<count;part++){pager pg;exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();sdk(exr_publication_pager_create(pub.p,part,f.p,&config,&options,&pg.p,nullptr));anchor a;sdk(exr_pager_anchor_create(pg.p,0,0,nullptr,&a.p,nullptr));add_text("epub-bookmark-part-"+std::to_string(part),"epub","annotation",2,1,part,parts[part].path,a.p);if(part==1)add_text("epub-chapter-progress","epub","progress",2,1,part,parts[part].path,a.p);}
    }
    for(int route=2;route<4;route++){
      fixed doc;exr_fixed_open_options options{};options.struct_size=sizeof(options);sdk(exr_library_fixed(lib.p,id[route],&options,&doc.p,nullptr));size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(doc.p,&count);
      auto add=[&](const char *name,const char *kind,size_t page,size_t start,size_t end){if(page>=count)throw std::runtime_error("fixed route missing");fixed_text text;sdk(exr_fixed_load_text(doc.p,page,nullptr,&text.p,nullptr));fixed_anchor a;sdk(exr_fixed_anchor_create(pages[page].id,text.p,start,end,&a.p,nullptr));rows.push_back("{\"id\":"+quote(name)+",\"role\":"+quote(route==2?"pdf":"cbz")+",\"kind\":"+quote(kind)+",\"mode\":3,\"route\":"+std::to_string(route)+",\"page\":"+std::to_string(page)+",\"page_id\":"+quote(a.p.page_id)+",\"start\":"+std::to_string(a.p.start)+",\"end\":"+std::to_string(a.p.end)+",\"exact\":"+quote(std::string(a.p.exact?a.p.exact:"",a.p.exact_size))+",\"prefix\":"+quote(std::string(a.p.prefix?a.p.prefix:"",a.p.prefix_size))+",\"suffix\":"+quote(std::string(a.p.suffix?a.p.suffix:"",a.p.suffix_size))+"}");};
      if(route==2){fixed_text text;sdk(exr_fixed_load_text(doc.p,0,nullptr,&text.p,nullptr));size_t size=0;const char *bytes=exr_fixed_text_string(text.p,&size);size_t at=locate(std::string(bytes,size),"Shared quote across pages.");add("pdf-highlight","annotation",0,at,at+std::strlen("Shared quote across pages."));add("pdf-bookmark","annotation",0,at,at);add("pdf-textless-bookmark","annotation",2,0,0);add("pdf-progress","progress",1,0,0);}
      else{add("cbz-bookmark","annotation",1,0,0);add("cbz-progress","progress",1,0,0);}
    }
    if(rows.size()!=18)throw std::runtime_error("eighteen captures required");std::string out="{\"parser_version\":"+quote(std::string("exreader-sdk-")+exr_version())+",\"captures\":[";for(size_t i=0;i<rows.size();i++){if(i)out+=',';out+=rows[i];}out+="]}";return output(env,out);
  }catch(...){return nullptr;}
}
extern "C" JNIEXPORT jlong JNICALL Java_org_exreader_sessionprobe_NativeSdk_readingGlobalImport(JNIEnv *env,jclass,jstring database,jstring original){
  try{library lib(argument(env,database));std::ifstream input(argument(env,original),std::ios::binary);if(!input)throw std::runtime_error("original missing");std::string bytes((std::istreambuf_iterator<char>(input)),std::istreambuf_iterator<char>());int64_t id=0;sdk(exr_library_import(lib.p,EXR_EPUB,bytes.data(),bytes.size(),"global",&id,nullptr));return id;}catch(...){return 0;}
}
extern "C" JNIEXPORT jlongArray JNICALL Java_org_exreader_sessionprobe_NativeSdk_readingResolve(JNIEnv *env,jclass,jstring database,jlong book,jint mode,jlong unit,jlong start,jlong end,jobjectArray fields,jstring font_path){
  jlong result[4]={-1,0,0,0};
  try{
    if(start<0||end<start||unit<0||env->GetArrayLength(fields)!=5)throw std::runtime_error("invalid pure selector values");
    std::string s[5];bool chapter=false;
    for(int i=0;i<5;i++){jstring value=(jstring)env->GetObjectArrayElement(fields,i);if(value){s[i]=argument(env,value);if(i==3)chapter=true;env->DeleteLocalRef(value);}}
    library lib(argument(env,database));exr_anchor_match match{};exr_status code=EXR_ARGUMENT;
    if(mode==1||mode==2){
      exr_anchor a{};a.start=(size_t)start;a.end=(size_t)end;a.exact=s[0].data();a.prefix=s[1].data();a.suffix=s[2].data();a.chapter=chapter?s[3].data():nullptr;
      if(mode==1){document doc;sdk(exr_library_document(lib.p,book,&doc.p,nullptr));code=exr_anchor_resolve_ex(doc.p,&a,nullptr,&match,nullptr);}
      else{
        publication pub;open_publication(lib.p,book,pub);size_t count=0;const exr_part *parts=exr_publication_parts(pub.p,&count);if((uint64_t)unit>=count||!parts[unit].path||s[4]!=parts[unit].path)throw std::runtime_error("EPUB index/path mismatch");
        font f;sdk(exr_font_open(argument(env,font_path).c_str(),&f.p,nullptr));pager pg;exr_layout_config config=exr_layout_config_defaults();exr_chapter_options options=exr_chapter_options_defaults();sdk(exr_publication_pager_create(pub.p,(size_t)unit,f.p,&config,&options,&pg.p,nullptr));code=exr_pager_anchor_resolve(pg.p,&a,nullptr,&match,nullptr);
      }
    }else if(mode==3){
      fixed doc;exr_fixed_open_options options{};options.struct_size=sizeof(options);sdk(exr_library_fixed(lib.p,book,&options,&doc.p,nullptr));size_t count=0;const exr_fixed_page *pages=exr_fixed_pages(doc.p,&count);size_t page=SIZE_MAX,hits=0;for(size_t n=0;n<count;n++)if(pages[n].id&&s[4]==pages[n].id){page=n;hits++;}if(hits!=1||page!=(size_t)unit)throw std::runtime_error("fixed page identity mismatch");
      fixed_text text;sdk(exr_fixed_load_text(doc.p,page,nullptr,&text.p,nullptr));exr_fixed_anchor a{};a.page_id=s[4].data();a.start=(size_t)start;a.end=(size_t)end;a.exact=s[0].data();a.exact_size=s[0].size();a.prefix=s[1].data();a.prefix_size=s[1].size();a.suffix=s[2].data();a.suffix_size=s[2].size();code=exr_fixed_anchor_resolve(a.page_id,text.p,&a,nullptr,&match,nullptr);
    }
    result[0]=code;result[1]=match.state;result[2]=(jlong)match.start;result[3]=(jlong)match.end;
  }catch(...){}
  jlongArray out=env->NewLongArray(4);if(out)env->SetLongArrayRegion(out,0,4,result);return out;
}
extern "C" JNIEXPORT jlongArray JNICALL Java_org_exreader_sessionprobe_NativeSdk_readingAudit(JNIEnv *env,jclass,jstring database,jlongArray books,jboolean initialize){
  jlong result[7]={-1,0,0,0,0,0,0};
  try{
    jlong ids[5];if(env->GetArrayLength(books)!=5)throw std::runtime_error("five routes required");env->GetLongArrayRegion(books,0,5,ids);library lib(argument(env,database));
    {
      size_t count=0;anchor initial;
      {document doc;sdk(exr_library_document(lib.p,ids[0],&doc.p,nullptr));exr_document_text(doc.p,&count);if(initialize)sdk(exr_anchor_create(doc.p,count,count,&initial.p,nullptr));}
      if(initialize)sdk(exr_library_progress(lib.p,ids[0],&initial.p,nullptr));
      anchor point;exr_anchor_state state=EXR_ANCHOR_MISSING;sdk(exr_library_progress_get(lib.p,ids[0],&point.p,&state,nullptr));result[1]=(jlong)point.p.start;result[2]=(jlong)count;
    }
    size_t n=0;exr_note *notes=nullptr;sdk(exr_library_notes(lib.p,ids[0],&notes,&n,nullptr));result[3]=(jlong)n;exr_notes_free(notes,n);notes=nullptr;sdk(exr_library_notes(lib.p,ids[4],&notes,&n,nullptr));result[4]=(jlong)n;exr_notes_free(notes,n);
    exr_epub_note *epub=nullptr;sdk(exr_library_epub_notes(lib.p,ids[1],&epub,&n,nullptr));result[5]=(jlong)n;exr_epub_notes_free(epub,n);
    for(int route=2;route<4;route++){exr_fixed_note *fixed_notes=nullptr;sdk(exr_library_fixed_notes(lib.p,ids[route],&fixed_notes,&n,nullptr));result[6]+=(jlong)n;exr_fixed_notes_free(fixed_notes,n);}result[0]=0;
  }catch(...){}
  jlongArray out=env->NewLongArray(7);if(out)env->SetLongArrayRegion(out,0,7,result);return out;
}
