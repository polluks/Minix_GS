; Minix GS context switching: interrupt/BRK save, process restart, and the
; BRK syscall wrapper.
;
; Frame layout on the process's own (bank-0) hardware stack, low->high:
;   [A(2)][X(2)][Y(2)][DP(2)][DB(1)][P(1)][PC(2)][PB(1)]   = 13 bytes
; The CPU pushes PB/PC/P (BRK and IRQ both; GSSquared pops 1-byte P), then
; the prolog pushes A/X/Y/DP/DB.  save() stores SP (= frame base) in
; proc_ptr->p_sp (offset 0), switches to the bank-0 kernel stack, and calls
; the C dispatcher; restart() undoes it and RTI's into the chosen process.
;
; All dispatchers run with I=1 between save and restart, so pick_proc() is
; only ever reached in trap/interrupt context (see AGENTS.md).

    section "text.far.context.0","acrx"
    a16
    x16

; Kernel stack top (bank 0).  Must stay under $8000 (see proc.h comment).
K_STACK_TOP = $7FFE

;=============================================================================
; _int_irq: entered via the bank-0 trampoline (jml from vector $FFEE).
;=============================================================================
    global _int_irq
_int_irq:
    sei                     ; defensive (65816 sets I on IRQ anyway)
    rep #$30
    pha
    phx
    phy
    phd
    phb
    ldx _proc_ptr
    tsc
    sta !0,x                ; proc_ptr->p_sp = SP (points at saved A)
    sta _dbg_irq_sp         ; debug: the SP just saved
    stx _dbg_proc_ptr
    ldx #K_STACK_TOP        ; kernel stack (bank 0, under $8000)
    txs
    lda #20                 ; debug mark: _int_irq entry
    jsl >_dbg_mark
    jsl >_irq_dispatch
    jmp >_restart

;=============================================================================
; _int_brk: native BRK (vector $FFE6 trampoline).  BRK does NOT set I.
;=============================================================================
    global _int_brk
_int_brk:
    sei
    rep #$30
    pha
    phx
    phy
    phd
    phb
    ldx _proc_ptr
    tsc
    sta !0,x
    sta _dbg_brk_sp         ; debug: the SP just saved
    stx _dbg_proc_ptr
    ldx #K_STACK_TOP
    txs
    lda #30                 ; debug mark: _int_brk entry
    jsl >_dbg_mark
    jsl >_brk_dispatch
    jmp >_restart

;=============================================================================
; _restart: run the process proc_ptr points at (also callable from C).
;=============================================================================
    global _restart
_restart:
    lda #10                 ; debug mark: restart entry
    jsl >_dbg_mark
    lda _cur_proc
    cmp #$FC19              ; IDLE = -999
    beq _idle
    ldx _proc_ptr
    stx _dbg_proc_ptr
    lda !0,x                ; p_sp
    sta _dbg_restart_sp
    lda >$000E20            ; capture only the FIRST time
    cmp #$AA
    beq cap_done
    ldy _dbg_restart_sp     ; Y = frame base (bank 0, under $8000)
    ldx #0                  ; capture the 13-byte frame to bank-0 $0E00
    phb
    lda #0
    pha
    plb                     ; DB = 0 so near-abs,Y reads bank 0
cap_loop:
    lda $0000,y
    sta >$000E00,x
    iny
    inx
    cpx #13
    bne cap_loop
    plb                     ; DB = 2 again
    lda #$AA
    sta >$000E20
cap_done:
    tcs                     ; switch to the process's own stack
    lda #11                 ; debug mark: after tcs
    jsl >_dbg_mark
    plb                     ; undo prolog: phb phd phy phx pha
    pld
    ply
    plx
    pla
    rti                     ; pops P(1), PC(2), PB(1)

_idle:
    cli
    wai
    jmp _idle

;=============================================================================
; _asm_recv: BRK syscall wrapper.  Sets X=src, Y=mptr, A=RECEIVE and traps.
; Returns the kernel's result in A (stored back into the saved frame by
; brk_dispatch).  The nop keeps the resume point valid for both PC+1 and
; PC+2 BRK return semantics (resume lands on nop->rtl or straight on rtl).
;=============================================================================
    global _asm_recv
_asm_recv:
    ldx _sys_src
    ldy _sys_mptr
    lda #2                  ; RECEIVE
    brk
    nop
    rtl

;=============================================================================
; Locking.  Valid in irq/trap context only (callers already run with I=1);
; lock()/restore() are no-ops that document the invariant.
;=============================================================================
    global _lock
_lock:
    sei
    rtl

    global _restore
_restore:
    rtl
