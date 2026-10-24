/* SPDX-License-Identifier: MIT */
#include <reader_preferences.h>
#include <stdio.h>
int main(int argc,char **argv) {
  reader_preferences p=reader_preferences_defaults();reader_preferences_error error={0};
  if(argc!=2) return 2;
  reader_preferences_status status=reader_preferences_load(argv[1],&p,NULL,&error);
  printf("{\"status\":%u,\"font\":%.6g,\"line\":%.6g,\"paragraph\":%.6g,\"margin\":%.6g,\"theme\":%u,\"direction\":%u,\"input\":%u,\"zoom\":%u}\n",
    (unsigned)status,(double)p.font_size,(double)p.line_spacing,(double)p.paragraph_spacing,(double)p.margin,p.theme,p.page_turn_direction,p.page_turn_input,p.fixed_page_zoom);
  return status==READER_PREFERENCES_OK ? 0:1;
}
