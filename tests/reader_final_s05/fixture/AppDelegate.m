// SPDX-License-Identifier: MIT
// CI-only fixture program for the S05 simulator distribution verifier.
// The compiled bundle is generated inside a GitHub Actions job and is never a
// product build: it proves the verifier, not the reader.
#import <UIKit/UIKit.h>

extern int exreader_s05_kit(void);

@interface S05FixtureDelegate : UIResponder <UIApplicationDelegate>
@property (nonatomic, strong) UIWindow *window;
@end

@implementation S05FixtureDelegate

- (BOOL)application:(UIApplication *)application
    didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
  self.window = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
  UIViewController *controller = [[UIViewController alloc] init];
  controller.view.backgroundColor = [UIColor systemBackgroundColor];
  UILabel *label = [[UILabel alloc] initWithFrame:CGRectInset(controller.view.bounds, 24, 120)];
  label.text = [NSString stringWithFormat:@"EXReader S05 fixture %d", exreader_s05_kit()];
  label.textAlignment = NSTextAlignmentCenter;
  label.numberOfLines = 0;
  label.textColor = [UIColor labelColor];
  [controller.view addSubview:label];
  self.window.rootViewController = controller;
  [self.window makeKeyAndVisible];
  return YES;
}

@end

int main(int argc, char *argv[]) {
  @autoreleasepool {
    return UIApplicationMain(argc, argv, nil, NSStringFromClass([S05FixtureDelegate class]));
  }
}
