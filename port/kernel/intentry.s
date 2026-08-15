; Minix GS interrupt trampolines.
;
; 4-byte "jml >_int_irq"/"jml >_int_brk" images, installed by int.c as part
; of the interrupt bring-up.  The CPU interrupt frame (PB, PC, P) sits below
; the trampoline's JML, so it survives the jump and is handled by context.s
; (save/restart) and the final RTI.

    section "text.far.int.0","acrx"
    global _int_enable
_int_enable:
    cli
    rtl

; Trampoline byte images: JML ><handler> with the 24-bit target resolved at
; link time.  (Deliberately data, not runtime-computed code, to sidestep
; vbcc's broken pea-arg handling for function pointers.)
    section "rodata.near.tramp.0","adrw"
    global _tramp_irq
_tramp_irq:
    db  $5C
    dl  _int_irq
    global _tramp_brk
_tramp_brk:
    db  $5C
    dl  _int_brk
