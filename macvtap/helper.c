#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/prctl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

#include <net/if.h>

#include <linux/sockios.h>

#include <linux/if.h>
#include <linux/if_tun.h>

#include <errno.h>

#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>

// gcc -Wall -O2 -o helper helper.c
// ip link add vmvlan${VMID} link ${LINK} type macvlan mode passthru
// qemu -netdev tap,id=mactap0,br=vmlan700,helper=/opt/vfmgr/macvtap/helper -device virtio-net-pci,netdev=mactap0,mac=##:##:##:##:##:##

static void usage(void)
{
    fprintf(stderr,
            "Usage: helper [--use-vnet] --br=TAPNAME --fd=unixfd\n");
}

static int send_fd(int c, int fd)
{
    char msgbuf[CMSG_SPACE(sizeof(fd))];
    struct msghdr msg = {
        .msg_control = msgbuf,
        .msg_controllen = sizeof(msgbuf),
    };
    struct cmsghdr *cmsg;
    struct iovec iov;
    char req[1] = { 0x00 };

    cmsg = CMSG_FIRSTHDR(&msg);
    cmsg->cmsg_level = SOL_SOCKET;
    cmsg->cmsg_type = SCM_RIGHTS;
    cmsg->cmsg_len = CMSG_LEN(sizeof(fd));
    msg.msg_controllen = cmsg->cmsg_len;

    iov.iov_base = req;
    iov.iov_len = sizeof(req);

    msg.msg_iov = &iov;
    msg.msg_iovlen = 1;
    memcpy(CMSG_DATA(cmsg), &fd, sizeof(fd));

    return sendmsg(c, &msg, 0);
}

int main(int argc, char **argv)
{
    char tmp[4096];
    char tmp2[128];
    struct ifreq ifr;
    int ret = 0;
    int use_vnet = 0;
    int unixfd = -1;
    FILE* fd = NULL;
    int tapfd = -1;
    const char *bridge = NULL;
    int index = 0;

    /* parse arguments */
    for (index = 1; index < argc; index++) {
        if (strcmp(argv[index], "--use-vnet") == 0) {
            use_vnet = 1;
        } else if (strncmp(argv[index], "--br=", 5) == 0) {
            bridge = &argv[index][5];
        } else if (strncmp(argv[index], "--fd=", 5) == 0) {
            unixfd = atoi(&argv[index][5]);
        } else {
            usage();
            return EXIT_FAILURE;
        }
    }

    if (bridge == NULL || unixfd == -1) {
        usage();
        return EXIT_FAILURE;
    }
    if (strlen(bridge) >= IFNAMSIZ) {
        fprintf(stderr, "name `%s' too long: %zu\n", bridge, strlen(bridge));
        return EXIT_FAILURE;
    }

    snprintf(tmp, 4095, "/sys/class/net/%s/ifindex", bridge);
    fd = fopen(tmp, "r");
    if (!fd) {
        fprintf(stderr, "failed to open ifindex: %s\n", strerror(errno));
        return EXIT_FAILURE;
    }
    fgets(tmp2, 127, fd);

    for (index = 0; index < 128; index++) {
        const char c = tmp2[index];
        if (c == 0 || c == 13 || c == 10) {
            tmp2[index] = 0;
            break;
        }
    }

    snprintf(tmp, 4095, "/dev/tap%s", tmp2);
    tapfd = open(tmp, O_RDWR);

    /* write fd to the domain socket */
    if (send_fd(unixfd, tapfd) == -1) {
        fprintf(stderr, "failed to write fd to unix socket: %s\n",
                strerror(errno));
        ret = EXIT_FAILURE;
        goto cleanup;
    }

cleanup:
    if (fd) {
        fclose(fd);
    }
    return ret;
}
