#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <stdint.h>
static void handler(int signal) { (void)signal; }
struct kernel_action { uint32_t handler, flags, restorer, mask[2]; } __attribute__((packed));
int main(void) {
    struct sigaction action = {0}, old = {0};
    action.sa_handler = handler;
    sigemptyset(&action.sa_mask);
    action.sa_flags = SA_RESTART;
    printf("C signal ABI: size=%zu action=%p old=%p\n", sizeof(action), (void *)&action, (void *)&old);
    int r = sigaction(SIGCHLD, NULL, &old);
    printf("query: %d errno=%d %s\n", r, errno, strerror(errno));
    r = sigaction(SIGCHLD, &action, &old);
    printf("install: %d errno=%d %s\n", r, errno, strerror(errno));
    struct kernel_action raw = {0};
    r = syscall(SYS_rt_sigaction, SIGCHLD, NULL, &raw, 8);
    printf("raw query: %d errno=%d %s handler=%x flags=%x\n", r, errno, strerror(errno), raw.handler, raw.flags);
    return 0;
}
