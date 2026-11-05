/* SPDX-License-Identifier: MIT */
#ifndef S06_HANDOFF_INTERNAL_H
#define S06_HANDOFF_INTERNAL_H
#include "s06_handoff.h"
#include <exr_desktop_drop.h>

void s06_handoff_collect(exr_drop_status status, exr_drop_request *request,
    const char *platform_note, s06_handoff_result *out);

#endif
