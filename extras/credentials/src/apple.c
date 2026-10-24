/* SPDX-License-Identifier: MIT */
/* Apple Keychain through Security.framework: one kSecClassGenericPassword item
   per account, service "EXReaderCredentials/<namespace>". On macOS every
   operation is confined to the user's default keychain, which must be
   unlocked; iOS/iPadOS uses the app's data protection keychain, device-only
   and never synchronized. */
#include "backend.h"
#include <Security/Security.h>
#include <TargetConditionals.h>
#include <stdio.h>
/* The macOS file-keychain interfaces (SecKeychain*, kSecUseKeychain,
   kSecMatchSearchList) are deprecated but are what confine an unentitled
   process to one keychain; they are used deliberately. */
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

static CFStringRef ascii(const char *value) {
  return CFStringCreateWithCString(kCFAllocatorDefault, value, kCFStringEncodingASCII);
}

#if TARGET_OS_OSX
typedef SecKeychainRef keychain_ref;
#else
typedef void *keychain_ref;
#endif

static CFMutableDictionaryRef item_query(const char *ns, const char *account, keychain_ref keychain) {
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
#if TARGET_OS_OSX
  {
    CFArrayRef list = CFArrayCreate(kCFAllocatorDefault, (const void **)&keychain, 1, &kCFTypeArrayCallBacks);
    if (!list) {
      CFRelease(service_value);
      CFRelease(account_value);
      CFRelease(query);
      return NULL;
    }
    CFDictionarySetValue(query, kSecMatchSearchList, list);
    CFRelease(list);
  }
#else
  (void)keychain;
#endif
  CFRelease(service_value);
  CFRelease(account_value);
  return query;
}

#if TARGET_OS_OSX
/* A locked legacy file keychain blocks SecItem on an unlock prompt even with
   kSecUseAuthenticationUIFail, so the default keychain's lock state is checked
   first and searches never reach other keychains. */
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
static exr_credentials_status open_keychain(keychain_ref *out) {
  SecKeychainStatus status = 0;
  *out = NULL;
  if (SecKeychainCopyDefault(out) != errSecSuccess || !*out) return EXR_CRED_UNAVAILABLE;
  if (SecKeychainGetStatus(*out, &status) != errSecSuccess || !(status & kSecUnlockStateStatus)) {
    CFRelease(*out);
    *out = NULL;
    return EXR_CRED_UNAVAILABLE;
  }
  return EXR_CRED_OK;
}
#pragma clang diagnostic pop
static void close_keychain(keychain_ref keychain) { if (keychain) CFRelease(keychain); }
#else
static exr_credentials_status open_keychain(keychain_ref *out) { *out = NULL; return EXR_CRED_OK; }
static void close_keychain(keychain_ref keychain) { (void)keychain; }
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
  keychain_ref keychain;
  exr_credentials_status opened = open_keychain(&keychain);
  if (opened != EXR_CRED_OK) return opened;
  query = item_query(ns, account, keychain);
  if (!query) {
    close_keychain(keychain);
    return EXR_CRED_IO;
  }
  data = CFDataCreate(kCFAllocatorDefault, secret, (CFIndex)secret_length);
  update = CFDictionaryCreateMutable(kCFAllocatorDefault, 0,
    &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
  if (!data || !update) {
    if (data) CFRelease(data);
    if (update) CFRelease(update);
    CFRelease(query);
    close_keychain(keychain);
    return EXR_CRED_IO;
  }
  CFDictionarySetValue(update, kSecValueData, data);
  status = SecItemUpdate(query, update);
  /* Add when absent; a concurrent add surfaces as a duplicate, then update. */
  for (attempt = 0; status == errSecItemNotFound && attempt < 2; ++attempt) {
    CFMutableDictionaryRef add = CFDictionaryCreateMutableCopy(kCFAllocatorDefault, 0, query);
    if (!add) { status = errSecAllocate; break; }
    CFDictionarySetValue(add, kSecValueData, data);
#if TARGET_OS_OSX
    CFDictionaryRemoveValue(add, kSecMatchSearchList);
    CFDictionarySetValue(add, kSecUseKeychain, keychain);
#else
    CFDictionarySetValue(add, kSecAttrAccessible, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly);
#endif
    status = SecItemAdd(add, NULL);
    CFRelease(add);
    if (status == errSecDuplicateItem) status = SecItemUpdate(query, update);
  }
  CFRelease(update);
  CFRelease(data);
  CFRelease(query);
  close_keychain(keychain);
  return map_error(status);
}

exr_credentials_status exr_cred_backend_get(const char *ns, const char *account,
                                            uint8_t *buffer, size_t capacity, size_t *out_length) {
  CFMutableDictionaryRef query;
  CFTypeRef result = NULL;
  exr_credentials_status mapped;
  OSStatus status;
  keychain_ref keychain;
  mapped = open_keychain(&keychain);
  if (mapped != EXR_CRED_OK) return mapped;
  query = item_query(ns, account, keychain);
  if (!query) {
    close_keychain(keychain);
    return EXR_CRED_IO;
  }
  CFDictionarySetValue(query, kSecReturnData, kCFBooleanTrue);
  CFDictionarySetValue(query, kSecMatchLimit, kSecMatchLimitOne);
  status = SecItemCopyMatching(query, &result);
  CFRelease(query);
  close_keychain(keychain);
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
  keychain_ref keychain;
  exr_credentials_status opened = open_keychain(&keychain);
  if (opened != EXR_CRED_OK) return opened;
  query = item_query(ns, account, keychain);
  if (!query) {
    close_keychain(keychain);
    return EXR_CRED_IO;
  }
  status = SecItemDelete(query);
  CFRelease(query);
  close_keychain(keychain);
  return map_error(status);
}
