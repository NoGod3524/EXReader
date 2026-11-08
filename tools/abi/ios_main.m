/* SPDX-License-Identifier: MIT */
#import <UIKit/UIKit.h>
#include <stdio.h>
#include <unistd.h>
int exr_acceptance(const char *book, const char *font, const char *output);
@interface EXRAcceptanceApp : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation EXRAcceptanceApp
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  (void)application; (void)options;
  NSString *output = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
  NSString *log = [output stringByAppendingPathComponent:@"acceptance.log"];
  if (!freopen(log.fileSystemRepresentation, "w", stdout)) return NO;
  dup2(fileno(stdout), fileno(stderr));
  setvbuf(stdout, NULL, _IONBF, 0);
  NSBundle *bundle = NSBundle.mainBundle;
  int result = exr_acceptance([bundle pathForResource:@"smoke" ofType:@"epub"].fileSystemRepresentation,
                             [bundle pathForResource:@"font" ofType:@"otf"].fileSystemRepresentation,
                             output.fileSystemRepresentation);
  fflush(stdout); fflush(stderr);
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController *controller = [UIViewController new];
  controller.view.backgroundColor = UIColor.systemBackgroundColor;
  UILabel *label = [[UILabel alloc] initWithFrame:CGRectMake(20, 80, 340, 120)];
  label.text = result == 0 ? @"PASS acceptance checks=5" : @"FAIL: see Documents/acceptance.log";
  label.numberOfLines = 0;
  [controller.view addSubview:label];
  self.window.rootViewController = controller;
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char **argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(EXRAcceptanceApp.class)); }
}
