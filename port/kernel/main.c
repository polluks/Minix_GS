/* Minix GS M1 kernel entry (called from startup.s via jsl >_kmain).
 *
 * Sets up the console and timer, builds the three kernel tasks, readies
 * them, and falls into the scheduler's first restart().  The first RTI pops
 * P=0 (I=0) so interrupts come up enabled in the first task -- kmain itself
 * never enables them.
 */
#include "console.h"
#include "int.h"
#include "proc.h"

void kmain(void)
{
    console_init();
    console_puts("Minix GS M1: scheduler bring-up\r\n");
    console_puts("tasks: clock, A, B -- round robin @ 6 ticks\r\n");
    timer_init();
    dbg_mark(1);                    /* after timer_init */

    proc_init();
    dbg_mark(2);                    /* after proc_init */
    create_task(proc_addr(CLOCK), CLOCK, (unsigned int)&clock_task, CLOCK_TOP);
    {   /* debug: does the CLOCK frame exist at bank0 $6FF2? copy to $0D00 */
        volatile unsigned char __far *q = (volatile unsigned char __far *)0x0006FF2UL;
        volatile unsigned char __far *d = (volatile unsigned char __far *)0x0000D00UL;
        int i;
        for (i = 0; i < 13; i++) d[i] = q[i];
    }
    {   /* debug: mulint16 self-check into $0D20 (expect m = 11*28 = 0x134) */
        int mi = 11;
        int m = mi * 28;
        volatile unsigned char __far *d = (volatile unsigned char __far *)0x0000D20UL;
        d[0] = (unsigned char)(m & 0xFF);
        d[1] = (unsigned char)(m >> 8);
        dbg_st_mark = 0x1111;        /* marker: self-test reached */
        dbg_st_r0 = mi;              /* what the caller thinks it passed */
        dbg_st_a = m;                /* what the caller received back */
    }
    while (dbg_go == 0) { }         /* STALL 1: probe reads the frame here */
    {   /* debug: dump proc[].p_sp/p_flags/p_pid (6 bytes each) to bank0 $0E00 */
        volatile unsigned char __far *d = (volatile unsigned char __far *)0x0000E00UL;
        int i;
        for (i = 0; i < 12; i++) {
            d[i * 6 + 0] = (unsigned char)(proc[i].p_sp & 0xFF);
            d[i * 6 + 1] = (unsigned char)(proc[i].p_sp >> 8);
            d[i * 6 + 2] = (unsigned char)(proc[i].p_flags & 0xFF);
            d[i * 6 + 3] = (unsigned char)(proc[i].p_flags >> 8);
            d[i * 6 + 4] = (unsigned char)(proc[i].p_pid & 0xFF);
            d[i * 6 + 5] = (unsigned char)(proc[i].p_pid >> 8);
        }
    }
    dbg_mark(3);
    create_task(proc_addr(TASK_A), TASK_A, (unsigned int)&task_a, TASK_A_TOP);
    dbg_mark(4);
    create_task(proc_addr(TASK_B), TASK_B, (unsigned int)&task_b, TASK_B_TOP);
    dbg_mark(5);

    ready(proc_addr(CLOCK));
    ready(proc_addr(TASK_A));
    ready(proc_addr(TASK_B));
    dbg_mark(6);                    /* after ready x3 */

    pick_proc();
    dbg_mark(7);                    /* after pick_proc */
    restart();                      /* never returns */
    dbg_mark(8);
}
