import os
import sys
import itertools
import time
import traceback
import signal
from subprocess import Popen

def pty_fork():
    """Fork, connecting the child's controlling terminal to a psuedo-terminal master.
    
    The child's stdin, stdout, and stderr file descriptors are overwritten so that
    they read & write to the slave part. 
    
    This is an implementation similar to forkpty()
    See also:
    https://github.com/coreutils/gnulib/blob/master/lib/forkpty.c

    Returns:
        Tuple[int,int]: The pid is the result from os.fork(), 
        and the master_fd is the master part of the file descriptor
        returned from os.openpty()
    """

    # Open the pty
    # see also: https://www.unix.com/man-page/linux/3/openpty/
    # this is akin to opening /dev/ptmx to get the master part
    # and then calling ptsname(3) to get the slave part name, and then opening that
    master_fd, slave_fd = os.openpty()
    if (pid := os.fork()) == 0:
        # This is the login_tty part
        # see: https://github.com/coreutils/gnulib/blob/master/lib/login_tty.c
        os.setsid()  # Establish a new session.
        os.close(master_fd)  # child does not need this

        # connect the child's stdin/stdout/stderr to the pts
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)

        # Explicitly open the tty to make it become a controlling tty. This works on Linux / BSD / OSF/1
        # alternatively, on some systems (linux), we can instead use ioctl (slave_fd, TIOCSCTTY, NULL)
        os.close(os.open(os.ttyname(slave_fd), os.O_RDWR))
        if slave_fd > 2:
            os.close (slave_fd)
    else:
        os.close(slave_fd)

    # return the fork's pid and master part of the terminal
    return pid, master_fd

if __name__ == '__main__':
    
    def hangup(signum, frame):
        print(f'pid {os.getpid()} got the hangup signal!', file=write_pipe)
        raise Exception('Hangup signal')

    ppid = os.getpid()
    r,w = os.pipe()
    read_pipe = os.fdopen(r, 'r', 1)
    write_pipe = os.fdopen(w, 'w', 1)

    pid, master_fd = pty_fork()

    if pid == 0:  # child
        try:
            signal.signal(signal.SIGHUP, hangup)
            read_pipe.close()
            for n in itertools.count():
                print (f'child - {n}', file=write_pipe)
                time.sleep(1)
                if n == 3:  # the controlling process of the pts and all descendents of it shall recieve sighup
                    if child_pid := os.fork():
                        print(f'forked child returns with status of {os.wait()}', file=write_pipe)
                    else:
                        Popen(['sleep', '100'])
                        sys.exit(0)
        except:
            traceback.print_exc(file=write_pipe)
    else:  # parent
        write_pipe.close()
        print ('parent')
        for i in range(30):
            buff = read_pipe.readline()
            print (f'child written: {buff}')
        print (f'closing pseudo terminal master fd')
        os.close(master_fd)  # the ctty slave part (and descendants of ctty process) shall recieve SIGHUP
        while buff := read_pipe.readline():
            print (f'child written: {buff}')
        for i in range(5, 0, -1):
            print (f'waiting to terminate master...{i}')
            time.sleep(1)
