#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>
int main(void) {
    errno = 0;
    int rc = prctl(PR_SET_PDEATHSIG, SIGTERM);
    printf("PR_SET_PDEATHSIG: %d errno=%d (%s)\n", rc, errno, strerror(errno));
    pid_t child = fork();
    if (child < 0) { perror("fork"); return 1; }
    if (child == 0) { sleep(2); _exit(0); }
    struct utsname uts;
    int ish = uname(&uts) == 0 && strlen(uts.release) >= 4 &&
        strcmp(uts.release + strlen(uts.release) - 4, "-ish") == 0;
    if (ish) {
        printf("pidfd_open: skipped on iSH (missing syscall raises SIGSYS); use SIGCHLD\n");
    } else {
    errno = 0;
    int fd = syscall(SYS_pidfd_open, child, 0);
    printf("pidfd_open: %d errno=%d (%s)\n", fd, errno, strerror(errno));
    if (fd >= 0) {
        siginfo_t info = {0}; errno = 0;
        rc = waitid(P_PIDFD, (id_t)fd, &info, WEXITED | WNOHANG | WNOWAIT);
        printf("waitid(P_PIDFD): %d errno=%d (%s)\n", rc, errno, strerror(errno));
        close(fd);
    }
    }
    int status;
    if (waitpid(child, &status, 0) < 0) { perror("waitpid"); return 1; }
    printf("waitpid: exit=%d\n", WIFEXITED(status) ? WEXITSTATUS(status) : -1);
    return 0;
}
