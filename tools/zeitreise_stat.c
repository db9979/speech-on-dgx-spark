/* File times follow the clock that libfaketime moved (tools/zeitreise.py): libfaketime 0.9.10 does not catch
   stat64 & co, which Python 3.11 on glibc >= 2.33 calls, so a file written just now looked months old to the tests.
   ZEITREISE_STAT = seconds the clock is moved ahead. Read times get them added, set times (utime) taken off. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static long off(void) { static long o = -1; if (o < 0) { const char *s = getenv("ZEITREISE_STAT"); o = s ? atol(s) : 0; } return o; }
static void fix(struct stat64 *b) { long o = off(); b->st_atim.tv_sec += o; b->st_mtim.tv_sec += o; b->st_ctim.tv_sec += o; }

int stat64(const char *p, struct stat64 *b) { static int (*r)(const char *, struct stat64 *); if (!r) r = dlsym(RTLD_NEXT, "stat64"); int x = r(p, b); if (!x) fix(b); return x; }
int lstat64(const char *p, struct stat64 *b) { static int (*r)(const char *, struct stat64 *); if (!r) r = dlsym(RTLD_NEXT, "lstat64"); int x = r(p, b); if (!x) fix(b); return x; }
int fstat64(int fd, struct stat64 *b) { static int (*r)(int, struct stat64 *); if (!r) r = dlsym(RTLD_NEXT, "fstat64"); int x = r(fd, b); if (!x) fix(b); return x; }
int fstatat64(int d, const char *p, struct stat64 *b, int f) { static int (*r)(int, const char *, struct stat64 *, int); if (!r) r = dlsym(RTLD_NEXT, "fstatat64"); int x = r(d, p, b, f); if (!x) fix(b); return x; }

static void real(const struct timespec *in, struct timespec *out) {
    struct timespec now; syscall(SYS_clock_gettime, CLOCK_REALTIME, &now);
    for (int i = 0; i < 2; i++) {
        if (!in || in[i].tv_nsec == UTIME_NOW) out[i] = now;
        else if (in[i].tv_nsec == UTIME_OMIT) out[i] = in[i];
        else { out[i] = in[i]; out[i].tv_sec -= off(); }
    }
}
int utimensat(int d, const char *p, const struct timespec t[2], int f) { struct timespec o[2]; real(t, o); return syscall(SYS_utimensat, d, p, o, f); }
int futimens(int fd, const struct timespec t[2]) { struct timespec o[2]; real(t, o); return syscall(SYS_utimensat, fd, NULL, o, 0); }
