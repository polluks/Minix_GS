# Minix GS — Porting MINIX 1.2 to the Apple IIgs

## Overview

Port of **MINIX 1.2** (the microkernel UNIX by Tanenbaum) to a **bare-metal Apple IIgs** (65816 CPU, no MMU). The OS is built with the **vbcc 65816 cross-compiler**, assembled with **vasm**, linked with **vlink**, and tested in the **GSSquared** emulator.

Reference source: `old-minix-1.2/` (kernel, MM, FS, lib, commands). The port lives under `port/`.

## Host Toolchain (macOS arm64)

The vbcc65816 *r2 distro* ships Linux/Win binaries only (cannot run on arm64 mac). Everything is built from source and lives in `/Users/sah/6502/`:

- **vbcc65816** (compiler): built at `/Users/sah/6502/vbcc-src/vbcc/bin/vbcc65816`. Requires regenerating `dt.h`/`dt.c` via interactive `dtgen` with the 65816 data model (see `tools/` notes).
- **vasm 2.0f** (assembler): `/Users/sah/6502/vasm-2.0f/vasm/vasm6502_oldstyle`. Built with `make CPU=6502 SYNTAX=oldstyle`. Supports `-816` (65816) and `-vobj3`.
- **vlink** (linker): `/Users/sah/6502/vlink-src/vlink/vlink`. Built with `make`. Supports appleomf, rawbin, rawseg, vobj.

### Assembled VBCC tree

`/Users/sah/6502/vbcc65816-mac/` = mac-built `bin/` (vbcc65816, vc, vasm6502_oldstyle, vobjdump, vlink, vprof) + `config/` + `targets/65816-iigs/` (headers, libvc.a, libm.a, startup.o) copied from the r2 distro. Set `VBCC=/Users/sah/6502/vbcc65816-mac` and put `$VBCC/bin` on PATH.

## VERIFIED Compiler/Toolchain Facts (do not re-derive)

