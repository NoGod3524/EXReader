/* SPDX-License-Identifier: MIT */
#import <UIKit/UIKit.h>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
int ios_reader_session_probe(int,char **);
@interface EXRSessionProbeApp : UIResponder<UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@property(nonatomic,strong) NSTimer *heartbeat;
@property(nonatomic) unsigned ticks;
@end
@implementation EXRSessionProbeApp
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  (void)application;(void)options;
  self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController *controller=[UIViewController new];UILabel *label=[[UILabel alloc] initWithFrame:self.window.bounds];
  label.text=@"EXReader native account acceptance";label.textAlignment=NSTextAlignmentCenter;
  [controller.view addSubview:label];self.window.rootViewController=controller;[self.window makeKeyAndVisible];
  self.heartbeat=[NSTimer scheduledTimerWithTimeInterval:.1 repeats:YES block:^(NSTimer *timer){(void)timer;self.ticks++;}];
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{@autoreleasepool{
    NSURL *documents=[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSURL *request=[documents URLByAppendingPathComponent:@"request.json"];
    NSDictionary *input=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfURL:request] options:0 error:nil];
    [NSFileManager.defaultManager removeItemAtURL:request error:nil];
    NSArray *arguments=input[@"arguments"];NSString *authorization=input[@"authorization"];
    if(![arguments isKindOfClass:NSArray.class]||![authorization isKindOfClass:NSString.class])return;
    setenv("READER_TEST_AUTH",authorization.UTF8String,1);
    std::vector<std::string> values;for(NSString *argument in arguments)values.emplace_back(argument.UTF8String);
    std::vector<char *> argv;for(auto &value:values)argv.push_back(value.data());
    NSString *log=[[documents path] stringByAppendingPathComponent:@"probe.log"];
    if(!freopen(log.fileSystemRepresentation,"wb",stdout)||!freopen(log.fileSystemRepresentation,"ab",stderr))return;
    int code=ios_reader_session_probe((int)argv.size(),argv.data());fflush(stdout);fflush(stderr);unsetenv("READER_TEST_AUTH");
    dispatch_async(dispatch_get_main_queue(),^{
      [self.heartbeat invalidate];NSDictionary *result=@{@"code":@(code),@"main_thread_ticks":@(self.ticks)};
      NSData *data=[NSJSONSerialization dataWithJSONObject:result options:0 error:nil];
      [data writeToURL:[documents URLByAppendingPathComponent:@"completion.json"] options:NSDataWritingAtomic error:nil];
    });
  }});
  return YES;
}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(EXRSessionProbeApp.class));}}
