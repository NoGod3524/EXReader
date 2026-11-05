/* SPDX-License-Identifier: MIT */
/* Reads the installed SDK's public identity so the inventory can compare it with the
   installed header and the installed package configuration. Same contract as the
   shared distribution probe, without a package version pin. */
#include <stdio.h>

#include <exreader.h>

int main(void)
{
  printf("{\"version\":\"%s\",\"abi\":%u,\"core_version\":\"%s\"}\n",
         exr_version(), (unsigned)exr_abi_version(), EXR_CORE_VERSION);
  return 0;
}
