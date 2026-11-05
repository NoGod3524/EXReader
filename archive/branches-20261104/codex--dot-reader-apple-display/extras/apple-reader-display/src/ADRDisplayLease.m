// SPDX-License-Identifier: MIT
#import <ADRDisplayLease.h>
#import <dispatch/dispatch.h>
#include <math.h>
#if !TARGET_OS_IOS
#import <IOKit/pwr_mgt/IOPMLib.h>
#endif
#ifndef ADR_SOURCE_SHA
#define ADR_SOURCE_SHA "unversioned"
#endif
const char *ADRDisplaySourceRevision(void) { return ADR_SOURCE_SHA; }
NSString *ADRStatusMessage(ADRStatus s) {
    switch (s) {
        case ADRStatusOK: return @"OK";
        case ADRStatusWrongThread: return @"Main thread required";
        case ADRStatusInvalid: return @"Invalid display value";
        case ADRStatusClosed: return @"Lease is closed";
        case ADRStatusScene: return @"Scene or screen is not available";
        case ADRStatusConflict: return @"Screen brightness already leased";
        case ADRStatusUnavailable: return @"System display capability unavailable";
        case ADRStatusIO: return @"System display operation failed";
        case ADRStatusUnsupported: return @"Display capability unsupported";
        case ADRStatusLimit: return @"Display lease limit reached";
    }
    return @"Unknown display status";
}

@interface ADRLeaseState : NSObject
@property BOOL closed;
@property BOOL enabled;
@property BOOL hostActive;
@property BOOL ownsIdle;
@property ADRStatus lastStatus;
@property NSInteger nativeCode;
#if TARGET_OS_IOS
@property(nonatomic, weak) UIWindow *window;
@property(nonatomic, weak) UIWindowScene *scene;
@property(nonatomic, strong) UIScreen *screen;
@property(nonatomic, strong) NSNumber *brightness;
@property BOOL ownsBrightness;
@property BOOL brightnessSuppressed;
@property CGFloat savedBrightness;
@property CGFloat writtenBrightness;
#else
@property IOPMAssertionID assertion;
#endif
- (ADRStatus)withdraw;
- (ADRStatus)reconcile;
- (ADRStatus)finish;
@end

static NSHashTable<ADRLeaseState *> *states;
#if TARGET_OS_IOS
static NSMapTable<UIScreen *, ADRLeaseState *> *brightnessOwners;
static NSUInteger idleOwners;
static BOOL savedIdle;
static NSUInteger brightnessMutationDepth;
static BOOL sameBrightness(CGFloat a, CGFloat b) { return fabs(a-b) <= 0.00001; }

static void observeBrightness(ADRLeaseState *s) {
    if (s.ownsBrightness && !sameBrightness(s.screen.brightness, s.writtenBrightness)) {
        // Do not restore, reapply, or take ownership of the external value.
        [brightnessOwners removeObjectForKey:s.screen];
        s.ownsBrightness = NO;
        s.brightnessSuppressed = YES;
    }
}
#endif
static void initializeCoordinator(void) {
    if (states) return;
    states = [NSHashTable weakObjectsHashTable];
#if TARGET_OS_IOS
    brightnessOwners = [NSMapTable weakToWeakObjectsMapTable];
    NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
    NSArray *names = @[UISceneDidActivateNotification, UISceneWillDeactivateNotification,
        UISceneDidEnterBackgroundNotification, UISceneDidDisconnectNotification,
        UIWindowDidBecomeHiddenNotification, UIWindowDidBecomeVisibleNotification,
        UIScreenBrightnessDidChangeNotification, UIApplicationWillTerminateNotification];
    for (NSNotificationName name in names) {
        // Retained by the center for process lifetime: one bounded set, not per lease.
        [nc addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n) {
            for (ADRLeaseState *s in states.allObjects) {
                if (s.closed) continue;
                if ([n.name isEqual:UIScreenBrightnessDidChangeNotification]) {
                    if (!brightnessMutationDepth && n.object == s.screen) observeBrightness(s);
                    continue;
                }
                if ([n.name isEqual:UIApplicationWillTerminateNotification] ||
                    ([n.name isEqual:UISceneDidDisconnectNotification] && n.object == s.scene)) {
                    [s finish];
                } else if ((n.object == s.scene &&
                    ([n.name isEqual:UISceneWillDeactivateNotification] ||
                     [n.name isEqual:UISceneDidEnterBackgroundNotification])) ||
                    (n.object == s.window && [n.name isEqual:UIWindowDidBecomeHiddenNotification])) {
                    s.lastStatus = [s withdraw];
                } else if (n.object == s.scene || n.object == s.window) {
                    s.lastStatus = [s reconcile];
                }
            }
        }];
    }
