/* Minix-GS M1 kernel entry (called from startup.s via jsl >_kmain). */
#include "console.h"

void kmain(void)
{
    console_init();
    console_puts("Minix GS M1: 65816 native, bank 0 I/O reachable\r\n");
    console_puts("kernel in bank $02, 80-col text via far pointers\r\n");
    for (;;)
        ;
}
