/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef EXR_BMFF_INTERNAL_H
#define EXR_BMFF_INTERNAL_H
#include "internal.h"
#define EXR_BMFF_TYPE(a,b,c,d) ((uint32_t)(a)<<24|(uint32_t)(b)<<16|(uint32_t)(c)<<8|(uint32_t)(d))
typedef struct { uint64_t data,end; uint32_t type; } exr_bmff_box;
typedef struct { const exr_source *source; const exr_control *control; exr_error *error; uint64_t bytes,limit; unsigned boxes; } exr_bmff_reader;
uint32_t exr_bmff_be16(const unsigned char *p);
uint32_t exr_bmff_be32(const unsigned char *p);
uint64_t exr_bmff_be64(const unsigned char *p);
exr_status exr_bmff_fail(exr_bmff_reader *io,const char *message);
exr_status exr_bmff_read(exr_bmff_reader *io,uint64_t at,void *out,size_t size);
exr_status exr_bmff_at(exr_bmff_reader *io,uint64_t at,uint64_t end,exr_bmff_box *box);
exr_status exr_bmff_child(exr_bmff_reader *io,const exr_bmff_box *parent,uint32_t type,int required,exr_bmff_box *out);
exr_status exr_bmff_header(exr_bmff_reader *io,const exr_bmff_box *box,void *bytes,size_t size);
exr_status exr_bmff_time(exr_bmff_reader *io,const exr_bmff_box *box,uint32_t *scale,uint64_t *duration);
#endif
