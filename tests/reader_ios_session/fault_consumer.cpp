/* SPDX-License-Identifier: MIT */
/* The unchanged installed session consumer runs on the app's background owner. */
#define main ios_fault_session_probe
#include "../reader_session/consumer/main.cpp"
#undef main
