/* SPDX-License-Identifier: MIT */
#ifndef READER_LINK_POLICY_TEST_HOOKS_H
#define READER_LINK_POLICY_TEST_HOOKS_H
/* Only compiled into the source-built test worker. The installed library never
   defines READER_LINK_POLICY_TEST_HOOKS, so allocation can not be steered from
   the environment or a caller. Counters are plain (single-threaded use); they
   are inert until rlp_test_begin is called. */
void rlp_test_begin(long fail_at); /* fail the Nth (1-based) allocation, 0 = never; resets counters */
void rlp_test_end(void);
long rlp_test_allocations(void);
long rlp_test_live(void);
#endif
