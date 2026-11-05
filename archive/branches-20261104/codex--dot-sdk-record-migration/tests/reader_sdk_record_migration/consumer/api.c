/* Installed public C ABI consumer; no private headers. */
#include <reader_reading_commands.h>
#include <reader_navigation.h>
#include <exr/core.h>
#include <stdio.h>
int main(void) {
  reader_rc_error error = {0}; reader_rc_result result = {0};
  if (reader_rc_apply(0, 0, &result, &error) != READER_RC_ARGUMENT) return 1;
  printf("SDK=%s commands=%s state=%s navigation=%s\n", exr_version(), READER_READING_COMMANDS_VERSION, READER_READING_STATE_VERSION, READER_NAVIGATION_VERSION);
  return 0;
}
