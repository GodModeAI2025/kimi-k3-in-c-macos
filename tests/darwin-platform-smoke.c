/* Compile-only smoke test for Darwin-specific source fragments used by the port.
 *
 * WHAT THIS DOES NOT PROVE. There is no macOS SDK on the machine that runs the package
 * validation, so the Mach types and constants below are LOCAL STAND-INS, not Apple's.
 * The real vm_statistics64_data_t has around twenty natural_t (32-bit) counters and a
 * real HOST_VM_INFO64_COUNT near 38, not the three-field uint64_t struct declared here.
 * So this file checks that the code SHAPE compiles -- the fcntl calls, the getrusage
 * unit handling, the argument types and the in/out `count` protocol -- and nothing about
 * Apple's headers. Only the macOS CI jobs compile against the real SDK.
 *
 * The engine widens each counter to uint64_t before summing precisely because the real
 * fields are 32-bit; keep that cast if this stand-in is ever updated. */
/* This prologue must stay identical to the one the ported sources use. It did not once:
 * the test declared _DARWIN_C_SOURCE while src/cli/k3_run.c still declared only
 * _POSIX_C_SOURCE, so the test compiled a struct rusage that had ru_maxrss while the
 * real file compiled one that did not. A green suite hid a hard macOS build failure. */
#define _DARWIN_C_SOURCE 1
#include <fcntl.h>
#include <stdint.h>
#include <stddef.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef F_NOCACHE
#define F_NOCACHE 48
#endif
#ifndef F_RDADVISE
#define F_RDADVISE 44
struct radvisory { off_t ra_offset; int ra_count; };
#endif

typedef unsigned int mach_port_t;
typedef unsigned long vm_size_t;
typedef int kern_return_t;
typedef unsigned int mach_msg_type_number_t;
typedef int *host_info64_t;
typedef struct {
    uint64_t free_count;
    uint64_t inactive_count;
    uint64_t speculative_count;
} vm_statistics64_data_t;

#define KERN_SUCCESS 0
#define HOST_VM_INFO64 4
#define HOST_VM_INFO64_COUNT 3

extern mach_port_t mach_host_self(void);
extern mach_port_t mach_task_self(void);
extern kern_return_t host_page_size(mach_port_t, vm_size_t *);
extern kern_return_t host_statistics64(mach_port_t, int, host_info64_t,
                                       mach_msg_type_number_t *);
extern kern_return_t mach_port_deallocate(mach_port_t, mach_port_t);

static int cache_bypassed_open(const char *path)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    if (fcntl(fd, F_NOCACHE, 1) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static double peak_rss_bytes(void)
{
    struct rusage ru;
    if (getrusage(RUSAGE_SELF, &ru) != 0) return 0.0;
    return (double)ru.ru_maxrss;
}

static double reclaimable_memory_bytes(void)
{
    mach_port_t host = mach_host_self();
    vm_size_t page_size = 0;
    vm_statistics64_data_t vm;
    mach_msg_type_number_t count = HOST_VM_INFO64_COUNT;
    if (host_page_size(host, &page_size) != KERN_SUCCESS ||
        host_statistics64(host, HOST_VM_INFO64, (host_info64_t)&vm, &count) != KERN_SUCCESS) {
        mach_port_deallocate(mach_task_self(), host);
        return 0.0;
    }
    const uint64_t pages = vm.free_count + vm.inactive_count + vm.speculative_count;
    mach_port_deallocate(mach_task_self(), host);
    return (double)pages * (double)page_size;
}

static int read_advice(int fd, off_t offset, int64_t bytes)
{
    struct radvisory ra;
    ra.ra_offset = offset;
    ra.ra_count = bytes > 0x7fffffffLL ? 0x7fffffff : (int)bytes;
    return fcntl(fd, F_RDADVISE, &ra);
}

int darwin_platform_smoke(const char *path, int fd)
{
    return cache_bypassed_open(path) + (int)peak_rss_bytes() +
           (int)reclaimable_memory_bytes() + read_advice(fd, 0, 4096);
}
