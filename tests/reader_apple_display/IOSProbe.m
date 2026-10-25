// SPDX-License-Identifier: MIT
#import "ProbeSupport.h"
#import <UIKit/UIKit.h>

static NSString *mode, *output;
static BOOL started, resumed, backgroundSeen, multiFinished;
static ADRDisplayLease *lifecycleLease, *firstLease, *secondLease;
static UIWindow *firstWindow;
static UIWindowScene *firstScene;

static void capability(NSString *name, ADRStatus status, BOOL ok) {
    if (status == ADRStatusUnavailable) pending(name, @"Real simulator property did not accept/read back request; no physical capability granted");
    else check(name, status == ADRStatusOK && ok);
}
static BOOL equalBrightness(CGFloat a, CGFloat b) { return fabs(a-b) < 0.00001; }
static void core(UIWindow *window) {
    UIApplication *app = UIApplication.sharedApplication;
    check(@"ios_real_active_scene", window.windowScene.activationState == UISceneActivationStateForegroundActive &&
        [app.connectedScenes containsObject:window.windowScene] && !window.hidden);
    BOOL originalIdle = app.idleTimerDisabled;
    check(@"ios_initial_idle_baseline", !originalIdle);
    ADRStatus status;
    check(@"ios_nil_window_rejected", [ADRDisplayLease leaseForWindow:(id)nil status:&status] == nil && status == ADRStatusScene);
    UIWindow *unconnected = [UIWindow new];
    check(@"ios_unconnected_window_rejected", [ADRDisplayLease leaseForWindow:unconnected status:&status] == nil && status == ADRStatusScene);
    ADRDisplayLease *a = [ADRDisplayLease leaseForWindow:window status:&status];
    check(@"ios_create", a && status == ADRStatusOK && !owns(a));
    check(@"ios_host_inactive", [a setEnabled:YES hostActive:NO brightness:nil] == ADRStatusOK && !owns(a));
    ADRStatus idleStatus = [a setEnabled:YES hostActive:YES brightness:nil];
    capability(@"ios_idle_enable", idleStatus, owns(a) && app.idleTimerDisabled);
    ADRDisplayLease *b = [ADRDisplayLease leaseForWindow:window status:NULL];
    ADRStatus dual = [b setEnabled:YES hostActive:YES brightness:nil];
    capability(@"ios_dual_lease", dual, owns(a) && owns(b) && [snapshot(b)[@"activeIdleLeases"] intValue] == 2);
    [a close];
    capability(@"ios_close_preserves_other", dual, owns(b) && app.idleTimerDisabled && [snapshot(b)[@"activeIdleLeases"] intValue] == 1);
    [b close];
    check(@"ios_last_close_restores", app.idleTimerDisabled == originalIdle);
    check(@"ios_close_idempotent", [a close] == ADRStatusOK);
    check(@"ios_closed_update_rejected", [a setEnabled:YES hostActive:YES brightness:nil] == ADRStatusClosed);
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    [a setEnabled:YES hostActive:YES brightness:nil];
    check(@"ios_cancel_releases", [a cancel] == ADRStatusOK && !owns(a) && app.idleTimerDisabled == originalIdle);
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    check(@"ios_nan_rejected", [a setEnabled:YES hostActive:YES brightness:@(NAN)] == ADRStatusInvalid && !owns(a));
    check(@"ios_inf_rejected", [a setEnabled:YES hostActive:YES brightness:@(INFINITY)] == ADRStatusInvalid);
    check(@"ios_negative_rejected", [a setEnabled:YES hostActive:YES brightness:@(-0.1)] == ADRStatusInvalid);
    check(@"ios_above_one_rejected", [a setEnabled:YES hostActive:YES brightness:@1.1] == ADRStatusInvalid);
    check(@"ios_wrong_type_rejected", [a setEnabled:YES hostActive:YES brightness:(id)@"not a number"] == ADRStatusInvalid);
    ADRStatus retry = [a setEnabled:YES hostActive:YES brightness:nil];
    capability(@"ios_retry_after_error", retry, owns(a));
    BOOL before = owns(a);
    __block BOOL wrong;
    dispatch_semaphore_t finished = dispatch_semaphore_create(0);
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{
        ADRStatus e;
        wrong = [a setEnabled:NO hostActive:NO brightness:nil] == ADRStatusWrongThread &&
            [a close] == ADRStatusWrongThread && [a cancel] == ADRStatusWrongThread &&
            [a snapshotWithStatus:&e] == nil && e == ADRStatusWrongThread &&
            [ADRDisplayLease leaseForWindow:window status:&e] == nil && e == ADRStatusWrongThread;
        dispatch_semaphore_signal(finished);
    });
    if (dispatch_semaphore_wait(finished, dispatch_time(DISPATCH_TIME_NOW, 10*NSEC_PER_SEC)) != 0) abort();
    check(@"ios_wrong_thread_no_mutation", wrong && owns(a) == before);
    app.idleTimerDisabled = NO;
    [a close];
    check(@"ios_external_idle_preserved", !app.idleTimerDisabled);
    app.idleTimerDisabled = YES;
    BOOL acceptedTrue = app.idleTimerDisabled;
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    [a setEnabled:YES hostActive:YES brightness:nil]; [a close];
    if (!acceptedTrue) pending(@"ios_saved_true_restored", @"Simulator rejects direct real UIApplication idleTimerDisabled property");
    else check(@"ios_saved_true_restored", app.idleTimerDisabled);
    app.idleTimerDisabled = originalIdle;
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    [a setEnabled:YES hostActive:YES brightness:nil];
    window.hidden = YES;
    check(@"ios_hidden_window_releases", !owns(a) && app.idleTimerDisabled == originalIdle);
    window.hidden = NO;
    if (idleStatus == ADRStatusUnavailable) pending(@"ios_visible_window_reacquires", @"Real idle property unavailable on simulator");
    else check(@"ios_visible_window_reacquires", owns(a) && app.idleTimerDisabled);
    [a close];

    UIScreen *screen = window.windowScene.screen;
    CGFloat originalBrightness = screen.brightness;
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    ADRStatus brightnessStatus = [a setEnabled:YES hostActive:YES brightness:@0.37];
    NSString *readback = [NSString stringWithFormat:@"requested=0.37 observed=%.8f status=%ld owns=%d; simulator is not physical backlight evidence",
        (double)screen.brightness, (long)brightnessStatus, [snapshot(a)[@"ownsBrightness"] boolValue]];
    record(@"ios_brightness_readback", brightnessStatus == ADRStatusUnavailable ? @"PENDING" :
        ((brightnessStatus == ADRStatusOK && [snapshot(a)[@"ownsBrightness"] boolValue] && equalBrightness(screen.brightness, .37)) ? @"PASS" : @"FAIL"), readback);
    b = [ADRDisplayLease leaseForWindow:window status:NULL];
    ADRStatus conflict = [b setEnabled:YES hostActive:YES brightness:@0.63];
    if (brightnessStatus == ADRStatusUnavailable) {
        pending(@"ios_brightness_conflict", @"Real property unavailable; exclusivity not awarded");
        pending(@"ios_conflict_no_partial_idle", @"Real property unavailable; exclusivity not awarded");
    } else {
        check(@"ios_brightness_conflict", conflict == ADRStatusConflict && [snapshot(a)[@"ownsBrightness"] boolValue]);
        check(@"ios_conflict_no_partial_idle", !owns(b) && ![snapshot(b)[@"ownsBrightness"] boolValue]);
    }
    [b close]; [a close];
    capability(@"ios_brightness_conditional_restore", brightnessStatus, equalBrightness(screen.brightness, originalBrightness));
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    ADRStatus externalStatus = [a setEnabled:YES hostActive:YES brightness:@0.39];
    screen.brightness = 0.79;
    BOOL externalAccepted = equalBrightness(screen.brightness, .79);
    (void)snapshot(a); // Observe the real changed property; no synthetic notification.
    [a close];
    if (!externalAccepted || externalStatus == ADRStatusUnavailable)
        pending(@"ios_brightness_external_preserved", @"Simulator did not support required real property writes");
    else check(@"ios_brightness_external_preserved", equalBrightness(screen.brightness, .79));
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    ADRStatus brRetry = [a setEnabled:YES hostActive:YES brightness:@0.41];
    screen.brightness = .81; (void)snapshot(a);
    brRetry = [a setEnabled:YES hostActive:YES brightness:@0.41];
    capability(@"ios_brightness_retry", brRetry, [snapshot(a)[@"ownsBrightness"] boolValue] && equalBrightness(screen.brightness, .41));
    ADRStatus invalid = [a setEnabled:YES hostActive:YES brightness:@(NAN)];
    if (brRetry == ADRStatusUnavailable) pending(@"ios_brightness_invalid_releases", @"Real brightness holding unavailable");
    else check(@"ios_brightness_invalid_releases", invalid == ADRStatusInvalid && !owns(a) &&
        ![snapshot(a)[@"ownsBrightness"] boolValue] && equalBrightness(screen.brightness, .81));
    [a close]; screen.brightness = originalBrightness;

    NSMutableArray *all = [NSMutableArray new];
    for (int i=0;i<64;i++) { ADRDisplayLease *l=[ADRDisplayLease leaseForWindow:window status:NULL]; if(l)[all addObject:l]; }
    ADRStatus limit;
    check(@"ios_lease_limit", all.count == 64 && [ADRDisplayLease leaseForWindow:window status:&limit] == nil && limit == ADRStatusLimit);
    for (ADRDisplayLease *l in all) [l close];
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    check(@"ios_limit_recovery", a != nil); [a close];
    @autoreleasepool {
        ADRDisplayLease *d = [ADRDisplayLease leaseForWindow:window status:NULL];
        [d setEnabled:YES hostActive:YES brightness:nil]; d = nil;
    }
    a = [ADRDisplayLease leaseForWindow:window status:NULL];
    check(@"ios_deallocation_release", [snapshot(a)[@"activeIdleLeases"] intValue] == 0 && app.idleTimerDisabled == originalIdle); [a close];
    pending(@"ios_physical_backlight", @"Simulator property state is not physical backlight evidence");
    pending(@"ios_physical_sleep", @"Simulator app state is not physical idle-sleep evidence");
    pending(@"ios_external_screen", @"No real external screen connected; brightness intentionally unsupported there");
    writeReport(output, @"complete");
}

