/* SPDX-License-Identifier: MIT */
#include <stdio.h>
#include <string.h>
#include "e1_platform.h"
#include "load_counters.h"
int main(int argc,char **argv) {
  if(!e1_pin()) return 3;
  if(argc==2 && !strcmp(argv[1],"--identity")) {
    printf("{\"reference_steps\":%" PRIu64 "}\n",perf_reference_steps());return 0;
  }
  load_init();
  if(argc==2 && !strcmp(argv[1],"--self-check")) {
    load_stamp a=load_read(),b=load_read();
    printf("{");load_print_stamp("empty",load_delta(a,b));
    a=load_read();Sleep(100);b=load_read();
    putchar(',');load_print_stamp("sleep100",load_delta(a,b));
    load_measure m=load_reference();putchar(',');load_print_measure("busy",m);
    printf("}\n");return 0;
  }
  load_measure warmup=load_reference();printf("{");load_print_measure("warmup",warmup);
  double elapsed[31];printf(",\"samples\":[");
  for(int i=0;i<31;i++) {
    load_measure m=load_reference();elapsed[i]=m.wall_ms;printf("%s{",i?",":"");
    load_print_measure("reference",m);putchar('}');
  }
  printf("],\"reference_ms\":[");
  for(int i=0;i<31;i++) printf("%s%.6f",i?",":"",elapsed[i]);
  printf("]}\n");return 0;
}
