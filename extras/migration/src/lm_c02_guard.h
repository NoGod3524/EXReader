/* SPDX-License-Identifier: MIT */
#ifndef LM_C02_GUARD_H
#define LM_C02_GUARD_H
#include "lm.h"
/* Enabled by the normal Windows CLI build only. The embedded C02 transformer
   never defines LM_C02_PRODUCTION. Every command may enter at most once. */
int lm_c02_guard_command(const char *,lm_err *);
int lm_c02_guard_read(const char *command,const char *target,const char *report,
 const char **physical_target,lm_err *);
#endif
