; Minix GS runtime helpers for vbcc 65816.
;
; ___mulint16: 16x16 -> 16 multiply emitted by vbcc for int*int.
;   ABI (vbcc machine.c declare_builtin): A = arg1, X = arg2, result in A.
;   Far call/return (jsl/rtl).  Clobbers A, X; preserves Y via phy.
;   (vasm's 65816 table has no MUL instruction, so do a 16-bit shift-add.)
; __DBR_init: data-bank marker.  vbcc emits its bank byte (^__DBR_init)
;   when casting an int to a near pointer.  Placed in bank-$02 data so
;   such casts resolve to the kernel data bank.

    section "DONTMERGE_text.far.runtime.0","acrx"
    a16
    x16
    global ___mulint16
___mulint16:
    phy
    phx
    pha
    pha
    lda #0
    sta 0,s                ; result = 0
    ldx #16
rt_mul_loop:
    sep #$20
    lda 4,s                ; b.lo
    lsr a
    sta 4,s
    lda 5,s                ; b.hi
    ror a
    sta 5,s
    rep #$20
    bcc rt_mul_shft
    clc
    lda 2,s                ; a
    adc 0,s
    sta 0,s
rt_mul_shft:
    lda 2,s                ; a <<= 1 (16-bit) via accumulator
    asl a
    sta 2,s
    dex
    bne rt_mul_loop
    lda 0,s
    ply
    ply
    ply
    ply
    rtl

    section "DONTMERGE_data.near.runtime.0","adrw"
    global __DBR_init
__DBR_init:
    db 0
