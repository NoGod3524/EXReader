/* SPDX-License-Identifier: MIT */
/* Independent CMS evaluation of the bundled profile for device colour tests. */
#ifndef EXR_TEST_CMYK_REFERENCE_H
#define EXR_TEST_CMYK_REFERENCE_H
#include <math.h>
#include <stdlib.h>
#ifdef EXR_ENABLE_ICC
#include <lcms2.h>
#include "miniz.h"
#include "default_cmyk_profile.h"
#endif
static void cmyk_reference(const double values[4],unsigned out[3]) {
  unsigned k;
#ifdef EXR_ENABLE_ICC
  mz_ulong size=961644;unsigned char *raw=malloc((size_t)size);
  cmsHPROFILE source,dest;cmsHTRANSFORM transform;double cmyk[4],rgb[3];
  if(!raw || mz_uncompress(raw,&size,default_cmyk_data,sizeof(default_cmyk_data))!=MZ_OK) abort();
  source=cmsOpenProfileFromMem(raw,(cmsUInt32Number)size);dest=cmsCreate_sRGBProfile();
  transform=cmsCreateTransform(source,TYPE_CMYK_DBL,dest,TYPE_RGB_DBL,INTENT_RELATIVE_COLORIMETRIC,
    cmsFLAGS_NOOPTIMIZE|cmsFLAGS_NOCACHE|cmsFLAGS_BLACKPOINTCOMPENSATION);
  if(!transform) abort();
  for(k=0;k<4;k++) cmyk[k]=values[k]*100;
  cmsDoTransform(transform,cmyk,rgb,1);
  for(k=0;k<3;k++) out[k]=(unsigned)floor(fmax(0,fmin(1,rgb[k]))*255+.5);
  cmsDeleteTransform(transform);cmsCloseProfile(source);cmsCloseProfile(dest);free(raw);
#else
  for(k=0;k<3;k++) out[k]=(unsigned)floor((1-fmin(1,values[k]+values[3]))*255+.5);
#endif
}
#endif
