#import <UIKit/UIKit.h>
int platform_probe(const char *, const char *, const char *, int);
@interface PlatformApp : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation PlatformApp
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  (void)application; (void)options;
  BOOL reopen = [NSProcessInfo.processInfo.arguments containsObject:@"reopen"];
  NSString *output = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  NSBundle *bundle = NSBundle.mainBundle;
  int result = platform_probe([bundle pathForResource:@"smoke" ofType:@"epub"].fileSystemRepresentation,
                              [bundle pathForResource:@"font" ofType:@"otf"].fileSystemRepresentation,
                              output.fileSystemRepresentation, reopen);
  NSString *state = [NSString stringWithFormat:@"exit=%d pid=%d\n", result, NSProcessInfo.processInfo.processIdentifier];
  [state writeToFile:[output stringByAppendingPathComponent:reopen ? @"reopen.exit" : @"create.exit"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController *controller = [UIViewController new];
  controller.view.backgroundColor = UIColor.whiteColor;
  UILabel *label = [[UILabel alloc] initWithFrame:CGRectMake(20, 80, 340, 100)];
  label.text = result ? @"FAIL: inspect Documents logs" : (reopen ? @"PASS 5/5" : @"PASS create; ready to reopen");
  [controller.view addSubview:label];
  self.window.rootViewController = controller;
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char **argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(PlatformApp.class)); }
}
