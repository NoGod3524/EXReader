#include <exr/base.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    const char *version = exr_version();
    const unsigned int abi = (unsigned int)exr_abi_version();
    printf("{\"sdk_version\":\"%s\",\"abi\":%u}\n", version, abi);
    return strcmp(version, "3.42.0") || abi != 1;
}
