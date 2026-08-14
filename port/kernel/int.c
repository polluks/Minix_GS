/* Minix GS MegaII/VBL interrupt timer and native-mode vector installation.
 *
 * The periodic interrupt source is the VBL (~60 Hz) from the video system,
 * delivered through the MegaII interrupt controller:
 *   $C041 INTEN   - bit 3 = VBL enable
 *   $C047 CLRVBLINT - any write clears the VBL interrupt (handler must do it)
 * Language card (bank 0 $C080-$C08F): writing $C080 selects bank 2, enables
 *   RAM reads (so $D000-$FFFF READS come from LC RAM, not ROM) and disables
 *   further LC writes.  This is what makes the native IRQ/BRK vector fetch
 *   at $FFEE/$FFE6 return our trampoline addresses instead of the ROM vector.
 * Native vectors (LC RAM in bank 0): $FFEE IRQ, $FFE6 BRK.
 * The 65816 fetches the vector from bank 0 and runs the handler with PB=0,
 * so the handlers live in bank 2 but are reached via 4-byte "jml" trampolines
 * installed in bank-0 RAM ($0900/$0908).  The VBL event itself is dispatched
 * by irq_dispatch() in proc.c (scheduler) via context.s save/restart.
 */
#include "int.h"

volatile unsigned short jiffies;    /* 60 Hz clock ticks */

/* JML images (4 bytes each) for the bank-2 handlers, defined in intentry.s. */
extern unsigned char tramp_irq[4];
extern unsigned char tramp_brk[4];

void timer_init(void)
{
    unsigned char i;
    volatile unsigned char __far *p;

    p = (volatile unsigned char __far *)0x000900UL;   /* copy JML to bank 0 */
    for (i = 0; i < 4; i++)
        p[i] = ((volatile unsigned char __far *)&tramp_irq)[i];

    p = (volatile unsigned char __far *)0x000908UL;
    for (i = 0; i < 4; i++)
        p[i] = ((volatile unsigned char __far *)&tramp_brk)[i];

    *(volatile unsigned short __far *)0x00FFEEUL = 0x0900;   /* native IRQ */
    *(volatile unsigned short __far *)0x00FFE6UL = 0x0908;   /* native BRK */
    *(volatile unsigned char __far *)0x00C080UL = 0;  /* LC: bank2, RAMRD on */
    *(volatile unsigned char __far *)0x00C041UL = 0x08; /* INTEN: VBL */
}
