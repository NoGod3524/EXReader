/* SPDX-License-Identifier: MIT */
// Simulator host for the installed probe: a real UIKit app whose main run loop
// drives AVSpeechSynthesizer. The probe runs on the main thread only, after
// -application:didFinishLaunchingWithOptions: has returned, so the run loop is
// already running and can be pumped from inside the probe.
#import <UIKit/UIKit.h>

#include <cstdio>

extern "C" int rtts_probe_run(const char *output_path);

@interface EXRTTSProbeApp : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end

@implementation EXRTTSProbeApp

- (BOOL)application:(UIApplication *)application
    didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
  (void)application;
  (void)launchOptions;
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController *controller = [UIViewController new];
  UILabel *label = [[UILabel alloc] initWithFrame:self.window.bounds];
  label.text = @"EXReader native speech acceptance";
  label.textAlignment = NSTextAlignmentCenter;
  label.numberOfLines = 0;
  [controller.view addSubview:label];
  self.window.rootViewController = controller;
  [self.window makeKeyAndVisible];

  dispatch_async(dispatch_get_main_queue(), ^{
    @autoreleasepool {
      NSURL *directory = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory
                                                             inDomains:NSUserDomainMask]
                             .firstObject;
      NSString *report = [directory URLByAppendingPathComponent:@"result.json"].path;
      NSString *done = [directory URLByAppendingPathComponent:@"done.json"].path;
      const int status = rtts_probe_run(report.UTF8String);
      NSString *marker = [NSString stringWithFormat:@"{\"exit\": %d}", status];
      [marker writeToFile:done atomically:YES encoding:NSUTF8StringEncoding error:nil];
      std::printf("PROBE_EXIT %d\n", status);
      std::fflush(stdout);
    }
  });
  return YES;
}

@end

int main(int argc, char **argv) {
  @autoreleasepool {
    return UIApplicationMain(argc, argv, nil, NSStringFromClass(EXRTTSProbeApp.class));
  }
}
