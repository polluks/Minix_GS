/* Minix GS process table and message passing (port of MINIX 1.2 proc.c).
 *
 * Message passing model is MINIX 1.x: copy-data-then-send.  All kernel
 * tasks share bank $02 (code/data) and keep their hardware stacks in bank 0
 * (the 65816 stack is always bank 0), so per-task message buffers are
 * static near pointers in bank $02 -- never on a task stack.
 *
 * Context switch rule (see AGENTS.md): proc_ptr MUST point at the running
 * process whenever the CPU is in process code.  pick_proc()/mini_rec() may
 * only run in interrupt/trap context (between save() and restart() in
 * context.s).  Tasks block by trapping (brk) into brk_dispatch(), exactly
 * like MINIX's int SYSVEC -> sys_call() path.
 */

#ifndef MINIX_GS_PROC_H
#define MINIX_GS_PROC_H

/* System call function codes. */
#define SEND         1
#define RECEIVE      2
#define BOTH         3
#define ANY          (NR_PROCS+100)

/* Task numbers (negative = kernel task). */
#define HARDWARE     -1
#define TASK_B       -2
#define TASK_A       -3
#define CLOCK        -4
#define IDLE         -999

#define NONE          0    /* no message source / not blocked */

#define NR_TASKS     4
#define NR_PROCS     8
#define NQ           3
#define TASK_Q       0
#define SERVER_Q     1
#define USER_Q       2
#define SCHED_RATE   6    /* rotate TASK_Q every 6 ticks (0.1 s @60 Hz) */

/* Return codes (subset of MINIX errno). */
#define OK           0
#define E_OVERRUN    4
#define E_BAD_DEST   5
#define E_BAD_SRC    5
#define E_NO_PERM    9

/* Message (mirrors MINIX h/type.h; 8 words = 16 bytes). */
typedef struct message {
    int m_source;          /* sender's process number */
    int m_type;            /* request/function code */
    int m1_i1, m1_i2, m1_i3;
    int m1_p1, m1_p2;      /* near pointers (same bank) */
} message;

/* p_flags bits.  A process is runnable iff p_flags == 0. */
#define P_SLOT_FREE  001
#define SENDING      004
#define RECEIVING    010

/* WARNING: context.s references p_sp at offset 0.  Keep it first. */
struct proc {
    int            p_sp;        /* 0  saved hardware stack ptr (bank 0) */
    int            p_flags;     /* 2  P_SLOT_FREE, SENDING, RECEIVING */
    int            p_pid;       /* 4  process id */
    struct proc   *p_nextready; /* 6  next in ready queue */
    struct proc   *p_callerq;   /* 8  head of procs wanting to send to me */
    struct proc   *p_sendlink;  /* 10 next proc wanting to send */
    message       *p_messbuf;   /* 12 where next message goes */
    int            p_getfrom;   /* 14 receive source filter (or ANY) */
    int            p_user_time; /* 16 accounting */
    int            p_sys_time;  /* 18 accounting */
};

#define proc_addr(n) (&proc[NR_TASKS + (n)])
#define NIL_PROC ((struct proc *)0)
#define NIL_MESS ((message *)0)

/* Bank-0 task stack regions (hardware stack must be bank 0). */
#define TASK_A_TOP   0xA3FE
#define TASK_B_TOP   0xA7FE
#define CLOCK_TOP    0xABFE
#define K_STACK_TOP  0xBFFE

/* Globals referenced by context.s (non-static). */
extern struct proc proc[NR_TASKS + NR_PROCS];
extern struct proc *proc_ptr;     /* &proc[cur_proc] */
extern struct proc *rdy_head[NQ], *rdy_tail[NQ];
extern int cur_proc, prev_proc;

/* Task entry points (tasks.c, clock.c). */
extern void task_a(void);
extern void task_b(void);
extern void clock_task(void);

/* Scheduler / IPC (proc.c). */
void proc_init(void);
void pick_proc(void);
void ready(struct proc *rp);
void unready(struct proc *rp);
void sched(void);
int  mini_send(int caller, int dest, message *m_ptr);
int  mini_rec(int caller, int src, message *m_ptr);
void create_task(struct proc *rp, int tasknr, unsigned int entry, int stack_top);

/* Trap-context dispatchers called from context.s. */
void irq_dispatch(void);
void brk_dispatch(void);

/* Locking (only valid in irq/trap context; see context.s). */
void lock(void);
void restore(void);

/* restart() switches to proc_ptr (context.s). */
void restart(void);

#endif
