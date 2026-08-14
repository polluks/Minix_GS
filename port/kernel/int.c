/* IIgs MegaII/VBL interrupt timer and native-mode vector installation.
 *
 * The IIgs has no 65C22 VIA timer in the GS/OS time-slice sense; the
 * periodic interrupt source is the VBL (vertical blanking, ~60 Hz) from the
 * video system, delivered through the MegaII interrupt controller:
 *   $C041 INTEN   - bit 3 = VBL enable
 *   $C047 CLRVBLINT - any write clears the VBL interrupt (handler must do it)
 * Language card (bank 0 $C080-$C08F): writing $C080 selects bank 2, enables
 *   RAM reads (so $D000-$FFFF READS come from LC RAM, not ROM) and disables
 *   further LC writes -- GSSquared has no dedicated $FFD0-$FFFF vector
 *   shadow, so this is what makes the native IRQ/BRK vector fetch at
 *   $FFEE/$FFE6 return our trampoline addresses instead of the ROM vector.
 * Native vectors (LC RAM in bank 0): $FFEE IRQ, $FFE6 BRK.
 * The 65816 fetches the vector from bank 0 and runs the handler with PB=0,
 * so int.s lives in bank 2 but is reached via 4-byte "jml >int_irq" /
 * "jml >int_brk" trampolines installed in bank-0 RAM ($0900/$0908).
 */
#include "int.h"

typedef volatile unsigned char vu8;
typedef volatile unsigned short vu16;

volatile unsigned short jiffies;   /* 60 Hz clock ticks */

/* JML images (4 bytes each) for the bank-2 handlers, defined in intentry.s. */
extern unsigned char tramp_irq[4];
extern unsigned char tramp_brk[4];

void irq_handler(void)
{
    *(vu8 __far *)0x00C047UL = 0;   /* CLRVBLINT: clear the VBL interrupt */
    jiffies++;
}

void brk_handler(void)
{
    /* native BRK (vector $FFE6) -- future syscall entry, no-op for now */
}

void timer_init(void)
{
    unsigned char i;
    vu8 __far *p;

    p = (vu8 __far *)0x000900UL;          /* copy JML >int_irq to bank 0 */
    for (i = 0; i < 4; i++)
        p[i] = ((vu8 __far *)&tramp_irq)[i];

    p = (vu8 __far *)0x000908UL;          /* copy JML >int_brk to bank 0 */
    for (i = 0; i < 4; i++)
        p[i] = ((vu8 __far *)&tramp_brk)[i];

    *(vu16 __far *)0x00FFEEUL = 0x0900;   /* native IRQ vector */
    *(vu16 __far *)0x00FFE6UL = 0x0908;   /* native BRK vector */
    *(vu8 __far *)0x00C080UL = 0;         /* LC: bank 2, RAMRD on (vector reads) */
    *(vu8 __far *)0x00C041UL = 0x08;      /* INTEN: enable VBL */
}
