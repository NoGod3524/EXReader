// SPDX-License-Identifier: MIT
#import "ProbeSupport.h"
#import <IOKit/pwr_mgt/IOPMLib.h>
#include <signal.h>

static NSDictionary *properties(ADRDisplayLease *lease) {
    IOPMAssertionID aid = [snapshot(lease)[@"assertionID"] unsignedIntValue];
    if (aid == kIOPMNullAssertionID) return nil;
    CFDictionaryRef result = IOPMAssertionCopyProperties(aid);
    return CFBridgingRelease(result);
}
int main(int argc, const char **argv) {
    @autoreleasepool {
        if (argc < 3) return 2;
        NSString *mode = @(argv[1]), *out = @(argv[2]);
        if ([mode isEqual:@"query"]) {
            if (argc != 4) return 2;
            CFDictionaryRef byProcess = NULL;
            IOReturn rc = IOPMCopyAssertionsByProcess(&byProcess);
            NSDictionary *dict = CFBridgingRelease(byProcess);
            NSArray *list = dict[@(atoi(argv[3]))] ?: @[];
            // Serialize only public non-sensitive count/type, not unrelated process details.
            NSUInteger display = 0;
            for (NSDictionary *p in list)
                if ([p[(__bridge NSString *)kIOPMAssertionTypeKey] isEqual:(__bridge NSString *)kIOPMAssertionTypePreventUserIdleDisplaySleep]) ++display;
            writeJSON(@{@"identity":identity(), @"queriedPID":@(atoi(argv[3])),
                @"returnCode":@(rc), @"displayAssertions":@(display)}, out);
            return rc == kIOReturnSuccess ? 0 : 3;
        }
        ADRStatus st = ADRStatusOK;
        ADRDisplayLease *a = [ADRDisplayLease leaseWithStatus:&st];
        if ([mode isEqual:@"hold"]) {
            st = [a setEnabled:YES hostActive:YES brightness:nil];
            writeJSON(@{@"identity":identity(), @"status":@(st), @"snapshot":snapshot(a),
                @"queriedProperties":properties(a) != nil ? @YES : @NO}, out);
            if (st != ADRStatusOK) return 3;
            for (;;) pause(); // Bounded by Actions supervisor; SIGKILL is intentional.
        }
        check(@"mac_create", a && st == ADRStatusOK);
        check(@"mac_initial_no_assertion", !owns(a) && !properties(a));
        check(@"mac_host_inactive", [a setEnabled:YES hostActive:NO brightness:nil] == ADRStatusOK && !properties(a));
        st = [a setEnabled:YES hostActive:YES brightness:nil];
        check(@"mac_real_assertion_created", st == ADRStatusOK && owns(a));
        NSDictionary *p = properties(a);
        check(@"mac_real_assertion_query", p &&
            [p[(__bridge NSString *)kIOPMAssertionTypeKey] isEqual:(__bridge NSString *)kIOPMAssertionTypePreventUserIdleDisplaySleep] &&
            [p[(__bridge NSString *)kIOPMAssertionLevelKey] intValue] == kIOPMAssertionLevelOn);
        unsigned int first = [snapshot(a)[@"assertionID"] unsignedIntValue];
        check(@"mac_repeated_enable_same_id", [a setEnabled:YES hostActive:YES brightness:nil] == ADRStatusOK &&
            [snapshot(a)[@"assertionID"] unsignedIntValue] == first);
        ADRDisplayLease *b = [ADRDisplayLease leaseWithStatus:NULL];
        check(@"mac_dual_distinct_ids", [b setEnabled:YES hostActive:YES brightness:nil] == ADRStatusOK &&
            [snapshot(b)[@"assertionID"] unsignedIntValue] != first && properties(b));
        check(@"mac_close_preserves_other", [a close] == ADRStatusOK && properties(b) && !owns(a));
        CFDictionaryRef released = IOPMAssertionCopyProperties(first);
        check(@"mac_released_id_absent", released == NULL);
        if (released) CFRelease(released);
        check(@"mac_close_idempotent", [a close] == ADRStatusOK);
        check(@"mac_closed_update_rejected", [a setEnabled:YES hostActive:YES brightness:nil] == ADRStatusClosed);
        check(@"mac_policy_deactivate_release", [b setEnabled:YES hostActive:NO brightness:nil] == ADRStatusOK && !properties(b));
        check(@"mac_policy_reactivate", [b setEnabled:YES hostActive:YES brightness:nil] == ADRStatusOK && properties(b));
        check(@"mac_nan_releases", [b setEnabled:YES hostActive:YES brightness:@(NAN)] == ADRStatusInvalid && !properties(b));
        check(@"mac_inf_rejected", [b setEnabled:YES hostActive:YES brightness:@(INFINITY)] == ADRStatusInvalid);
        check(@"mac_negative_rejected", [b setEnabled:YES hostActive:YES brightness:@(-0.1)] == ADRStatusInvalid);
        check(@"mac_above_one_rejected", [b setEnabled:YES hostActive:YES brightness:@1.1] == ADRStatusInvalid);
        check(@"mac_brightness_unsupported", [b setEnabled:YES hostActive:YES brightness:@0.5] == ADRStatusUnsupported && !owns(b));
        check(@"mac_retry_after_error", [b setEnabled:YES hostActive:YES brightness:nil] == ADRStatusOK && properties(b));
        __block BOOL wrong = NO;
        dispatch_semaphore_t finished = dispatch_semaphore_create(0);
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_DEFAULT, 0), ^{
            ADRStatus e = ADRStatusOK;
            wrong = [b setEnabled:NO hostActive:NO brightness:nil] == ADRStatusWrongThread &&
                [b close] == ADRStatusWrongThread && [b cancel] == ADRStatusWrongThread &&
                [b snapshotWithStatus:&e] == nil && e == ADRStatusWrongThread &&
                [ADRDisplayLease leaseWithStatus:&e] == nil && e == ADRStatusWrongThread;
            dispatch_semaphore_signal(finished);
        });
        if (dispatch_semaphore_wait(finished, dispatch_time(DISPATCH_TIME_NOW, 10*NSEC_PER_SEC)) != 0) abort();
        check(@"mac_wrong_thread_no_mutation", wrong && properties(b));
        check(@"mac_cancel_releases", [b cancel] == ADRStatusOK && !properties(b));
        NSMutableArray *leases = [NSMutableArray new];
        for (int i=0;i<64;i++) { ADRDisplayLease *l=[ADRDisplayLease leaseWithStatus:NULL]; if(l)[leases addObject:l]; }
        ADRStatus limit;
        check(@"mac_lease_limit", leases.count == 64 && [ADRDisplayLease leaseWithStatus:&limit] == nil && limit == ADRStatusLimit);
        for (ADRDisplayLease *l in leases) [l close];
        ADRDisplayLease *again = [ADRDisplayLease leaseWithStatus:NULL];
        check(@"mac_limit_recovery", again != nil); [again close];
        __block unsigned int droppedID;
        @autoreleasepool {
            ADRDisplayLease *d = [ADRDisplayLease leaseWithStatus:NULL];
            [d setEnabled:YES hostActive:YES brightness:nil]; droppedID = [snapshot(d)[@"assertionID"] unsignedIntValue];
            d = nil;
        }
        CFDictionaryRef dropped = IOPMAssertionCopyProperties(droppedID);
        check(@"mac_deallocation_release", droppedID != kIOPMNullAssertionID && dropped == NULL);
        if (dropped) CFRelease(dropped);
        pending(@"mac_physical_sleep", @"Hosted runner has no observed physical display/sleep measurement");
        writeReport(out, @"complete");
        for (NSDictionary *c in cases) if ([c[@"status"] isEqual:@"FAIL"]) return 1;
    }
    return 0;
}
