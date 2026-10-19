/* SPDX-License-Identifier: MIT */
#include <exreader.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
/* Decode only; a host can send these interleaved float frames to its device. */
static int example_main(int argc,char **argv) {
  exr_wave *wave=NULL; const exr_wave_info *info; exr_error error={0}; exr_status status;
  float *samples=NULL,peak=0; uint64_t at=0,frames; uint32_t rate,channels;
  if(argc!=2) { fprintf(stderr,"usage: exreader-wave-example input.wav\n"); return 2; }
  status=exr_wave_open(argv[1],NULL,&wave,&error); if(status!=EXR_OK) goto finish;
  info=exr_wave_format(wave); frames=info->frames; rate=info->sample_rate; channels=info->channels;
  samples=malloc((size_t)1024*channels*sizeof(*samples));
  if(!samples) { fprintf(stderr,"sample buffer allocation failed\n"); exr_wave_free(wave); return 1; }
  while(at<frames) {
    size_t read=0,i; status=exr_wave_read(wave,at,1024,samples,&read,NULL,&error); if(status!=EXR_OK) goto finish;
    if(!read) { fprintf(stderr,"unexpected PCM EOF\n"); free(samples); exr_wave_free(wave); return 1; }
    for(i=0;i<read*channels;i++) { float value=samples[i]<0 ? -samples[i] : samples[i]; if(value>peak) peak=value; }
    at+=read;
  }
  printf("rate=%u channels=%u frames=%" PRIu64 " decoded=%" PRIu64 " peak=%.6f\n",rate,channels,frames,at,(double)peak);
finish:
  if(status!=EXR_OK) fprintf(stderr,"%d: %s\n",status,error.message);
  free(samples); exr_wave_free(wave); return status==EXR_OK ? 0 : 1;
}
#include "entry.h"
