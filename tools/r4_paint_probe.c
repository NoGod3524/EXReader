/* SPDX-License-Identifier: MIT */
/* Same public paint consumer and private work counter for both CI SDKs. */
#define main original_paint_tests
#include "../tests/test_paint_source.c"
#undef main
int main(void) { clipped_budget(0);return 0; }
