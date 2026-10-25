/* SPDX-License-Identifier: MIT */
#include <reader_reading_state.h>
#include "windows_wave3_types.h"
#ifndef EXR_READER_SELECTOR_BYTES_CANDIDATE
#error "The wave-3 bridge belongs to the explicit raw reading-state family"
#endif
reader_rs_status reader_rs_encode_retained_raw_v3(reader_revisions *,const reader_rs_envelope *,const reader_rs_capture *,
  unsigned,size_t,char **,size_t *,reader_rs_error *);
extern "C" reader_rs_status w3_encode_retained(reader_revisions *store,const reader_rs_envelope *env,
    const reader_rs_capture *capture,unsigned version,size_t part,char **wire,size_t *bytes,reader_rs_error *error) {
  return reader_rs_encode_retained_raw_v3(store,env,capture,version,part,wire,bytes,error);
}
