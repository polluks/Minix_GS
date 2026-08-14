; Minix GS interrupt trampolines.
;
; The 65816 fetches native vectors from bank 0 ($FFE6 BRK, $FFEE IRQ) and
; forces PB=0 for the handler, so the vector cannot point straight at bank-$02
; code.  int.c installs these 4-byte "jml >_int_irq"/"jml >_int_brk"
; trampolines in bank-0 RAM ($0900/$0908) and points the vectors at them.
; The CPU interrupt frame (PB, PC, P) sits below the trampoline's JML, so it
; survives the jump and is handled by context.s (save/restart) and the final
; RTI.

    section "text.far.int.0","acrx"
    global _int_enable
_int_enable:
    cli
    rtl

; Trampoline byte images: JML ><handler> with the 24-bit target resolved at
; link time.  int.c copies these into bank-0 RAM ($0900/$0908) and points the
; native vectors at them.  (Deliberately data, not runtime-computed code, to
; sidestep vbcc's broken pea-arg handling for function pointers.)
    section "rodata.near.tramp.0","adrw"
    global _tramp_irq
_tramp_irq:
    db  $5C
    dl  _int_irq
    global _tramp_brk
_tramp_brk:
    db  $5C
    dl  _int_brk
