/* Minix GS kernel process and message handling (port of MINIX 1.2 proc.c).
 *
 * Entry points:
 *   irq_dispatch() -- called from context.s after the VBL save; sends the
 *       clock tick and re-picks a process.
 *   brk_dispatch()  -- native BRK trap; SEND/RECEIVE syscalls (MINIX's
 *       sys_call).  Runs in trap context (interrupts off, kernel stack).
 *   mini_send/mini_rec/ready/unready/pick_proc/sched -- as in MINIX.
 *
 * All of these run with interrupts disabled, between save() and restart()
 * in context.s, so proc_ptr changes are always followed by a switch before
 * any process code runs again.
 */
#include "proc.h"
#include "console.h"
#include "int.h"

typedef volatile unsigned char vu8;
typedef volatile unsigned short vu16;

static void cp_mess_from(int caller, message *src, message *dst);

struct proc proc[NR_TASKS + NR_PROCS];
struct proc *proc_ptr;                /* &proc[cur_proc] */
struct proc *rdy_head[NQ], *rdy_tail[NQ];
int cur_proc = IDLE, prev_proc = IDLE;

/* Initialize the whole proc table.  Slot n holds task/proc number n-NR_TASKS;
 * unused slots are marked free (HARDWARE's slot is only a proc_ptr fallback
 * for IDLE and never runs).  A pointer difference rp-proc would need a 28-byte
 * divide, so the task number is stored directly in p_pid instead. */
void proc_init(void)
{
    int i;

    for (i = 0; i < NR_TASKS + NR_PROCS; i++) {
        proc[i].p_flags = P_SLOT_FREE;
        proc[i].p_pid = i - NR_TASKS;
        proc[i].p_nextready = NIL_PROC;
        proc[i].p_callerq = NIL_PROC;
        proc[i].p_sendlink = NIL_PROC;
    }
    for (i = 0; i < NQ; i++)
        rdy_head[i] = rdy_tail[i] = NIL_PROC;
}

/* Scratch for the brk syscall (read by asm_recv in context.s). */
volatile int sys_src, sys_mptr;

/* Tick message sent by the VBL interrupt to the clock task. */
static message tick_mess;
static int sched_ticks = SCHED_RATE;

/*===========================================================================*
 *				irq_dispatch				     *
 *===========================================================================*/
void irq_dispatch(void)
{
    *(vu8 __far *)0x00C047UL = 0;   /* CLRVBLINT: clear the VBL interrupt */
    dbg_mark(40);                   /* debug: irq_dispatch entry */

    tick_mess.m_source = HARDWARE;
    tick_mess.m_type = 2;           /* CLOCK_TICK */
    mini_send(HARDWARE, CLOCK, &tick_mess);

    /* Round-robin the kernel tasks every SCHED_RATE ticks. */
    if (--sched_ticks == 0) {
        sched_ticks = SCHED_RATE;
        sched();
    } else {
        pick_proc();
    }
}

/*===========================================================================*
 *				brk_dispatch				     *
 *===========================================================================*/
void brk_dispatch(void)
{
    struct proc *rp = proc_ptr;
    vu16 __far *fp = (vu16 __far *)(unsigned long)rp->p_sp;
    int func = fp[0];       /* A: SEND or RECEIVE */
    int src = fp[1];        /* X: src/dest */
    int mptr = fp[2];       /* Y: message buffer (near ptr) */
    int n = 0;

    dbg_mark(50);           /* debug: brk_dispatch entry */
    switch (func) {
        case SEND:
            n = mini_send(rp->p_pid, src, (message *)mptr);
            break;
        case RECEIVE:
            n = mini_rec(rp->p_pid, src, (message *)mptr);
            break;
    }
    fp[0] = n;                      /* return value in saved A */
}

/*===========================================================================*
 *				mini_send				     *
 *===========================================================================*/
int mini_send(int caller, int dest, message *m_ptr)
{
    struct proc *caller_ptr, *dest_ptr, *next_ptr;

    caller_ptr = proc_addr(caller);
    dest_ptr = proc_addr(dest);
    if (dest_ptr->p_flags & P_SLOT_FREE) return E_BAD_DEST;

    if ((dest_ptr->p_flags & RECEIVING) &&
        (dest_ptr->p_getfrom == ANY || dest_ptr->p_getfrom == caller)) {
        /* Destination is blocked waiting for this message: deliver now. */
        cp_mess_from(caller, m_ptr, dest_ptr->p_messbuf);
        dest_ptr->p_flags &= ~RECEIVING;
        if (dest_ptr->p_flags == 0) ready(dest_ptr);
    } else {
        /* Destination not waiting.  Block and queue the caller. */
        if (caller == HARDWARE) return E_OVERRUN;   /* tick lost */
        caller_ptr->p_messbuf = m_ptr;
        caller_ptr->p_flags |= SENDING;
        unready(caller_ptr);
        if ((next_ptr = dest_ptr->p_callerq) == NIL_PROC) {
            dest_ptr->p_callerq = caller_ptr;
        } else {
            while (next_ptr->p_sendlink != NIL_PROC)
                next_ptr = next_ptr->p_sendlink;
            next_ptr->p_sendlink = caller_ptr;
        }
        caller_ptr->p_sendlink = NIL_PROC;
    }
    return OK;
}

/*===========================================================================*
 *				mini_rec				     *
 *===========================================================================*/
