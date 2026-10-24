/* SPDX-License-Identifier: MIT */
#include "apple_transport.h"
#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <dispatch/dispatch.h>
#include <TargetConditionals.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>

namespace {
constexpr size_t chunk_size=65536;
struct transfer {
  std::mutex mutex;
  std::condition_variable changed;
  std::array<unsigned char,chunk_size> bytes{};
  size_t count=0;
  bool header=false, stopped=false, finished=false, write_ready=false;
  NSHTTPURLResponse *__strong response=nil;
  NSError *__strong error=nil;
  exr_webdav_status auth=EXR_DAV_OK;
};
exr_webdav_status native_error(NSError *error){
  if(!error)return EXR_DAV_OK;
  if(![error.domain isEqualToString:NSURLErrorDomain])return EXR_DAV_IO;
  switch(error.code){
    case NSURLErrorSecureConnectionFailed:case NSURLErrorServerCertificateHasBadDate:
    case NSURLErrorServerCertificateUntrusted:case NSURLErrorServerCertificateHasUnknownRoot:
    case NSURLErrorServerCertificateNotYetValid:case NSURLErrorClientCertificateRejected:
    case NSURLErrorClientCertificateRequired:return EXR_DAV_TLS;
    case NSURLErrorUserAuthenticationRequired:return EXR_DAV_AUTH;
    default:return EXR_DAV_IO;
  }
}
exr_webdav_status fail(exr_webdav_error *error,exr_webdav_status code,int http=0){
  if(error){error->code=code;error->http_status=http;
    const char *message=code==EXR_DAV_TLS?"Native HTTPS trust validation failed":
      code==EXR_DAV_AUTH?"Credentials required for the configured origin":
      code==EXR_DAV_CANCELLED?"Transfer cancelled":code==EXR_DAV_ARGUMENT?"Native HTTPS requires a host worker and valid request":
      code==EXR_DAV_MEMORY?"Cannot allocate native HTTPS state":"Native HTTPS transfer failed";
    std::snprintf(error->message,sizeof(error->message),"%s",message);
  }return code;
}
struct output_stream {
  CFWriteStreamRef value=nullptr;
  ~output_stream(){close();}
  void close(){if(value){CFWriteStreamSetClient(value,0,nullptr,nullptr);CFWriteStreamSetDispatchQueue(value,nullptr);
    CFWriteStreamClose(value);CFRelease(value);value=nullptr;}}
};
}

@interface EXRDAVDelegate : NSObject<NSURLSessionDataDelegate,NSURLSessionTaskDelegate> {
@public
  std::shared_ptr<transfer> state;
  NSInputStream *body;
  BOOL body_supplied;
}
@end

static void output_ready(CFWriteStreamRef stream,CFStreamEventType event,void *context){
  (void)stream;(void)event;EXRDAVDelegate *delegate=(__bridge EXRDAVDelegate *)context;
  auto state=delegate->state;
  {std::lock_guard<std::mutex> lock(state->mutex);state->write_ready=true;}
  state->changed.notify_all();
}
@implementation EXRDAVDelegate
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task
    didReceiveResponse:(NSURLResponse *)response completionHandler:(void (^)(NSURLSessionResponseDisposition))completion {
  (void)session;(void)task;
  if(![response isKindOfClass:NSHTTPURLResponse.class]){completion(NSURLSessionResponseCancel);return;}
  size_t header_bytes=0;bool bounded=true;
  NSDictionary *headers=((NSHTTPURLResponse *)response).allHeaderFields;
  for(id key in headers){
    size_t bytes=[[key description] lengthOfBytesUsingEncoding:NSUTF8StringEncoding]+
      [[headers[key] description] lengthOfBytesUsingEncoding:NSUTF8StringEncoding];
    if(bytes>32768-header_bytes){bounded=false;break;}header_bytes+=bytes;
  }
  bool stopped;
  {std::lock_guard<std::mutex> lock(state->mutex);stopped=state->stopped;
    if(!bounded)state->auth=EXR_DAV_LIMIT;
    if(!stopped){state->response=(NSHTTPURLResponse *)response;state->header=true;}}
  state->changed.notify_all();completion(stopped||!bounded?NSURLSessionResponseCancel:NSURLSessionResponseAllow);
}
- (void)URLSession:(NSURLSession *)session dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
  (void)session;(void)task;
  const unsigned char *bytes=(const unsigned char *)data.bytes;size_t left=data.length;
  while(left){
    std::unique_lock<std::mutex> lock(state->mutex);
    state->changed.wait(lock,[&]{return state->stopped||!state->count;});
    if(state->stopped)return;
    size_t count=left<chunk_size?left:chunk_size;
    std::memcpy(state->bytes.data(),bytes,count);state->count=count;
    bytes+=count;left-=count;lock.unlock();state->changed.notify_all();
  }
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
    willPerformHTTPRedirection:(NSHTTPURLResponse *)response newRequest:(NSURLRequest *)request
    completionHandler:(void (^)(NSURLRequest *))completion {
  (void)session;(void)task;(void)response;(void)request;
  completion(nil); /* Shared C++ policy decides every redirect, before another request. */
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
    didReceiveChallenge:(NSURLAuthenticationChallenge *)challenge
    completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition,NSURLCredential *))completion {
  (void)session;(void)task;
  NSString *method=challenge.protectionSpace.authenticationMethod;
  if([method isEqualToString:NSURLAuthenticationMethodServerTrust]){
    completion(NSURLSessionAuthChallengePerformDefaultHandling,nil);return;
  }
  {std::lock_guard<std::mutex> lock(state->mutex);
    state->auth=[method isEqualToString:NSURLAuthenticationMethodClientCertificate]?EXR_DAV_TLS:EXR_DAV_AUTH;}
  state->changed.notify_all();completion(NSURLSessionAuthChallengeCancelAuthenticationChallenge,nil);
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task
    needNewBodyStream:(void (^)(NSInputStream *))completion {
  (void)session;(void)task;
  if(body_supplied){completion(nil);return;}
  body_supplied=YES;completion(body);
}
- (void)URLSession:(NSURLSession *)session task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
  (void)session;(void)task;
  {std::lock_guard<std::mutex> lock(state->mutex);state->error=error;state->finished=true;}
  state->changed.notify_all();
}
@end

