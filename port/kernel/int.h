#ifndef MINIX_GS_INT_H
#define MINIX_GS_INT_H

extern volatile unsigned short jiffies;

void timer_init(void);
void int_enable(void);

/* Debug markers (int.c): write byte n to bank-0 $0F00 and update the
 * bank-2 counters so the debugger probes can see where the kernel got to.
 * Defined here so context.s and every kernel file can call it. */
extern volatile unsigned char dbg_last;
extern volatile unsigned short dbg_count;
extern volatile unsigned short dbg_irq_sp;    /* SP saved by _int_irq  */
extern volatile unsigned short dbg_brk_sp;    /* SP saved by _int_brk  */
extern volatile unsigned short dbg_restart_sp;/* SP right after tcs    */
extern volatile unsigned short dbg_proc_ptr;  /* low word of proc_ptr  */
extern volatile unsigned short dbg_go;        /* probe sets 1 to release kmain stalls */
extern volatile unsigned short dbg_mul_r0;    /* ___mulint16: args (r0/r1) and result (a) */
extern volatile unsigned short dbg_mul_r1;
extern volatile unsigned short dbg_mul_a;
extern volatile unsigned short dbg_st_r0;     /* self-test locals (written by kmain) */
extern volatile unsigned short dbg_st_a;
extern volatile unsigned short dbg_st_mark;   /* 0x1111 once self-test has run */

void dbg_mark(unsigned char n);

#endif
