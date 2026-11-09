#include <stdlib.h>

int main(int argc, char **argv) {
    volatile int index = argc + 3;
    int *values = (int *)malloc(4 * sizeof(int));
    (void)argv;
    if (!values) return 2;
    values[index] = 42;
    free(values);
    return 0;
}
