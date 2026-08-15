; Minix GS kernel startup (bare-metal, bank $02).
;
; Entry contract (see AGENTS.md): native mode, SEI, DB=$02, M/X=16,
; DP=$0000, SP=$7FFE (bank-0 stack under $8000 -- see proc.h). Reached via
; JML >$020100 from the boot block. zpage storage (r0-r31 + btmp0-3) lives
; at $020000, right at the bank base, so DP-relative addressing hits
; $0000-$00FF.

    section zpage,"adrwz"
    global r0
r0:     reserve 2
    global r1
r1:     reserve 2
    global r2
r2:     reserve 2
    global r3
r3:     reserve 2
    global r4
r4:     reserve 2
    global r5
r5:     reserve 2
    global r6
r6:     reserve 2
    global r7
r7:     reserve 2
    global r8
r8:     reserve 2
    global r9
r9:     reserve 2
    global r10
r10:    reserve 2
    global r11
r11:    reserve 2
    global r12
r12:    reserve 2
    global r13
r13:    reserve 2
    global r14
r14:    reserve 2
    global r15
r15:    reserve 2
    global r16
r16:    reserve 2
    global r17
r17:    reserve 2
    global r18
r18:    reserve 2
    global r19
r19:    reserve 2
    global r20
r20:    reserve 2
    global r21
r21:    reserve 2
    global r22
r22:    reserve 2
    global r23
r23:    reserve 2
    global r24
r24:    reserve 2
    global r25
r25:    reserve 2
    global r26
r26:    reserve 2
    global r27
r27:    reserve 2
    global r28
r28:    reserve 2
    global r29
r29:    reserve 2
    global r30
r30:    reserve 2
    global r31
r31:    reserve 2
    global btmp0
btmp0:  reserve 2
    global btmp1
btmp1:  reserve 2
    global btmp2
btmp2:  reserve 2
    global btmp3
btmp3:  reserve 2

    section "text.far.startup.0","acrx"
    global _start
_start:
    sei
    rep #$30            ; M/X = 16
    a16
    x16
    ldx #$7FFE
    txs                 ; kernel hardware stack in bank 0 (under $8000)
    lda #$0000
    tcd                 ; DP = $0000 (already 0, be explicit)
    jsl >_kmain         ; never returns

halt:
    wai
    jmp halt
