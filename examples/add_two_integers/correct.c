#include <stdio.h>

static long long add_integers(long long left, long long right) {
    return left + right;
}

int main(void) {
    long long left = 0;
    long long right = 0;
    if (scanf("%lld %lld", &left, &right) != 2) {
        return 1;
    }
    printf("%lld\n", add_integers(left, right));
    return 0;
}
