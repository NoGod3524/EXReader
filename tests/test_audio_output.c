/* SPDX-License-Identifier: GPL-3.0-only */
#include "exreader.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static exr_error error;
static unsigned checks;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"line %d: %s (%d: %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
#define OK(x) CHECK((x)==EXR_OK)
static void invalid(void) {
  static const uint32_t rates[]={0,1,7999,192001,UINT32_MAX};
  static const uint32_t channels[]={0,3,UINT32_MAX};
  size_t i,written=123; exr_audio_output *output=(exr_audio_output *)(uintptr_t)1;
  const char *backend=exr_audio_output_backend();
#if defined(_WIN32)
  CHECK(backend && !strcmp(backend,"waveOut"));
#elif defined(__APPLE__)
  CHECK(backend && !strcmp(backend,"AudioQueue"));
#elif defined(__ANDROID__)
  CHECK(backend && !strcmp(backend,"OpenSL ES"));
#elif defined(__linux__)
  CHECK(backend && !strcmp(backend,"ALSA"));
#else
  CHECK(!backend);
#endif
  CHECK(exr_audio_output_open(48000,2,NULL,&error)==EXR_ARGUMENT);
  for(i=0;i<sizeof(rates)/sizeof(*rates);i++) {
    output=(exr_audio_output *)(uintptr_t)1;
    CHECK(exr_audio_output_open(rates[i],2,&output,&error)==EXR_ARGUMENT && !output);
  }
  for(i=0;i<sizeof(channels)/sizeof(*channels);i++) {
    output=(exr_audio_output *)(uintptr_t)1;
    CHECK(exr_audio_output_open(48000,channels[i],&output,&error)==EXR_ARGUMENT && !output);
  }
  CHECK(exr_audio_output_write(NULL,NULL,0,&written,&error)==EXR_ARGUMENT && !written);
  CHECK(exr_audio_output_write(NULL,NULL,0,NULL,&error)==EXR_ARGUMENT);
  written=123; CHECK(exr_audio_output_pending(NULL,&written,&error)==EXR_ARGUMENT && !written);
  CHECK(exr_audio_output_pending(NULL,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_audio_output_pause(NULL,1,&error)==EXR_ARGUMENT);
  CHECK(exr_audio_output_flush(NULL,&error)==EXR_ARGUMENT); exr_audio_output_free(NULL);
}
static void device(void) {
  exr_audio_output *output=NULL; float samples[8192]={0}; size_t written=123,pending=123; exr_status status;
  /* Explicit manual mode only: opening a default device and submitting silence
     must never happen during ordinary CTest execution. */
  OK(exr_audio_output_open(48000,2,&output,&error)); CHECK(output);
  OK(exr_audio_output_pending(output,&pending,&error)); CHECK(!pending);
  OK(exr_audio_output_pause(output,1,&error));
  samples[0]=NAN; CHECK(exr_audio_output_write(output,samples,4096,&written,&error)==EXR_ARGUMENT && !written);
  samples[0]=INFINITY; written=123; CHECK(exr_audio_output_write(output,samples,4096,&written,&error)==EXR_ARGUMENT && !written);
  samples[0]=0;
  CHECK(exr_audio_output_write(output,samples,65537,&written,&error)==EXR_LIMIT && !written);
  CHECK(exr_audio_output_write(output,NULL,1,&written,&error)==EXR_ARGUMENT && !written);
  CHECK(exr_audio_output_write(output,samples,1,NULL,&error)==EXR_ARGUMENT);
  CHECK(exr_audio_output_pending(output,NULL,&error)==EXR_ARGUMENT);
  OK(exr_audio_output_write(output,samples,4096,&written,&error)); CHECK(!written);
  OK(exr_audio_output_flush(output,&error)); OK(exr_audio_output_pending(output,&pending,&error)); CHECK(!pending);
  OK(exr_audio_output_write(output,samples,4096,&written,&error)); CHECK(!written);
  OK(exr_audio_output_pause(output,0,&error));
  OK(exr_audio_output_write(output,samples,4096,&written,&error)); CHECK(written>0 && written<=4096);
  OK(exr_audio_output_pending(output,&pending,&error));
  status=exr_audio_output_pause(output,1,&error); CHECK(status==EXR_OK || status==EXR_FORMAT);
  OK(exr_audio_output_flush(output,&error)); OK(exr_audio_output_pending(output,&pending,&error)); CHECK(!pending);
  exr_audio_output_free(output);
}
int main(int argc,char **argv) {
  CHECK(argc==1 || (argc==2 && !strcmp(argv[1],"--device"))); invalid(); if(argc==2) device();
  printf("Native audio output passed (%u checks; %s)\n",checks,exr_audio_output_backend() ? exr_audio_output_backend() : "no backend"); return 0;
}