int mini_rec(int caller, int src, message *m_ptr)
{
    struct proc *caller_ptr, *sender_ptr, *prev_ptr;
    int sender;

    caller_ptr = proc_addr(caller);

    sender_ptr = caller_ptr->p_callerq;
    prev_ptr = NIL_PROC;
    while (sender_ptr != NIL_PROC) {
        sender = sender_ptr->p_pid;
        if (src == ANY || src == sender) {
            /* Acceptable message found.  Copy it and deblock the sender. */
            cp_mess_from(sender, sender_ptr->p_messbuf, m_ptr);
            sender_ptr->p_flags &= ~SENDING;
            if (sender_ptr->p_flags == 0) ready(sender_ptr);
            if (sender_ptr == caller_ptr->p_callerq)
                caller_ptr->p_callerq = sender_ptr->p_sendlink;
            else
                prev_ptr->p_sendlink = sender_ptr->p_sendlink;
            return OK;
        }
        prev_ptr = sender_ptr;
        sender_ptr = sender_ptr->p_sendlink;
    }

    /* No suitable message: block the caller. */
    caller_ptr->p_getfrom = src;
    caller_ptr->p_messbuf = m_ptr;
    caller_ptr->p_flags |= RECEIVING;
    unready(caller_ptr);
    return OK;
}

/*===========================================================================*
 *				pick_proc				     *
 *===========================================================================*/
void pick_proc(void)
{
    int q;

    if (rdy_head[TASK_Q] != NIL_PROC) q = TASK_Q;
    else if (rdy_head[SERVER_Q] != NIL_PROC) q = SERVER_Q;
    else q = USER_Q;

    prev_proc = cur_proc;
    if (rdy_head[q] != NIL_PROC) {
        cur_proc = rdy_head[q]->p_pid;
        proc_ptr = rdy_head[q];
    } else {
        cur_proc = IDLE;
        proc_ptr = proc_addr(HARDWARE);
    }
}

/*===========================================================================*
 *				ready					     *
 *===========================================================================*/
void ready(struct proc *rp)
{
    int r, q;

    lock();
    r = rp->p_pid;
    q = (r < 0 ? TASK_Q : r < NR_PROCS ? SERVER_Q : USER_Q);

    if (rdy_head[q] == NIL_PROC)
        rdy_head[q] = rp;
    else
        rdy_tail[q]->p_nextready = rp;
    rdy_tail[q] = rp;
    rp->p_nextready = NIL_PROC;
    restore();
}

/*===========================================================================*
 *				unready					     *
 *===========================================================================*/
void unready(struct proc *rp)
{
    struct proc *xp;
    int r, q;

    lock();
    r = rp->p_pid;
    q = (r < 0 ? TASK_Q : r < NR_PROCS ? SERVER_Q : USER_Q);
    if ((xp = rdy_head[q]) == NIL_PROC) { restore(); return; }
    if (xp == rp) {
        rdy_head[q] = xp->p_nextready;
        pick_proc();
    } else {
        while (xp->p_nextready != rp)
            if ((xp = xp->p_nextready) == NIL_PROC) { restore(); return; }
        xp->p_nextready = xp->p_nextready->p_nextready;
        while (xp->p_nextready != NIL_PROC) xp = xp->p_nextready;
        rdy_tail[q] = xp;
    }
    restore();
}

/*===========================================================================*
 *				sched					     *
 *===========================================================================*/
void sched(void)
{
    struct proc *h;

    lock();
    h = rdy_head[TASK_Q];
    if (h != NIL_PROC && h->p_nextready != NIL_PROC) {
        /* Move the head of TASK_Q to the tail (round robin). */
        rdy_tail[TASK_Q]->p_nextready = h;
        rdy_head[TASK_Q] = h->p_nextready;
        rdy_tail[TASK_Q] = h;
        h->p_nextready = NIL_PROC;
    }
    pick_proc();
    restore();
}

/*===========================================================================*
 *				cp_mess_from				     *
 *===========================================================================*/
static void cp_mess_from(int caller, message *src, message *dst)
{
    int *s = (int *)src;
    int *d = (int *)dst;
    int i;

    d[0] = caller;
    for (i = 1; i < 8; i++)
        d[i] = s[i];
}

/*===========================================================================*
 *				create_task				     *
 *===========================================================================*/
void create_task(struct proc *rp, int tasknr, unsigned int entry, int stack_top)
{
    vu8 __far *f = (vu8 __far *)(unsigned long)(stack_top - 13);
    int i;

    /* Build the 13-byte initial frame at stack_top-13 (bank 0):
     *   [A(2)][X(2)][Y(2)][DP(2)][DB(1)][P(1)][PC(2)][PB(1)]
     * P=0: M=0 X=0 I=0 (native 16-bit, interrupts enabled on RTI).
     */
    for (i = 0; i < 8; i++)
        f[i] = 0;
    f[8] = 2;                       /* DB = $02 */
    f[9] = 0x00;                    /* P */
    f[10] = entry & 0xFF;
    f[11] = (entry >> 8) & 0xFF;
    f[12] = 2;                      /* PB = $02 */

    rp->p_sp = stack_top - 13;
    rp->p_flags = 0;                /* clear P_SLOT_FREE */
    rp->p_pid = tasknr;
    rp->p_nextready = NIL_PROC;
    rp->p_callerq = NIL_PROC;
    rp->p_sendlink = NIL_PROC;
    rp->p_getfrom = NONE;
    rp->p_messbuf = NIL_MESS;
    rp->p_user_time = 0;
    rp->p_sys_time = 0;
}
