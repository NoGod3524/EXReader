/* SPDX-License-Identifier: MIT
 * Deliberate harness faults: prove both runtimes report before trusting a scan.
 * These are positive controls, never counted as product findings.
 */
#include <stdlib.h>
#include <string.h>
#include <limits.h>
int main(int argc,char **argv) {
  if(argc!=2) return 2;
  if(!strcmp(argv[1],"asan")) {
    volatile int index=8;
    volatile char *p=malloc(8);
    if(!p) return 2;
    p[index]=1;
    free((void *)p);
  } else if(!strcmp(argv[1],"ubsan")) {
    volatile int n=INT_MAX;
    volatile int result=n+1;
    (void)result;
  } else return 2;
  return 0;
}
