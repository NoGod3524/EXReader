/* SPDX-License-Identifier: GPL-3.0-only */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include <exreader.h>
#include <inttypes.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#include <windows.h>
#endif
static volatile sig_atomic_t interrupted;
static void stop(int signal_number) { (void)signal_number; interrupted=1; }
static void wait_for_device(void) {
#ifdef _WIN32
  Sleep(10);
#else
  struct timespec delay={0,10000000}; nanosleep(&delay,NULL);
#endif
}
/* Inspection is silent. Playback requires an explicit --play argument. Hosts
   may instead route the same decoder to their own PCM provider/device policy. */
static int example_main(int argc,char **argv) {
  exr_pcm *pcm=NULL; exr_audio_output *output=NULL; exr_error error={0}; exr_status status=EXR_OK;
  const exr_pcm_info *info; float *samples=NULL,peak=0; uint64_t at=0; uint32_t rate=0,channels=0; int play=0;
  if(argc<2 || argc>3 || (argc==3 && strcmp(argv[2],"--play"))) {
    fprintf(stderr,"usage: exreader-pcm-example input.wav|input.flac|input.mp3 [--play]\n"); return 2;
  }
  play=argc==3; status=exr_pcm_open(argv[1],NULL,&pcm,&error); if(status!=EXR_OK) goto finish;
  info=exr_pcm_format(pcm); rate=info->sample_rate; channels=info->channels;
  samples=malloc(1024*channels*sizeof(*samples)); if(!samples) { status=EXR_MEMORY; strcpy(error.message,"sample buffer allocation failed"); goto finish; }
  if(play) { status=exr_audio_output_open(rate,channels,&output,&error); if(status!=EXR_OK) goto finish; signal(SIGINT,stop); }
  while(!interrupted) {
    size_t read=0,i,submitted=0; unsigned waits=0;
    status=exr_pcm_read(pcm,at,1024,samples,&read,NULL,&error); if(status!=EXR_OK || !read) break;
    for(i=0;i<read*channels;i++) { float v=fabsf(samples[i]); if(v>peak) peak=v; }
    while(output && submitted<read && !interrupted) {
      size_t written=0;
      status=exr_audio_output_write(output,samples+submitted*channels,read-submitted,&written,&error); submitted+=written;
      if(status!=EXR_OK) goto finish;
      if(written) waits=0;
      else {
        if(++waits>3000) { status=EXR_IO; strcpy(error.message,"audio device did not accept samples for 30 seconds"); goto finish; }
        wait_for_device();
      }
    }
    at+=read;
  }
  if(status==EXR_OK && output && !interrupted) {
    unsigned waits=0; size_t pending=0;
    do {
      status=exr_audio_output_pending(output,&pending,&error); if(status!=EXR_OK || !pending || interrupted) break;
      if(++waits>3000) { status=EXR_IO; strcpy(error.message,"audio device did not drain for 30 seconds"); break; }
      wait_for_device();
    } while(pending);
  }
  if(status==EXR_OK) printf("rate=%u channels=%u decoded=%" PRIu64 " peak=%.6f%s\n",rate,channels,at,(double)peak,play ? " played" : "");
finish:
  if(status!=EXR_OK) fprintf(stderr,"%d: %s\n",status,error.message);
  if(output) { exr_error ignored={0}; exr_audio_output_flush(output,&ignored); }
  exr_audio_output_free(output); exr_pcm_free(pcm); free(samples); return interrupted ? 130 : status==EXR_OK ? 0 : 1;
}
#include "entry.h"