static void multiUnavailable(NSString *reason) {
    if (multiFinished) return; multiFinished = YES;
    pending(@"ios_multiscene_real_sessions", reason);
    pending(@"ios_multiscene_isolation", reason);
    pending(@"ios_scene_disconnect_releases", reason);
    [firstLease close]; [secondLease close]; writeReport(output, @"complete");
}

@interface DisplaySceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation DisplaySceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)session; (void)options;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];
    UIViewController *controller = [UIViewController new];
    controller.view.backgroundColor = UIColor.systemBackgroundColor;
    UILabel *label = [[UILabel alloc] initWithFrame:CGRectMake(24, 70, 340, 100)];
    label.text = @"EXReader display native probe"; label.numberOfLines = 0;
    [controller.view addSubview:label]; self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
}
- (void)sceneDidBecomeActive:(UIScene *)scene {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 500 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        if ([mode isEqual:@"core"]) { if (!started) { started = YES; core(self.window); } return; }
        if ([mode isEqual:@"reopen"]) {
            if (started) return; started = YES;
            ADRDisplayLease *l = [ADRDisplayLease leaseForWindow:self.window status:NULL];
            check(@"ios_new_process_no_saved_lease", !owns(l) && [snapshot(l)[@"activeIdleLeases"] intValue] == 0);
            check(@"ios_new_process_idle_baseline", !UIApplication.sharedApplication.idleTimerDisabled);
            check(@"ios_new_process_active_scene", scene.activationState == UISceneActivationStateForegroundActive);
            [l close]; writeReport(output, @"complete"); return;
        }
        if ([mode isEqual:@"lifecycle"]) {
            if (!started) {
                started = YES;
                lifecycleLease = [ADRDisplayLease leaseForWindow:self.window status:NULL];
                ADRStatus s = [lifecycleLease setEnabled:YES hostActive:YES brightness:nil];
                capability(@"ios_lifecycle_active_holds", s, owns(lifecycleLease));
                writeReport(output, @"active");
            } else if (backgroundSeen && !resumed) {
                resumed = YES;
                ADRStatus s = [snapshot(lifecycleLease)[@"lastStatus"] integerValue];
                capability(@"ios_lifecycle_foreground_reacquires", s, owns(lifecycleLease));
                writeReport(output, @"resumed");
            }
            return;
        }
        if ([mode isEqual:@"multiscene"]) {
            if (multiFinished) return;
            if (!started) {
                started = YES; firstScene = (UIWindowScene *)scene; firstWindow = self.window;
                firstLease = [ADRDisplayLease leaseForWindow:self.window status:NULL];
                [firstLease setEnabled:YES hostActive:YES brightness:nil];
                if (!UIApplication.sharedApplication.supportsMultipleScenes) {
                    multiUnavailable(@"UIKit reports supportsMultipleScenes=false on this simulator"); return;
                }
                NSUserActivity *activity = [[NSUserActivity alloc] initWithActivityType:@"org.exreader.display.second"];
                UISceneActivationRequestOptions *requestOptions = [UISceneActivationRequestOptions new];
                requestOptions.requestingScene = firstScene;
                [UIApplication.sharedApplication requestSceneSessionActivation:nil userActivity:activity options:requestOptions errorHandler:^(NSError *error) {
                    multiUnavailable([NSString stringWithFormat:@"Real scene activation error %@/%ld", error.domain, (long)error.code]);
                }];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 15 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                    if (!secondLease) multiUnavailable(@"No second active real scene within the bounded simulator observation window");
                });
            } else if (scene != firstScene && !secondLease) {
                secondLease = [ADRDisplayLease leaseForWindow:self.window status:NULL];
                ADRStatus s = [secondLease setEnabled:YES hostActive:YES brightness:nil];
                check(@"ios_multiscene_real_sessions", UIApplication.sharedApplication.connectedScenes.count >= 2 &&
                    ![scene.session.persistentIdentifier isEqual:firstScene.session.persistentIdentifier]);
                [firstLease setEnabled:NO hostActive:NO brightness:nil];
                capability(@"ios_multiscene_isolation", s, owns(secondLease) && !owns(firstLease));
                [UIApplication.sharedApplication requestSceneSessionDestruction:firstScene.session options:nil errorHandler:^(NSError *error) {
                    (void)error;
                    if (!multiFinished) {
                        multiFinished = YES; pending(@"ios_scene_disconnect_releases", [NSString stringWithFormat:@"Real scene destruction error %@/%ld", error.domain, (long)error.code]);
                        [firstLease close]; [secondLease close]; writeReport(output, @"complete");
                    }
                }];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
                    if (!multiFinished) {
                        multiFinished = YES; pending(@"ios_scene_disconnect_releases", @"Real scene destruction not observed within bounded simulator window");
                        [firstLease close]; [secondLease close]; writeReport(output, @"complete");
                    }
                });
            }
        }
    });
}
- (void)sceneDidEnterBackground:(UIScene *)scene {
    (void)scene;
    if (![mode isEqual:@"lifecycle"] || !started || backgroundSeen) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (backgroundSeen) return; backgroundSeen = YES;
        check(@"ios_lifecycle_background_releases", !owns(lifecycleLease) &&
            ![snapshot(lifecycleLease)[@"ownsBrightness"] boolValue]);
        writeReport(output, @"background");
    });
}
- (void)sceneDidDisconnect:(UIScene *)scene {
    if (![mode isEqual:@"multiscene"] || scene != firstScene || multiFinished) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (multiFinished) return; multiFinished = YES;
        check(@"ios_scene_disconnect_releases", [snapshot(firstLease)[@"closed"] boolValue] && !owns(firstLease) &&
            ![UIApplication.sharedApplication.connectedScenes containsObject:firstScene]);
        [secondLease close]; writeReport(output, @"complete");
    });
}
@end
@interface DisplayAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation DisplayAppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    (void)application; (void)options;
    NSArray *args = NSProcessInfo.processInfo.arguments;
    NSUInteger index = [args indexOfObject:@"--mode"];
    mode = index != NSNotFound && index + 1 < args.count ? args[index+1] : @"core";
    output = [[NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject] stringByAppendingPathComponent:@"report.json"];
    return YES;
}
- (UISceneConfiguration *)application:(UIApplication *)application configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {
    (void)application; (void)options;
    UISceneConfiguration *config = [[UISceneConfiguration alloc] initWithName:@"Display" sessionRole:session.role];
    config.sceneClass = UIWindowScene.class; config.delegateClass = DisplaySceneDelegate.class; return config;
}
@end
int main(int argc, char **argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(DisplayAppDelegate.class)); }
}
