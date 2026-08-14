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

    proc_init();
    create_task(proc_addr(CLOCK), CLOCK, (unsigned int)&clock_task, CLOCK_TOP);
    create_task(proc_addr(TASK_A), TASK_A, (unsigned int)&task_a, TASK_A_TOP);
    create_task(proc_addr(TASK_B), TASK_B, (unsigned int)&task_b, TASK_B_TOP);

    ready(proc_addr(CLOCK));
    ready(proc_addr(TASK_A));
    ready(proc_addr(TASK_B));

    pick_proc();
    restart();                      /* never returns */
}
