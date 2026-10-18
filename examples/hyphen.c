/* SPDX-License-Identifier: GPL-3.0-only */
#include <exreader.h>
#include <stdio.h>
#include <string.h>
int main(void) {
  /* Original demonstration patterns, not a complete English dictionary. */
  const char patterns[]="hy1phen phen1ation";
  const char word[]="hyphenation";
  exr_hyphen_pattern_input input={sizeof(input),"en",patterns,sizeof(patterns)-1,2,2};
  exr_hyphenator *hyphenator=NULL; exr_error error={0}; unsigned char points[sizeof(word)]; size_t i;
  if(exr_hyphenator_create_patterns(&input,1,0,NULL,&hyphenator,&error)!=EXR_OK ||
     exr_hyphenator_breaks(hyphenator,"en-US",word,strlen(word),points,NULL,&error)!=EXR_OK) {
    fprintf(stderr,"%s\n",error.message); exr_hyphenator_free(hyphenator); return 1;
  }
  for(i=0;i<sizeof(word);i++) if(points[i]!=(i==2 || i==6)) { exr_hyphenator_free(hyphenator); return 1; }
  for(i=0;word[i];i++) { if(points[i]) putchar('-'); putchar(word[i]); }
  putchar('\n'); exr_hyphenator_free(hyphenator); return 0;
}
