/* SPDX-License-Identifier: MIT */
#ifndef ANDROID_DAV_CONSUMER_H
#define ANDROID_DAV_CONSUMER_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
struct dav_result {
  int status,http,published,reentry,wrong_owner,first_status;
  uint64_t bytes,count;
  char resource[4097],title[1025];
};
void dav_consume(const char *root,const char *auth,const char *directory,const char *action,
  const char *resource,const char *filename,const uint64_t limits[6],struct dav_result *result);
#ifdef __cplusplus
}
#endif
#endif
