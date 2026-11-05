// SPDX-License-Identifier: MIT
#import <Foundation/Foundation.h>
#import <ADRDisplayLease.h>
#import <CommonCrypto/CommonDigest.h>
#import <dispatch/dispatch.h>
#include <unistd.h>
#include <math.h>
#import "identity.h"

static NSMutableArray *cases;
static NSString *fileSHA(NSString *path) {
    NSData *data = [NSData dataWithContentsOfFile:path];
    if (!data.length) return @"";
    CC_SHA256_CTX context; CC_SHA256_Init(&context);
    const unsigned char *bytes = data.bytes;
    NSUInteger remaining = data.length;
    while (remaining) {
        CC_LONG n = (CC_LONG)MIN(remaining, (NSUInteger)1048576);
        CC_SHA256_Update(&context, bytes, n); bytes += n; remaining -= n;
    }
    unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256_Final(digest, &context);
    NSMutableString *s = [NSMutableString string];
    for (int i=0; i<CC_SHA256_DIGEST_LENGTH; ++i) [s appendFormat:@"%02x", digest[i]];
    return s;
}
static NSDictionary *identity(void) {
    return @{@"source":@ADR_PROBE_SOURCE, @"librarySource":@(ADRDisplaySourceRevision()),
        @"run":@ADR_PROBE_RUN, @"attempt":@ADR_PROBE_ATTEMPT,
        @"librarySHA256":@ADR_LIBRARY_SHA, @"headerSHA256":@ADR_HEADER_SHA,
        @"binarySHA256":fileSHA(NSBundle.mainBundle.executablePath ?: NSProcessInfo.processInfo.arguments[0]),
        @"bundleIdentifier":NSBundle.mainBundle.bundleIdentifier ?: @"",
        @"executableName":(NSBundle.mainBundle.executablePath ?: NSProcessInfo.processInfo.arguments[0]).lastPathComponent,
#if TARGET_OS_IOS
        @"appInfoSHA256":fileSHA([NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"Info.plist"]),
#else
        @"appInfoSHA256":@"",
#endif
        @"pid":@(getpid()), @"platform":@ADR_PLATFORM};
}
static void record(NSString *name, NSString *status, NSString *detail) {
    if (!cases) cases = [NSMutableArray new];
    for (NSDictionary *c in cases) if ([c[@"name"] isEqual:name]) abort();
    [cases addObject:@{@"name":name, @"status":status, @"detail":detail}];
    NSLog(@"ADR_CASE %@ %@ %@", name, status, detail);
}
static void check(NSString *name, BOOL ok) { record(name, ok ? @"PASS" : @"FAIL", @"real native API observation"); }
static void pending(NSString *name, NSString *why) { record(name, @"PENDING", why); }
static NSDictionary *snapshot(ADRDisplayLease *lease) { return [lease snapshotWithStatus:NULL]; }
static BOOL owns(ADRDisplayLease *lease) { return [snapshot(lease)[@"ownsIdle"] boolValue]; }
static void writeJSON(NSDictionary *value, NSString *path) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingPrettyPrinted error:&error];
    if (!data || ![data writeToFile:path options:NSDataWritingAtomic error:&error]) abort();
}
static void writeReport(NSString *path, NSString *stage) {
    writeJSON(@{@"schema":@1, @"identity":identity(), @"stage":stage,
        @"cases":cases ?: @[], @"physicalSleepVerified":@NO, @"physicalBacklightVerified":@NO}, path);
}
