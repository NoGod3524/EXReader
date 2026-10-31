/* SPDX-License-Identifier: MIT */
#ifndef PC02_TRANSFORM_H
#define PC02_TRANSFORM_H
/* Synchronous private-image operations. The provider reserves, copies and
   pins every object under its live pc02 owner; these functions never publish. */
int pc02t_build(int pack_descriptor,const char *pack,const char *stage,
 const char *mirror_stage,const char *original_mirror,int allow_partial);
int pc02t_verify(int pack_descriptor,const char *target,const char *pack,
 const char *mirror);
int pc02t_original_verify(const char *private_target,const char *private_mirror_or_null);
#endif
