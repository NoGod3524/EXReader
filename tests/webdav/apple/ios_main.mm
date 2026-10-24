/* SPDX-License-Identifier: MIT */
#import <UIKit/UIKit.h>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
int apple_dav_probe(int,char **);

@interface EXRDAVProbeApp : UIResponder<UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation EXRDAVProbeApp
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  (void)application;(void)options;
  self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController *controller=[UIViewController new];
  UILabel *label=[[UILabel alloc] initWithFrame:self.window.bounds];
  label.text=@"EXReader native WebDAV acceptance";label.textAlignment=NSTextAlignmentCenter;
  [controller.view addSubview:label];self.window.rootViewController=controller;[self.window makeKeyAndVisible];
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
    @autoreleasepool {
      NSURL *directory=[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
      NSURL *request=[directory URLByAppendingPathComponent:@"request.json"];
      NSData *data=[NSData dataWithContentsOfURL:request];
      NSArray *arguments=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:nil]:nil;
      [NSFileManager.defaultManager removeItemAtURL:request error:nil];
      if(![arguments isKindOfClass:NSArray.class])return;
      std::vector<std::string> values;
      for(id argument in arguments){if(![argument isKindOfClass:NSString.class])return;values.emplace_back([argument UTF8String]);}
      std::vector<char *> argv;for(auto &value:values)argv.push_back(value.data());
      std::ostringstream output;auto previous=std::cout.rdbuf(output.rdbuf());int status=2;
      try{status=apple_dav_probe((int)argv.size(),argv.data());}catch(...){status=3;}
      std::cout.rdbuf(previous);
      std::string bytes=status?"{\"probe_failure\":true}":output.str();
      NSData *result=[NSData dataWithBytes:bytes.data() length:bytes.size()];
      [result writeToURL:[directory URLByAppendingPathComponent:@"result.json"] options:NSDataWritingAtomic error:nil];
    }
  });
  return YES;
}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(EXRDAVProbeApp.class));}}
