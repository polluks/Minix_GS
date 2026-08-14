/* Minix GS clock task (port of MINIX 1.2 clock.c).  Receives one CLOCK_TICK
 * per VBL wake-up from the interrupt handler, advances realtime, and will
 * later host alarms/watchdogs.  The round-robin scheduling itself happens in
 * the interrupt handler (proc.c sched()), not here, so this stays a plain
 * message consumer.
 */
#include "proc.h"

/* Syscall argument globals filled by recv() and consumed by asm_recv(). */
extern volatile int sys_src, sys_mptr;

static message mc;              /* message buffer (bank $02, near) */
volatile int clock_ticks;       /* ticks processed (probe-able) */

/* Traps to the kernel: X=src, Y=buf, A=RECEIVE.  Defined in context.s. */
extern int asm_recv(void);

int recv(int src, int mptr)
{
    sys_src = src;
    sys_mptr = mptr;
    return asm_recv();
}

void clock_task(void)
{
    for (;;) {
        recv(ANY, (int)&mc);            /* blocks until a tick arrives */
        if (mc.m_source == HARDWARE && mc.m_type == 2)  /* CLOCK_TICK */
            clock_ticks++;
    }
}
