/* SPDX-License-Identifier: MIT */
#ifndef WH3_TRANSFORM_H
#define WH3_TRANSFORM_H
/* Called synchronously by an admitted owner. No worker outlives these calls.
   The owner reserves and pins all paths; these functions never publish. */
int wh3t_build(void *pack_handle,const char *pack,const char *stage,
 const char *mirror_stage,const char *original_mirror,int allow_partial);
int wh3t_verify(void *pack_handle,const char *target,const char *pack,const char *mirror);
int wh3t_clean_library(const char *target);
#endif
