/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
/* Deliberately faulty test-only host: ignore stored font on restart. */
static gint ignore_saved_font(GKeyFile *file,const gchar *group,const gchar *name,GError **error) {
  if(!strcmp(group,"reader")&&!strcmp(name,"font")) return 24;
  return g_key_file_get_integer(file,group,name,error);
}
#define g_key_file_get_integer ignore_saved_font
#include "../../examples/linux/reader.c"
