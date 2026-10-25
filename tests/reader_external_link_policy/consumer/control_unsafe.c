/* SPDX-License-Identifier: MIT */
/* Negative control for the symbol audit. It is archived into
   link-unsafe-control and never executed: the audit must find these forbidden
   network, process and file references. Without this control a clean audit of
   the real library could not be distinguished from an audit that inspects
   nothing. */
#if defined(_MSC_VER)
#define _CRT_SECURE_NO_WARNINGS
#endif
#include <stdio.h>
#include <stdlib.h>

/* Declared here on purpose: the control must not drag platform headers into the
   build, and only the symbol references matter to the audit. */
extern int getaddrinfo(const char* node, const char* service, const void* hints, void** result);

int link_unsafe_control_launch(const char* command) { return system(command); }

void* link_unsafe_control_read(const char* path) { return fopen(path, "rb"); }

int link_unsafe_control_delete(const char* path) { return remove(path); }

int link_unsafe_control_resolve(const char* host) { return getaddrinfo(host, "80", NULL, NULL); }
