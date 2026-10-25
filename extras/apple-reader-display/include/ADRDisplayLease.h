// SPDX-License-Identifier: MIT
#import <Foundation/Foundation.h>
#import <TargetConditionals.h>
#if TARGET_OS_IOS
#import <UIKit/UIKit.h>
#endif

NS_ASSUME_NONNULL_BEGIN
typedef NS_ENUM(NSInteger, ADRStatus) {
    ADRStatusOK = 0, ADRStatusWrongThread, ADRStatusInvalid, ADRStatusClosed,
    ADRStatusScene, ADRStatusConflict, ADRStatusUnavailable, ADRStatusIO,
    ADRStatusUnsupported, ADRStatusLimit
};
FOUNDATION_EXPORT NSString *ADRStatusMessage(ADRStatus status);
FOUNDATION_EXPORT const char *ADRDisplaySourceRevision(void);

/** Native display lease, version 1.0. All calls (including snapshot) are main-thread
 * only. No callbacks, persistence, SDK dependency or permission prompts. At most
 * 64 live leases per process. Retain the lease while needed. close/cancel release
 * synchronously on the main thread and are idempotent; both permanently close it.
 * Off-main destruction queues cleanup on main; use explicit close for a boundary.
 * Wrong-thread calls make no changes. Other update errors withdraw this lease's
 * requests, never another lease's requests. A fresh update may retry.
 */
@interface ADRDisplayLease : NSObject
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;
#if TARGET_OS_IOS
/** Binds to this real connected UIWindowScene, window and screen. A hidden or
 * inactive scene may be bound, but holds no requests. Window/screen migration
 * requires a new lease. External screens support idle only; brightness returns
 * Unsupported. UIKit notifications release on inactivity, hidden window or
 * disconnect; activation reacquires only an explicitly enabled request.
 */
+ (nullable instancetype)leaseForWindow:(UIWindow *)window status:(nullable ADRStatus *)status;
#else
+ (nullable instancetype)leaseWithStatus:(nullable ADRStatus *)status;
#endif
/** hostActive is explicit host policy, ANDed with real visibility/scene state on
 * iOS. brightness=nil means idle-only; otherwise finite [0,1]. macOS brightness
 * returns Unsupported. iOS brightness is screen-wide, exclusive among leases.
 * Idle is application-wide, reference-counted among leases. Last release only
 * restores saved state if the current value still equals this owner's write.
 * Observed external brightness changes relinquish the brightness claim until
 * a new explicit update. Same-value external writes cannot be distinguished.
 */
- (ADRStatus)setEnabled:(BOOL)enabled hostActive:(BOOL)hostActive brightness:(nullable NSNumber *)brightness;
- (ADRStatus)close;
- (ADRStatus)cancel;
/** Fixed, non-sensitive diagnostics; nil on wrong thread. assertionID on macOS is
 * diagnostic only, must not be released or retained by callers. */
- (nullable NSDictionary<NSString *, id> *)snapshotWithStatus:(nullable ADRStatus *)status;
@end
NS_ASSUME_NONNULL_END