- **Call model**: default code model is **far** — all calls are `jsl >func` / returns `rtl` (24-bit addresses). This works even within a single bank. The `-sc` flag is BROKEN for calls (emits `rts` in callees but `jsl >target` in callers → stack corruption). **Never use `-sc`.**
- **Optimization -O=0 ONLY (CRITICAL, verified end-to-end)**: vbcc 65816 backend V0.2's stack-arg convention at `-O>=2` is BROKEN. At `-O=0` args are passed in registers (A + X for the bank byte of far/near pointers; last arg pushed via `pea`), and the callee spills them to *its own* frame (`sta 1,s` / `sta 3,s`). At `-O>=2` the caller additionally pre-stores the register-arg into *its own* frame slot, but the callee reads *its* post-prologue `$01,s` — off by `3 (return) + callee frame` bytes → args arrive as garbage (e.g. `console_puts` read stale `0x0416` instead of the string pointer, writing junk `0x00` to the text pages → blank screen). `real_offset()` never accounts for the return address + saved regs for params (only the `off<0` branch does, but params get positive offsets). **Use `-O=0` for all kernel C code** until the backend is fixed.
- **Data model**: near 16-bit pointers, resolved via DB (data bank). `zpage` r0-r31 + btmp0-3 are scratch regs; the compiler emits `zpage btmpN` as *imports* — actual storage must be provided by our startup (reserve 2 each; r0-r31=0x00-0x3E, btmp0-3=0x40-0x46 in zpage).
- **Sections emitted**: `DONTMERGE_text.far.<name>.<n>` (acrx), `DONTMERGE_data.near.<name>.<n>` (adrw), `DONTMERGE_bss.near.<name>.<n>` (aurw), `DONTMERGE_rodata...`, `zpage` (adrwz).
- **Sections/attributes**: vlink script pattern syntax is `filepat(sectionpat)` e.g. `*(DONTMERGE_text*)`. Section names include a numeric prefix in vlink's errors but the pattern matches the base name.
- **24-bit addressing works**: linking with a linker script `MEMORY { BANK: ORIGIN=0x020000, LENGTH=0x10000 }` and `SECTIONS` with explicit VMAs resolves all JSL targets to `$02xxxx` correctly (VOBJ3 = 3 bytes/address). Confirmed in rawbin output: `22 00 01 02` = JSL $020100.
- **zpage must be at bank base**: vbcc uses DP-relative addressing; set DP=0 and place zpage section first at the bank base ($xx0000) so r0-r31/btmp land at $0000-$00FF.
- **Assembly syntax** (vasm oldstyle, 65816): `>` = long (24-bit) → `jsr >addr` IS `jsl`; `!` = near; `^` = bank byte. `a16`/`x16`/`a8` pseudo-ops declare A/X width for the assembler's optimizer; compiler emits `rep/sep #32` and `#`/$20 to actually switch M/X (M=bit5, X=bit6 of P). Data directives: **`db`/`byte`/`defb`, `dw`/`word`/`defw`, `dl`** (NOT `dc.b`/`dc.w` — `dc` is a space directive and `dc.b` fails; NOT `.word`). vbcc itself emits `db`, `dw`, `dd`, `reserve`, `zpage` — matches vasm.
- **MVN/MVP (verified with vasm + snes9x)**: vasm oldstyle syntax is standard `mvn <src>,<dest>` (source first); it emits `54 <dest> <src>` — the hardware order, **first byte after the opcode is the DESTINATION bank, second is the SOURCE bank** (snes9x `Op54`/`Op44` and GSSquared's `move_memory` in `base_6502.cpp` agree). MVN copies A+1 bytes from (src_bank : **X**) to (dest_bank : **Y**), incrementing X and Y each byte and decrementing A (rewind while A ≠ $FFFF); MVP is identical but decrements X/Y. X = source address, Y = dest address for both; DB is left = dest bank. So `mvn #$02,#$00` → `54 00 02` = src bank $02 → dest bank $00 — same on real hardware and GSSquared. (The earlier note that the emulator "swaps vs spec" was wrong.)
- **Far pointers**: vbcc 65816 `__far` = 24-bit pointer (indirect long via zpage btmp regs). `vu8 __far *p = (vu8 __far*)0x00C030UL; *p = v;` → `sta [btmp3]`. Use for ALL bank-0 I/O ($C000-$CFFF), text pages, vectors from the bank-$02 kernel.
- **IIgs iigs config** (r2): `-const-in-data -unsigned-char -mask-opt`; assembler `-816 -vobj3 -quiet -nowarn=62 -opt-branch -ldots -Fvobj`; linker `-stack=4096 -maxsegsize=32768 -mtype -version=2 -b appleomf -Cvbcc` + startup.o + `-lvc`. The stock `startup.s` targets GS/OS (`$E10000` calls) — NOT usable for bare metal; we write our own.
- Full end-to-end verified: `vc +iigs -O files.c` → valid IIgs OMF (magic `9B 4D`, `_text.startup`). And flat `rawbin` link at $020000 → correct bank bytes.

## Memory Model / Architecture

- **No MMU**. Per-process 64KB bank in expansion RAM; kernel copies via DB manipulation. Bank isolation = memory protection.
- **Bank layout (plan)**: bank $02 kernel text, $03 kernel data/stack, $04+ processes/tasks. Bank 0 = main memory ($0000-$BFFF RAM; $C000-$CFFF I/O; $D000-$FFFF ROM/LC). The IIgs shadow register ($C035) controls ROM shadowing of $C000-$FFFF; LC RAM at $D000-$FFFF is read when RAMRD ($C080) is set. **Vectors ($FFE4-$FFFF) are NOT "always RAM"** — in GSSquared they come from ROM unless RAMRD is on AND the emulator's `vp_read` honors RAMRD (see interrupt bring-up note below).
- **Interrupt bring-up (VERIFIED in GSSquared, kernel change + 2 emulator fixes)**: timer_init copies trampolines to $0900/$0908, writes vectors $FFEE=0900/$FFE6=0908 **BEFORE** `$C080` (LC RAMRD, write-enable off), then `$C041=0x08` (INTEN bit3=VBL). VBL scanner event → f_vblint_asserted → MegaII IRQ → CPU push P/PC/PB → vector $FFEE (LC RAM) → $00:0900 → `jml >$0203D3` prolog (`rep #$30; pha; phx; phy; phd; phb`) → jsl >$0202E7 (`sta >$C047; inc $049E`) → epilog (`plb pld ply plx pla`) → `rti`. jiffies@$02049E ticks 60 Hz. **Emulator bugs fixed in the GSSquared clone (NOT upstream, NOT in this repo)**: (1) `MMU_IIgs::vp_read` ignored RAMRD and always returned ROM for bank-0 vector fetches → kernel got ROM's $C074 vector instead of $0900; (2) `display_write_c041` never set `f_vbl_enable`, so INTEN bit3 never reached the MegaII IRQ logic. On real hardware only the kernel change is needed.
- **I/O and special pages exist ONLY in bank 0**: in expansion-RAM banks $02+, $C000-$CFFF is plain RAM, not I/O; text pages $0400/$0500 and vectors $FFD0-$FFFF also live in bank 0. Kernel in bank $02 must reach them with `__far` 24-bit pointers.
- **Hardware stack is ALWAYS in bank 0** (65816 native, 16-bit SP) — all process/kernel stacks must live in bank 0 ($8000-$BFFF region). DP addressing is DBR-relative (DP:offset within current DBR bank).
- **80-col text layout (VERIFIED, incl. GSSquared `src/display/text_page_layout.hpp`)**: classic Apple II nonlinear row offsets — row r base = `$0400 + ((r&7)*0x80) + ((r>>3)*0x28)` (row offsets 0x000,0x080,...,0x3D0). 80-col interleaves per char pair at offset x: **even column (2x) = AUX `$01:0400+base+x`**, **odd column (2x+1) = MAIN `$00:0400+base+x`**. Aux = bank $01 (+0x10000 in GSSquared). Page 2 = $0800. Writing bank1 $0400 in GSSquared lands in the aux text buffer the scanner reads (calc_aux_write passes bank-1 addresses through).
- **Context switch**: on interrupt, 65816 pushes P (1 or 2 bytes per M flag) then PC (bank:offset). Interrupt entry prolog: `php` (re-push interrupted P, same size), `rep #$30`, then save A/X/Y/DP/DB, switch SP to kernel stack, JML to handler. Restore: `plb pld ply plx pla` then `rti` — RTI pops P at the size dictated by its own M bit and 3-byte PC, returning to the right bank automatically.
- **Syscalls**: use `brk` (native BRK vector $FFE6). B flag in pushed P distinguishes BRK (syscall) from IRQ. Args in A=function, X=src_dest, Y=m_ptr; return in A. Mirrors Minix `int 32` / RET_REG.
- **minix message size** on 8086: `Msize = 12` words; cp_mess copies 11 words after the source field.

## Testing

- **GSSquared 0.7.1101** (`/Applications/GSSquared.app`) is the test emulator (GUI app; IIgs ROMs in `Contents/Resources/roms/apple2gs/main.rom` + `char.rom`). No useful CLI found; it boots disk images via GUI/menus. Buildable from source (CMake + SDL3) for a CLI `GSSquared`. GSSquared maps the firmware image into slot 5 (`main_rom + 0x1C500`, "GS INT"), IWM slot 5 = 3.5" SmartPort drives.
- **Disk image**: build an 800K disk image with `port/tools/mkdisk.py`: block 0 = custom ProDOS 8 boot block; blocks 1..N = raw kernel image (`kernel.raw`). `bootblock.s` assembles for **org $0800**; mkdisk.py locates the nblocks byte (immediately after the parlist) via a byte-signature search and patches it.
- **Boot flow (VERIFIED, corrected)**: the firmware loads block 0 to **$0800 (bank 0)** and runs it in **emulation mode** from **$0801** (byte 0 = ProDOS signature $01, which the firmware checks). Entry regs A/X/Y are set by firmware (A=0x3178 X=0x50 Y=2 observed; don't rely on them — compute the slot from X like the ProDOS boot block). Boot block: `sei;cld`; read kernel blocks via SmartPort into bank 0, then `clc;xce` (native), `rep #$30`, DB=$02, `jml >$020100`. Mode switching: emulation→native = `clc;xce`; native→emulation = `sec;xce`.
- **SmartPort call layout (VERIFIED from ROM 01 disassembly + emulator traces)**: `jsr $C50D` is followed in-memory by 5 inline bytes. Let `base` = the return address the caller's JSR pushed (= `[S+7]` at FF:6AC5, measured = $0808 for a JSR at $0806, i.e. JSR-addr+2). The firmware parses: **cmd at `[base+1]`**, **16-bit param-list ptr at `[base+2..3]`** (`LDA [$57],Y; Y=1`), and patches the caller's return address to **`base + 5`** (verified arithmetic at FF:6ADB-6AE7: `AND #$0002; EOR #$0002; CLC; ADC #$0003; ADC $07,S` → constant +5 for cmds $01/$41). So the return lands on the **6th inline byte**. Correct call: `jsr $C50D; db $00`(lead)`, db cmd, dw parlist, db $00` and put the continuation at the next byte — e.g. `jsr $C50D; db $00; db $01; dw parlist; db $00; bcs`. **Do NOT** use `dw $0000` for the last two inline bytes: the return target lands on the 6th byte, and a trailing `$00` there executes as BRK. (Earlier AGENTS.md example `...; dw $0000` would BRK.)
- **SmartPort entries**: internal 3.5" SmartPort at **slot 5**; slot signature `$C5FF=$0A`; ProDOS block-device entry **$C50A** (SEC, register-based), SmartPort dispatch **+3 = $C50D** (CLC). `$C50D` prologue self-detects emulation callers; C clear = success, A=0. Unit numbers start at **$01** (internal boot 3.5" = unit 1). **Standard READ BLOCK** cmd $01 param list: `db count`, `db unit`, `dw buffer` (bank 0 only), block `db lo,mid,hi`. **Extended READ BLOCK** cmd $41 param list: `db count`, `db unit`, buffer `db lo,hi,bank,res` (reads directly into bank $02), block `db lo,mid,hi,res`. Extended reads into bank $02 NOT yet verified in GSSquared (re-test with the corrected 5-byte layout pending).
- **Real ProDOS disk boots in GSSquared (VERIFIED)**: sys6.po's block 0 runs and reaches $2000, and its first C50A read completes in ~8 s wall-clock. sys6's IIgs path IS the register-based **$C50A** entry (slot computed from X, dispatch addr from `$C5FF`); the $0986 direct-IWM routine is only the Apple-II fallback (copied from slot ROM when `$C5FF` = 0). **C50A return contract**: the driver returns via `RTS`, so the caller must push a return address — sys6 does `jsr $0927` where `$0927: LDA $60; STA $44; LDA $61; STA $45; JMP ($0048)`. A bare `jmp ($0048)` (our first test) never returns and crashes into the FE/FF boot-error path.
- **Firmware driver structure (disassembled, both entries converge)**: C50D = CLC/ROR/AND#$80/STA $E10FB0 (SmartPort, bit7=0); C50A = SEC/BCS C50E (block-device, bit7=1). Both → JSL $FF6AB5. FF:6AB7 BCC $6ABC (emulation) vs JMP $6FC8 (native); 6ABD `LDA $E10FB0; BMI $6AEB` (bit7 → skip param parse); driver at 6AEB: PHP/SEI/JSR $6F4D/JSR $6A6E → delay loop FF:6A80-6A92 (`LDA $C08C,X; PHY; LDY #$D9; DEY; BRA×3; BNE` ~217 iters) → slot-5 firmware driver at bank 0 $C600+ (main.rom offset 0x1C600): C628 `LDX $2B` (drive select), C62E `LDA $C088,X; JSL $FF65B1` (direct IWM read), **C65E sync poll** `LDA $C08C,X; BPL` then EOR #$D5 / CMP #$AA / CMP #$96 with Y-countdown retry → C627 outer retry (DEC $03) → after $03 runs out, C62E direct read.
- **IWM sync-poll hang (ours)**: both C50D and C50A calls reach the C65E poll; the CPU sits there (~670 hits per 25 s, identical for sys6 and ours) but **ours never receives IWM data** (60-100 s+), while sys6's reads complete in ~8 s. zpage state at C50A entry is byte-identical between sys6 and ours except **$46 = block number (sys6 = 2, ours = 1)** and the Y register. Leading untested hypothesis: the firmware driver refuses/times out on block 1 (only blocks ≥ 2 read reliably), or a spin-up timing difference. Next test: boot block reading block 2 first.
- **Kernel entry contract**: native mode, SEI, DB=$02, M/X=16, DP=$0000, SP=$BFFE (bank-0 stack $8000-$BFFF); zpage storage (r0-r31 + btmp0-3) defined in startup.s at $020000; `_start` = first text symbol at $020100.

## Status

- [x] vbcc65816 toolchain built & verified on macOS arm64 (compiler, vasm, vlink)
- [x] Rawbin link at $020000 with correct 24-bit bank bytes
- [x] Boot/SmartPort conventions verified (slot 5, $C50D, cmd $01/$41, unit $01)
- [x] 80-col text layout confirmed (row map + aux/main interleave)
- [x] Project skeleton under `port/` (boot/bootblock.s, tools/mkdisk.py, tools/gs2* debug harness, README credits)
- [~] Boot block + 800K disk image builder — reads work for sys6 (C50A, ~8 s/read) but our C50A call hangs at the IWM sync poll; block-1-vs-2 hypothesis untested
- [x] IIgs bare-metal bring-up: console works — **M1 banner displays in GSSquared 80-col mode** (kernel at $020100 → kmain → console_init/puts/putchar; blank screen was the `-O=2` arg bug, fixed by `-O=0`)
- [ ] VIA2 timer, ADB
- [x] Interrupt entry: VBL IRQ + 60 Hz jiffies ticker working in GSSquared (kernel $C080/$C041 + LC vectors; emulator needed the 2 fixes above — verify on real hardware)
- [ ] Microkernel scheduler + IPC (Minix proc.c/mpx88.s port)
- [ ] MM, FS (SmartPort block driver), userland

## Key References

- MINIX source: `/Users/sah/ai/Minix-GS/old-minix-1.2/` — `src/kernel/{mpx88.s,klib88.s,proc.c,system.c,main.c,table.c}`, `h/com.h`, `h/type.h`
- vbcc: `/Users/sah/6502/vbcc-src/vbcc/machines/65816/` (backend); r2 distro `/Users/sah/6502/vbcc65816/`
- vasm: `/Users/sah/6502/vasm-2.0f/vasm/`; vlink: `/Users/sah/6502/vlink-src/vlink/` (docs: `vlink.texi`)
- GSSquared source: `/var/folders/.../T/opencode/gs2src` (shallow clone)
