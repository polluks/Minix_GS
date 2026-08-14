/* Minix GS demo kernel tasks: busy loops that count and print occasionally.
 * They never block; the VBL interrupt preempts them and round-robins the
 * task queue (see proc.c sched()).  The counters are read by the gs2*
 * debugger probes to prove context switching works.
 */
#include "proc.h"
#include "console.h"

volatile int task_a_count, task_b_count;

void task_a(void)
{
    for (;;) {
        task_a_count++;
        if ((task_a_count & 0x3FFF) == 0)
            console_putchar('A');
    }
}

void task_b(void)
{
    for (;;) {
        task_b_count++;
        if ((task_b_count & 0x3FFF) == 0)
            console_putchar('B');
    }
}