extern "C" exr_webdav_status exr_apple_http(const exr_apple_request *input,exr_webdav_error *error){
  if(error)std::memset(error,0,sizeof(*error));
  if(!input||!input->url||!input->method||!input->headers||!input->receive||!input->timeout_ms)
    return fail(error,EXR_DAV_ARGUMENT);
#if TARGET_OS_IPHONE
  if(NSThread.isMainThread)return fail(error,EXR_DAV_ARGUMENT);
#endif
  auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(input->timeout_ms);
  @autoreleasepool {
    try {
      auto state=std::make_shared<transfer>();
      NSURL *url=[NSURL URLWithString:[NSString stringWithUTF8String:input->url]];
      if(!url||![url.scheme isEqualToString:@"https"])return fail(error,EXR_DAV_ARGUMENT);
      NSMutableURLRequest *request=[NSMutableURLRequest requestWithURL:url];
      request.HTTPMethod=[NSString stringWithUTF8String:input->method];
      request.cachePolicy=NSURLRequestReloadIgnoringLocalCacheData;request.HTTPShouldHandleCookies=NO;
      request.timeoutInterval=(NSTimeInterval)input->timeout_ms/1000.0;
      [request setValue:@"identity" forHTTPHeaderField:@"Accept-Encoding"];
      if(input->authorization&&*input->authorization)
        [request setValue:[NSString stringWithUTF8String:input->authorization] forHTTPHeaderField:@"Authorization"];
      if(!std::strcmp(input->method,"PROPFIND")){
        static const char xml[]="<?xml version=\"1.0\"?><d:propfind xmlns:d=\"DAV:\"><d:prop><d:displayname/><d:resourcetype/><d:getcontentlength/><d:getetag/></d:prop></d:propfind>";
        request.HTTPBody=[NSData dataWithBytes:xml length:sizeof(xml)-1];
        [request setValue:@"1" forHTTPHeaderField:@"Depth"];
        [request setValue:@"application/xml; charset=utf-8" forHTTPHeaderField:@"Content-Type"];
      }
      EXRDAVDelegate *delegate=[EXRDAVDelegate new];delegate->state=state;
      output_stream output;
      if(input->read){
        CFReadStreamRef stream=nullptr;
        CFStreamCreateBoundPair(kCFAllocatorDefault,&stream,&output.value,(CFIndex)chunk_size);
        if(!stream||!output.value){if(stream)CFRelease(stream);return fail(error,EXR_DAV_MEMORY);}
        delegate->body=CFBridgingRelease(stream);
        CFStreamClientContext signal{0,(__bridge void *)delegate,
          [](void *value)->void *{return const_cast<void *>(CFRetain(value));},
          [](void *value){CFRelease(value);},nullptr};
        if(!CFWriteStreamSetClient(output.value,kCFStreamEventCanAcceptBytes|kCFStreamEventErrorOccurred|kCFStreamEventEndEncountered,output_ready,&signal))
          return fail(error,EXR_DAV_IO);
        CFWriteStreamSetDispatchQueue(output.value,dispatch_get_global_queue(QOS_CLASS_UTILITY,0));
        [request setValue:@"*" forHTTPHeaderField:@"If-None-Match"];
        [request setValue:@"application/octet-stream" forHTTPHeaderField:@"Content-Type"];
        [request setValue:[NSString stringWithFormat:@"%llu",(unsigned long long)input->upload_bytes] forHTTPHeaderField:@"Content-Length"];
      }
      NSURLSessionConfiguration *configuration=NSURLSessionConfiguration.ephemeralSessionConfiguration;
      configuration.URLCache=nil;configuration.HTTPCookieStorage=nil;configuration.URLCredentialStorage=nil;
      configuration.HTTPShouldSetCookies=NO;configuration.HTTPMaximumConnectionsPerHost=1;
      configuration.waitsForConnectivity=NO;configuration.connectionProxyDictionary=@{};
      configuration.timeoutIntervalForRequest=request.timeoutInterval;
      configuration.timeoutIntervalForResource=request.timeoutInterval;
      NSOperationQueue *queue=[NSOperationQueue new];queue.maxConcurrentOperationCount=1;
      NSURLSession *session=[NSURLSession sessionWithConfiguration:configuration delegate:delegate delegateQueue:queue];
      NSURLSessionTask *task=input->read?[session uploadTaskWithStreamedRequest:request]:[session dataTaskWithRequest:request];
      /* Delegates never retain input/context or invoke its callbacks. Native
         cancellation may settle after return; only internal state can remain. */
      struct cleanup {
        std::shared_ptr<transfer> state;
        NSURLSession *__strong session;
        NSURLSessionTask *__strong task;
        ~cleanup(){
          {std::lock_guard<std::mutex> lock(state->mutex);state->stopped=true;}
          state->changed.notify_all();[task cancel];[session invalidateAndCancel];
        }
      } lifetime{state,session,task};
      exr_webdav_status result=EXR_DAV_OK;int http=0;bool have_header=false;
      std::array<unsigned char,chunk_size> pending{};size_t used=0,available=0;uint64_t read_total=0;
      [task resume];
      if(output.value&&!CFWriteStreamOpen(output.value))return fail(error,EXR_DAV_IO);
      for(;;){
        bool worked=false;
        if(input->cancelled&&input->cancelled(input->context)){result=EXR_DAV_CANCELLED;break;}
        if(std::chrono::steady_clock::now()>=deadline){result=EXR_DAV_IO;break;}
        NSHTTPURLResponse *response=nil;bool finished=false;NSError *native=nil;
        {
          std::lock_guard<std::mutex> lock(state->mutex);
          if(state->header&&!have_header){response=state->response;have_header=true;}
          finished=state->finished;native=state->error;
          state->write_ready=false;
          if(state->auth!=EXR_DAV_OK){result=state->auth;http=result==EXR_DAV_AUTH?401:0;break;}
        }
        if(response){
          worked=true;
          http=(int)response.statusCode;
          NSString *location=[response valueForHTTPHeaderField:@"Location"];
          NSString *length=[response valueForHTTPHeaderField:@"Content-Length"];
          result=input->headers(input->context,http,location?location.UTF8String:"",length?length.UTF8String:"");
          if(result!=EXR_DAV_OK||http==301||http==302||http==307||http==308)break;
        }
        size_t count;
        {std::lock_guard<std::mutex> lock(state->mutex);count=state->count;}
        if(count){
          worked=true;
          result=input->receive(input->context,state->bytes.data(),count);
          {std::lock_guard<std::mutex> lock(state->mutex);state->count=0;}
          state->changed.notify_all();if(result!=EXR_DAV_OK)break;
        }
        if(finished){result=native_error(native);if(result==EXR_DAV_OK&&!have_header)result=EXR_DAV_IO;break;}
        if(output.value&&CFWriteStreamCanAcceptBytes(output.value)){
          if(used==available&&read_total<input->upload_bytes){
            size_t want=(size_t)std::min<uint64_t>(chunk_size,input->upload_bytes-read_total);
            available=0;used=0;result=input->read(input->context,pending.data(),want,&available);
            if(result!=EXR_DAV_OK)break;
            if(!available||available>want){result=EXR_DAV_IO;break;}read_total+=available;
          }
          if(used<available){
            CFIndex wrote=CFWriteStreamWrite(output.value,pending.data()+used,(CFIndex)(available-used));
            if(wrote<=0){result=EXR_DAV_IO;break;}used+=(size_t)wrote;
            worked=true;
          }
          if(used==available&&read_total==input->upload_bytes)output.close();
        }
        if(output.value&&CFWriteStreamGetStatus(output.value)==kCFStreamStatusError){result=EXR_DAV_IO;break;}
        if(worked)continue;
        std::unique_lock<std::mutex> lock(state->mutex);
        state->changed.wait_for(lock,std::chrono::milliseconds(5),[&]{return state->count||state->finished||state->write_ready||(!have_header&&state->header);});
      }
      output.close();
      return result==EXR_DAV_OK?result:fail(error,result,http);
    }catch(...){return fail(error,EXR_DAV_MEMORY);}
  }
}
