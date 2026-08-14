; Minix GS interrupt entry (native-mode IRQ/BRK prolog + epilog).
;
; The 65816 fetches native vectors from bank 0 ($FFE6 BRK, $FFEE IRQ) and
; forces PB=0 for the handler, so the vector cannot point straight at bank-$02
; code.  Instead int.c installs 4-byte trampolines in bank 0
; ("jml >int_irq" / "jml >int_brk") and points the vectors at them.  The CPU
; interrupt frame (PB, PC, P) sits below the trampoline's JML, so it survives
; the jump and is popped by the final RTI.
;
; Frame accounting (GSSquared 65816 model): the emulator pushes PB(1), PC(2),
; P(1) and RTI pops P(1), PC(2), PB(1) -- one P byte regardless of M.  So the
; prolog does NOT re-push P; it only saves A/X/Y/DP/DB on top and restores
; them before RTI.
;
; Entry invariants (single-context kernel): DB=$02, DP=$0000, hardware stack
; is the bank-0 kernel stack.  No stack switch yet (comes with the scheduler).

    section "text.far.int.0","acrx"
    global _int_irq
_int_irq:
    rep #$30            ; M/X = 16
    a16
    x16
    pha
    phx
    phy
    phd
    phb
    jsl >_irq_handler
    plb
    pld
    ply
    plx
    pla
    rti

    global _int_brk
_int_brk:
    rep #$30
    a16
    x16
    pha
    phx
    phy
    phd
    phb
    jsl >_brk_handler
    plb
    pld
    ply
    plx
    pla
    rti

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
