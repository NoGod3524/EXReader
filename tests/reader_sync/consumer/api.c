/* SPDX-License-Identifier: MIT */
#include <reader_sync.h>
int main(void){reader_sync *sync=0;reader_sync_error error;
  return reader_sync_create(0,&sync,&error)==READER_SYNC_ARGUMENT&&sync==0?0:1;
}
