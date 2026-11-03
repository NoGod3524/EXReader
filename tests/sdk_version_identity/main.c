#include <stdio.h>
#include <string.h>
#include <exr/base.h>

int main(void) {
    printf("header=%s\nruntime=%s\nabi=%u\n", EXR_SDK_VERSION, exr_version(), exr_abi_version());
    return strcmp(EXR_SDK_VERSION, exr_version()) || exr_abi_version() != EXR_ABI_VERSION;
}
