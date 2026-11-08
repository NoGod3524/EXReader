#include <stdio.h>

int main(void) {
    int x = 0x7fffffff;
    x += 1;
    printf("%d\n", x);
    return 0;
}
