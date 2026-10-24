/* SPDX-License-Identifier: MIT */
/* Apple Keychain through Security.framework: one kSecClassGenericPassword item
   per account, service "EXReaderCredentials/<namespace>". macOS uses the
   user's default keychain search list; iOS/iPadOS uses the app's data
   protection keychain, device-only and never synchronized. */
#include "backend.h"
#include <Security/Security.h>
#include <TargetConditionals.h>
#include <stdio.h>

static CFStringRef ascii(const char *value) {
  return CFStringCreateWithCString(kCFAllocatorDefault, value, kCFStringEncodingASCII);
}

static CFMutableDictionaryRef item_query(const char *ns, const char *account) {
  char service[32 + EXR_CREDENTIALS_NAMESPACE_MAX];
  CFMutableDictionaryRef query = CFDictionaryCreateMutable(kCFAllocatorDefault, 0,
    &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
  CFStringRef service_value, account_value;
  if (!query) return NULL;
  snprintf(service, sizeof service, "EXReaderCredentials/%s", ns);
  service_value = ascii(service);
  account_value = ascii(account);
  if (!service_value || !account_value) {
    if (service_value) CFRelease(service_value);
    if (account_value) CFRelease(account_value);
    CFRelease(query);
    return NULL;
  }
  CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword);
  CFDictionarySetValue(query, kSecAttrService, service_value);
  CFDictionarySetValue(query, kSecAttrAccount, account_value);
  CFDictionarySetValue(query, kSecAttrSynchronizable, kCFBooleanFalse);
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
  /* Never block on an unlock prompt: a locked keychain is UNAVAILABLE. */
  CFDictionarySetValue(query, kSecUseAuthenticationUI, kSecUseAuthenticationUIFail);
#pragma clang diagnostic pop
  CFRelease(service_value);
  CFRelease(account_value);
  return query;
}

#if TARGET_OS_OSX
/* A locked legacy file keychain blocks SecItem on an unlock prompt even with
   kSecUseAuthenticationUIFail, so refuse before searching: the default
   keychain and every keychain in the search list must be unlocked. */
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
static int unlocked(SecKeychainRef keychain) {
  SecKeychainStatus status = 0;
  return SecKeychainGetStatus(keychain, &status) == errSecSuccess && (status & kSecUnlockStateStatus);
}

static int keychains_unlocked(void) {
  SecKeychainRef keychain = NULL;
  CFArrayRef list = NULL;
  int ok;
  CFIndex i;
  if (SecKeychainCopyDefault(&keychain) != errSecSuccess || !keychain) return 0;
  ok = unlocked(keychain);
  CFRelease(keychain);
  if (ok && SecKeychainCopySearchList(&list) == errSecSuccess && list) {
    for (i = 0; ok && i < CFArrayGetCount(list); ++i)
      ok = unlocked((SecKeychainRef)CFArrayGetValueAtIndex(list, i));
    CFRelease(list);
  } else {
    ok = 0;
  }
  return ok;
}
#pragma clang diagnostic pop
#define REQUIRE_UNLOCKED() do { if (!keychains_unlocked()) return EXR_CRED_UNAVAILABLE; } while (0)
#else
#define REQUIRE_UNLOCKED() do { } while (0)
#endif

static exr_credentials_status map_error(OSStatus status) {
  switch (status) {
    case errSecSuccess: return EXR_CRED_OK;
    case errSecItemNotFound: return EXR_CRED_NOT_FOUND;
    case errSecInteractionNotAllowed: /* locked, or before first unlock */
    case errSecNotAvailable:
    case errSecNoSuchKeychain:
    case errSecNoDefaultKeychain:
    case errSecMissingEntitlement:
    case errSecAuthFailed:
    case errSecUserCanceled:
    case errSecReadOnly:
      return EXR_CRED_UNAVAILABLE;
    default: return EXR_CRED_IO;
  }
}

exr_credentials_status exr_cred_backend_put(const char *ns, const char *account,
                                            const uint8_t *secret, size_t secret_length) {
  CFMutableDictionaryRef query, update;
  CFDataRef data;
  OSStatus status;
  int attempt;
  REQUIRE_UNLOCKED();
  query = item_query(ns, account);
  if (!query) return EXR_CRED_IO;
  data = CFDataCreate(kCFAllocatorDefault, secret, (CFIndex)secret_length);
  update = CFDictionaryCreateMutable(kCFAllocatorDefault, 0,
    &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
  if (!data || !update) {
    if (data) CFRelease(data);
    if (update) CFRelease(update);
    CFRelease(query);
    return EXR_CRED_IO;
  }
  CFDictionarySetValue(update, kSecValueData, data);
  status = SecItemUpdate(query, update);
  /* Add when absent; a concurrent add surfaces as a duplicate, then update. */
  for (attempt = 0; status == errSecItemNotFound && attempt < 2; ++attempt) {
    CFMutableDictionaryRef add = CFDictionaryCreateMutableCopy(kCFAllocatorDefault, 0, query);
    if (!add) { status = errSecAllocate; break; }
    CFDictionarySetValue(add, kSecValueData, data);
#if TARGET_OS_IPHONE
    CFDictionarySetValue(add, kSecAttrAccessible, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly);
#endif
    status = SecItemAdd(add, NULL);
    CFRelease(add);
    if (status == errSecDuplicateItem) status = SecItemUpdate(query, update);
  }
  CFRelease(update);
  CFRelease(data);
  CFRelease(query);
  return map_error(status);
}

exr_credentials_status exr_cred_backend_get(const char *ns, const char *account,
                                            uint8_t *buffer, size_t capacity, size_t *out_length) {
  CFMutableDictionaryRef query;
  CFTypeRef result = NULL;
  exr_credentials_status mapped;
  OSStatus status;
  REQUIRE_UNLOCKED();
  query = item_query(ns, account);
  if (!query) return EXR_CRED_IO;
  CFDictionarySetValue(query, kSecReturnData, kCFBooleanTrue);
  CFDictionarySetValue(query, kSecMatchLimit, kSecMatchLimitOne);
  status = SecItemCopyMatching(query, &result);
  CFRelease(query);
  mapped = map_error(status);
  if (mapped != EXR_CRED_OK) {
    if (result) CFRelease(result);
    return mapped;
  }
  if (!result || CFGetTypeID(result) != CFDataGetTypeID()) {
    if (result) CFRelease(result);
    return EXR_CRED_IO;
  }
  mapped = exr_cred_copy_out(CFDataGetBytePtr((CFDataRef)result), (size_t)CFDataGetLength((CFDataRef)result),
                             buffer, capacity, out_length);
  CFRelease(result);
  return mapped;
}

exr_credentials_status exr_cred_backend_delete(const char *ns, const char *account) {
  CFMutableDictionaryRef query;
  OSStatus status;
  REQUIRE_UNLOCKED();
  query = item_query(ns, account);
  if (!query) return EXR_CRED_IO;
  status = SecItemDelete(query);
  CFRelease(query);
  return map_error(status);
}