#endif
}

@implementation ADRLeaseState
- (ADRStatus)withdraw {
#if TARGET_OS_IOS
    if (self.ownsBrightness) {
        observeBrightness(self);
        if (self.ownsBrightness) {
            [brightnessOwners removeObjectForKey:self.screen];
            self.ownsBrightness = NO;
            brightnessMutationDepth++;
            self.screen.brightness = self.savedBrightness;
            brightnessMutationDepth--;
        }
    }
    if (self.ownsIdle) {
        self.ownsIdle = NO;
        if (idleOwners) --idleOwners;
        if (idleOwners == 0 && UIApplication.sharedApplication.idleTimerDisabled == YES)
            UIApplication.sharedApplication.idleTimerDisabled = savedIdle;
    }
    return ADRStatusOK;
#else
    if (self.assertion != kIOPMNullAssertionID) {
        IOReturn r = IOPMAssertionRelease(self.assertion);
        self.nativeCode = r;
        if (r != kIOReturnSuccess) return ADRStatusIO; // Keep ID for explicit close retry.
        self.assertion = kIOPMNullAssertionID;
        self.ownsIdle = NO;
    }
    return ADRStatusOK;
#endif
}
- (ADRStatus)reconcile {
    if (self.closed) return ADRStatusClosed;
#if TARGET_OS_IOS
    if (!self.window || !self.scene || self.window.windowScene != self.scene ||
        self.scene.screen != self.screen ||
        ![UIApplication.sharedApplication.connectedScenes containsObject:self.scene]) {
        [self withdraw]; self.enabled = NO; return ADRStatusScene;
    }
    if (!self.enabled || !self.hostActive || self.window.hidden || self.window.alpha <= 0 ||
        self.scene.activationState != UISceneActivationStateForegroundActive) return [self withdraw];
    observeBrightness(self);
    ADRLeaseState *owner = [brightnessOwners objectForKey:self.screen];
    if (self.brightness && !self.brightnessSuppressed && owner && owner != self) {
        [self withdraw]; self.enabled = NO; return ADRStatusConflict;
    }
    if (self.brightness && !self.brightnessSuppressed && !self.ownsBrightness) {
        self.savedBrightness = self.screen.brightness;
        self.writtenBrightness = self.brightness.doubleValue;
        brightnessMutationDepth++;
        self.screen.brightness = self.writtenBrightness;
        brightnessMutationDepth--;
        if (!sameBrightness(self.screen.brightness, self.writtenBrightness)) {
            [self withdraw]; self.enabled = NO; return ADRStatusUnavailable;
        }
        self.ownsBrightness = YES;
        [brightnessOwners setObject:self forKey:self.screen];
    }
    if (!self.ownsIdle) {
        if (idleOwners == 0) {
            savedIdle = UIApplication.sharedApplication.idleTimerDisabled;
            UIApplication.sharedApplication.idleTimerDisabled = YES;
            if (!UIApplication.sharedApplication.idleTimerDisabled) {
                [self withdraw]; self.enabled = NO; return ADRStatusUnavailable;
            }
        }
        idleOwners++; self.ownsIdle = YES;
    }
    return ADRStatusOK;
#else
    if (!self.enabled || !self.hostActive) return [self withdraw];
    if (self.assertion != kIOPMNullAssertionID) return ADRStatusOK;
    IOPMAssertionID identifier = kIOPMNullAssertionID;
    IOReturn r = IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleDisplaySleep,
        kIOPMAssertionLevelOn, CFSTR("EXReader reading display lease"), &identifier);
    self.nativeCode = r;
    if (r != kIOReturnSuccess) {
        self.enabled = NO;
        return (r == kIOReturnUnsupported || r == kIOReturnNotPrivileged) ? ADRStatusUnavailable : ADRStatusIO;
    }
    self.assertion = identifier; self.ownsIdle = YES; return ADRStatusOK;
#endif
}
- (ADRStatus)finish {
    self.enabled = NO; self.hostActive = NO;
    ADRStatus s = [self withdraw];
    if (s == ADRStatusOK) { self.closed = YES; [states removeObject:self]; }
    self.lastStatus = s; return s;
}
@end

