// SPDX-License-Identifier: MIT
// Host-owned lease. Install the library, then #import only its public header.
#import <ADRDisplayLease.h>

#if TARGET_OS_IOS
ADRDisplayLease *beginReaderDisplay(UIWindow *window, ADRStatus *status) {
    ADRDisplayLease *lease = [ADRDisplayLease leaseForWindow:window status:status];
#else
ADRDisplayLease *beginReaderDisplay(ADRStatus *status) {
    ADRDisplayLease *lease = [ADRDisplayLease leaseWithStatus:status];
#endif
    if (!lease) return nil;
    *status = [lease setEnabled:YES hostActive:YES brightness:nil];
    if (*status != ADRStatusOK) { [lease close]; return nil; }
    return lease; // Retain on the owning reader controller; close on reader exit.
}
