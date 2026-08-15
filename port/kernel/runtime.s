; Minix GS runtime helpers for vbcc 65816.
;
; ___mulint16: 16x16 -> 16 multiply emitted by vbcc for int*int.
;   ABI (vbcc machine.c declare_builtin, non-SNES/816 model): BFIRST_GPR = r0,
;   BFIRST_GPR1 = r1 -- i.e. arg1 in zpage r0, arg2 in zpage r1, result in A.
;   The compiler emits `lda a; sta r0` / `lda b; sta r1` before `jsl` (do NOT
;   implement the A/X convention here; the emitted call sites pass r0/r1).
;   Far call/return (jsl/rtl).  Clobbers r0/r1/A/X; Y and the stack are
;   caller-saved per vbcc.
; __DBR_init: data-bank marker.  vbcc emits its bank byte (^__DBR_init)
;   when casting an int to a near pointer.  Placed in bank-$02 data so
;   such casts resolve to the kernel data bank.

    section "DONTMERGE_text.far.runtime.0","acrx"
    a16
    x16
    global ___mulint16
___mulint16:
    zpage r0
    zpage r1
    lda r0
    sta _dbg_mul_r0
    lda r1
    sta _dbg_mul_r1
    lda #0
    pha
    ldx #16
rt_mul_loop:
    sep #$20
    lda r1+1                ; b.hi
    lsr a                   ; C = old hi bit0 (old value bit8)
    sta r1+1
    lda r1                  ; b.lo
    ror a                   ; bit7 = old hi bit0; C = old lo bit0 (add-test bit)
    sta r1
    rep #$20
    bcc rt_mul_shft
    clc
    lda r0
    adc 0,s
    sta 0,s
rt_mul_shft:
    lda r0
    asl a
    sta r0
    dex
    bne rt_mul_loop
    lda 0,s
    sta _dbg_mul_a
    ply
    rtl

    section "DONTMERGE_data.near.runtime.0","adrw"
    global __DBR_init
__DBR_init:
    db 0