@interface ADRDisplayLease ()
@property(nonatomic, strong) ADRLeaseState *state;
@end
@implementation ADRDisplayLease
- (instancetype)initPrivate { return [super init]; }
#if TARGET_OS_IOS
+ (instancetype)leaseForWindow:(UIWindow *)window status:(ADRStatus *)outStatus {
#else
+ (instancetype)leaseWithStatus:(ADRStatus *)outStatus {
#endif
    ADRStatus s = ADRStatusOK;
    if (!NSThread.isMainThread) s = ADRStatusWrongThread;
#if TARGET_OS_IOS
    else if (![window isKindOfClass:UIWindow.class] || !window.windowScene ||
             ![UIApplication.sharedApplication.connectedScenes containsObject:window.windowScene]) s = ADRStatusScene;
#endif
    if (s != ADRStatusOK) { if (outStatus) *outStatus = s; return nil; }
    initializeCoordinator();
    if (states.count >= 64) { if (outStatus) *outStatus = ADRStatusLimit; return nil; }
    ADRDisplayLease *lease = [[self alloc] initPrivate];
    lease.state = [ADRLeaseState new];
#if TARGET_OS_IOS
    lease.state.window = window; lease.state.scene = window.windowScene; lease.state.screen = window.windowScene.screen;
#endif
    [states addObject:lease.state];
    if (outStatus) *outStatus = ADRStatusOK;
    return lease;
}
- (ADRStatus)setEnabled:(BOOL)enabled hostActive:(BOOL)hostActive brightness:(NSNumber *)brightness {
    if (!NSThread.isMainThread) return ADRStatusWrongThread;
    ADRLeaseState *s = self.state;
    if (s.closed) return ADRStatusClosed;
    ADRStatus failure = ADRStatusOK;
    if (brightness && (![brightness isKindOfClass:NSNumber.class] ||
        !isfinite(brightness.doubleValue) || brightness.doubleValue < 0 || brightness.doubleValue > 1)) failure = ADRStatusInvalid;
#if TARGET_OS_IOS
    else if (brightness && s.screen != UIScreen.mainScreen) failure = ADRStatusUnsupported;
#else
    else if (brightness) failure = ADRStatusUnsupported;
#endif
    if (failure != ADRStatusOK) {
        s.enabled = NO;
        ADRStatus release = [s withdraw];
        s.lastStatus = release == ADRStatusOK ? failure : release; return s.lastStatus;
    }
#if TARGET_OS_IOS
    observeBrightness(s);
    // Replacing a request is a release/acquire transaction. Validate first; no
    // other owner can intervene because all state is confined to the main thread.
    if ((s.brightness != brightness && ![s.brightness isEqual:brightness]) || s.brightnessSuppressed) {
        [s withdraw];
        s.brightness = brightness; s.brightnessSuppressed = NO;
    }
#endif
    s.enabled = enabled; s.hostActive = hostActive;
    s.lastStatus = [s reconcile]; return s.lastStatus;
}
- (ADRStatus)close {
    if (!NSThread.isMainThread) return ADRStatusWrongThread;
    return [self.state finish];
}
- (ADRStatus)cancel { return [self close]; }
- (NSDictionary *)snapshotWithStatus:(ADRStatus *)outStatus {
    if (!NSThread.isMainThread) { if (outStatus) *outStatus = ADRStatusWrongThread; return nil; }
    ADRLeaseState *s = self.state;
#if TARGET_OS_IOS
    observeBrightness(s);
#endif
    NSMutableDictionary *d = [@{@"closed":@(s.closed), @"enabled":@(s.enabled),
        @"hostActive":@(s.hostActive), @"ownsIdle":@(s.ownsIdle),
        @"lastStatus":@(s.lastStatus), @"nativeCode":@(s.nativeCode)} mutableCopy];
#if TARGET_OS_IOS
    d[@"ownsBrightness"] = @(s.ownsBrightness); d[@"brightnessSuppressed"] = @(s.brightnessSuppressed);
    d[@"activeIdleLeases"] = @(idleOwners);
    d[@"sceneActive"] = @(s.scene && s.scene.activationState == UISceneActivationStateForegroundActive);
#else
    d[@"assertionID"] = @(s.assertion); d[@"ownsBrightness"] = @NO;
#endif
    if (outStatus) *outStatus = ADRStatusOK; return d;
}
- (void)dealloc {
    ADRLeaseState *s = _state;
    if (NSThread.isMainThread) [s finish];
    else dispatch_async(dispatch_get_main_queue(), ^{ [s finish]; });
}
@end
