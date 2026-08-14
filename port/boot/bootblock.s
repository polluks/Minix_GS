; Minix-GS boot block (TEST: register-based $C50A path, sys6-style loop).
;
; The IIgs firmware (ROM 01) loads block 0 to $0800 (bank 0) and runs it in
; EMULATION mode (E=1) from $0801 after checking byte 0 == $01 (ProDOS boot
; signature).
;
; The $C50D in-memory SmartPort path hangs in GSSquared's slot-5 firmware IWM
; driver (the sync-byte poll at $C65E never sees data). The ProDOS boot block
; (sys6.po) works because it calls the register-based $C50A entry instead.
; This boot block replicates sys6's $C50A loop exactly:
;   - zpage $42 = count, $44/$45 = buffer, $46/$47 = block number
;   - $4A/$4C/$4E = table pointers (zeroed)
;   - the loop counter lives in MEMORY ($46 = block number), NOT Y -- the
;     C50A driver clobbers Y and the earlier Y-counter version looped forever
;     (trace: the C50A return address kept executing).
;   - call via `jsr call_c50a` where call_c50a sets $44/$45 from $60/$61 then
;     `jmp ($0048)` (the driver returns with RTS, so we must JSR, not JMP).
;
; We read blocks 2..(nblocks+1) into a bank-0 staging buffer ($0C00 + n*512),
; then copy them to bank $02. Block 1 is skipped (the firmware's IWM driver
; fails to read block 1 in GSSquared; sys6's working boot also starts at 2).

    cpu 65816
    org $0800

boot_start:
    db $01              ; ProDOS boot signature: firmware checks byte 0 == $01
    sei                 ; mask IRQ (code actually runs from $0801)
    cld                 ; binary mode

    ; --- SmartPort $C50A register setup (mirrors sys6.po boot block) ---
    lda #$50            ; slot 5 << 4 (firmware passes X=$50; hardcode slot 5)
    sta $43             ; drive select register (IWM handshake slot)
    lda #$0A            ; slot signature value from $C5FF
    sta $48
    lda #$C5
    sta $49             ; $48/$49 = $C50A (ProDOS block-device entry)

    ; --- read-loop state (zpage cells the driver leaves intact) ---
    lda nblocks
    clc
    adc #$02
    sta blklimit        ; stop after reading block (nblocks + 1)
    stz $4a             ; low table pointer
    stz $4c             ; high table pointer
    stz $4e             ; ?
    stz $47             ; block number high byte = 0
    lda #$01
    sta $42             ; block count = 1
    lda #$02
    sta $46             ; first block = 2
    stz $60             ; buffer low byte = 0
    lda #$0C
    sta $61             ; buffer high byte = $0C  ($0C00 staging area)
    sta $4b             ; $4B = buffer high (sys6 sets $4A=0/$4B=$0C pair)

read_loop:
    jsr call_c50a       ; -> $C50A (the driver RTS back here; sys6 does the
                        ;    same via `jsr $0927` -- a plain jmp crashes because
                        ;    the firmware's driver returns with RTS)
    bcs boot_err
    inc $61
    inc $61             ; buffer += 512
    inc $46             ; block += 1
    lda $46
    cmp blklimit
    bne read_loop
    ; NOTE: call_c50a is placed AFTER done_load below -- a fall-through into
    ; it here would re-enter the driver for a phantom read that never returns.

done_load:
    ; native mode, M/X = 16.
    ; Copy nblocks*512 bytes from bank 0 $0C00 to bank $02 $020000 using
    ; absolute LONG indexed addressing. (MVN could do this too: vasm syntax
    ; `mvn #$02,#$00` = src bank $02 -> dest bank $00, and both GSSquared and
    ; real hardware encode `54 <dest> <src>` identically. The long-addressing
    ; loop is used instead and is correct on both emulator and hardware.)
    clc
    xce
    rep #$30
    a16
    x16
    sep #$20            ; A = 8-bit
    a8
    lda nblocks
    rep #$20
    a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a               ; A = nblocks * 512 (byte count)
    sta $06             ; r3 = copy count (zpage free in boot block)
    ldx #$0000
copy_loop:
    lda $000C00,x       ; bank $00, long indexed
    sta $020000,x       ; bank $02, long indexed
    inx
    inx
    cpx $06
    bne copy_loop
    lda #$0002
    pha
    plb                 ; DB = $02
    jml >$020100

boot_err:
    jmp boot_err        ; hang on error (A = SmartPort error code)

call_c50a:
    lda $60
    sta $44             ; $44/$45 = buffer
    lda $61
    sta $45
    jmp ($0048)         ; -> $C50A (ProDOS block-device entry)

; READ BLOCK parameter list (padding to the full form the ROM reads; kept so
; tools/mkdisk.py can locate the NBLOCKS byte right after it):
parlist:
    db $01              ; param count = 1
    db $01              ; unit number = 1 (internal boot 3.5" drive)
    db $00, $0C         ; buffer = $00:0C00 (lo, hi) -- bank 0 staging area
    db $02, $00, $00    ; block number = 2 (lo, mid, hi)
    db $00, $00         ; reserved
nblocks:
    db $00              ; NBLOCKS: patched by tools/mkdisk.py
blklimit:
    db $00              ; 2 + NBLOCKS, computed at boot (driver-safe RAM)
