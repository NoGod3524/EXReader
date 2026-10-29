/* SPDX-License-Identifier: MIT */
#include "reader_selector_bytes_v1.h"
#include "reader_selector_bytes_detail.h"
#include <cstring>
#include <limits>

namespace {
bool encoded_length(size_t count,size_t &length) {
  const size_t maximum=std::numeric_limits<size_t>::max();
  if(count>maximum-2)return false;
  const size_t groups=(count+2)/3;
  if(groups>maximum/4)return false;
  length=groups*4;return true;
}
reader_selector_status_v1 deliver(const std::string &value,void *output,
                                  size_t capacity,size_t *count) {
  if(!output){*count=value.size();return READER_SELECTOR_V1_OK;}
  if(capacity<value.size()){*count=value.size();return READER_SELECTOR_V1_BUFFER;}
  if(!value.empty())std::memcpy(output,value.data(),value.size());
  *count=value.size();return READER_SELECTOR_V1_OK;
}
}
extern "C" reader_selector_status_v1 reader_revision_selector_encode_v1(
    const void *bytes,size_t count,char *output,size_t capacity,size_t *output_count) {
  if(!output_count)return READER_SELECTOR_V1_ARGUMENT;
  *output_count=0;
  if((!bytes&&count)||(!output&&capacity))return READER_SELECTOR_V1_ARGUMENT;
  size_t required=0;
  if(!encoded_length(count,required))return READER_SELECTOR_V1_LIMIT;
  if(!output){*output_count=required;return READER_SELECTOR_V1_OK;}
  if(capacity<required){*output_count=required;return READER_SELECTOR_V1_BUFFER;}
  try {
    const std::string value=reader_selector_bytes_detail::encode(
        bytes?static_cast<const char *>(bytes):"",count);
    return deliver(value,output,capacity,output_count);
  } catch(...) {return READER_SELECTOR_V1_MEMORY;}
}
extern "C" reader_selector_status_v1 reader_revision_selector_decode_v1(
    const char *encoded,size_t encoded_count,size_t declared_bytes,
    size_t byte_limit,size_t scalar_limit,void *output,size_t capacity,size_t *output_count) {
  if(!output_count)return READER_SELECTOR_V1_ARGUMENT;
  *output_count=0;
  if((!encoded&&encoded_count)||(!output&&capacity))return READER_SELECTOR_V1_ARGUMENT;
  size_t required=0;
  if(declared_bytes>byte_limit||!encoded_length(declared_bytes,required))return READER_SELECTOR_V1_LIMIT;
  if(encoded_count!=required)return READER_SELECTOR_V1_FORMAT;
  try {
    std::string value;
    const auto status=reader_selector_bytes_detail::decode(
        std::string(encoded?encoded:"",encoded_count),declared_bytes,byte_limit,scalar_limit,value);
    if(status==reader_selector_bytes_detail::result::limit)return READER_SELECTOR_V1_LIMIT;
    if(status!=reader_selector_bytes_detail::result::ok)return READER_SELECTOR_V1_FORMAT;
    return deliver(value,output,capacity,output_count);
  } catch(...) {return READER_SELECTOR_V1_MEMORY;}
}
