/* Minix GS MegaII/VBL interrupt timer and native-mode vector installation.
 *
 * The periodic interrupt source is the VBL (~60 Hz) from the video system,
 * delivered through the MegaII interrupt controller:
 *   $C041 INTEN   - bit 3 = VBL enable
 *   $C047 CLRVBLINT - any write clears the VBL interrupt (handler must do it)
 *
 * Vector installation on stock GSSquared: the native IRQ/BRK vector fetch
 * (vp_read) returns ROM whenever IOLC shadowing is enabled, so the kernel
 * inhibits IOLC shadowing via the shadow register ($C035) bit 6 and points
 * $FFEE/$FFE6 at bank-0 RAM trampolines ($0900/$0908, jml images).  With
 * shadowing off, $C000-$CFFF in bank 0 reads as plain RAM in the emulator,
 * so all soft-switch I/O is done through the bank $E0 MegaII window (which
 * serves the same handlers); text-page writes still shadow to the VGC via
 * the independent TEXT1 shadow bit.  See AGENTS.md "Interrupt bring-up".
 */
#include "int.h"

volatile unsigned short jiffies;    /* 60 Hz clock ticks */

/* Debug markers written by dbg_mark() (see int.h). */
volatile unsigned char dbg_last;
volatile unsigned short dbg_count;
volatile unsigned short dbg_irq_sp;
volatile unsigned short dbg_brk_sp;
volatile unsigned short dbg_restart_sp;
volatile unsigned short dbg_proc_ptr;
volatile unsigned short dbg_go;
volatile unsigned short dbg_mul_r0;    /* ___mulint16 args/result (written by runtime.s) */
volatile unsigned short dbg_mul_r1;
volatile unsigned short dbg_mul_a;
volatile unsigned short dbg_st_r0;     /* self-test locals (written by kmain) */
volatile unsigned short dbg_st_a;
volatile unsigned short dbg_st_mark;   /* 0x1111 once self-test has run */

void dbg_mark(unsigned char n)
{
    dbg_last = n;
    dbg_count++;
    *(volatile unsigned char __far *)0x000F00UL = n;   /* bank-0 mirror */
}

/* JML images (4 bytes each) for the bank-2 handlers, defined in intentry.s. */
extern unsigned char tramp_irq[4];
extern unsigned char tramp_brk[4];

void timer_init(void)
{
    unsigned char i;
    volatile unsigned char __far *p;

    /* Inhibit I/O+LC shadowing so the native vector fetch reads bank-0 RAM
     * instead of ROM (stock GSSquared vp_read).  Written via the bank $E0
     * MegaII window, which reaches the C0xx handler regardless. */
    *(volatile unsigned char __far *)0x00E0C035UL = 0x40;

    p = (volatile unsigned char __far *)0x000900UL;   /* copy JML to bank 0 */
    for (i = 0; i < 4; i++)
        p[i] = ((volatile unsigned char __far *)&tramp_irq)[i];

    p = (volatile unsigned char __far *)0x000908UL;
    for (i = 0; i < 4; i++)
        p[i] = ((volatile unsigned char __far *)&tramp_brk)[i];

    *(volatile unsigned short __far *)0x00FFEEUL = 0x0900;   /* native IRQ */
    *(volatile unsigned short __far *)0x00FFE6UL = 0x0908;   /* native BRK */

    /* INTEN: enable the VBL source.  Bank $E0 because bank-0 $C0xx is RAM
     * now that IOLC shadowing is off. */
    *(volatile unsigned char __far *)0x00E0C041UL = 0x08;
}
