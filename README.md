# Minix GS — Minix on the Apple IIGS

Port of [Minix 1.2](https://en.wikipedia.org/wiki/MINIX) (the classic 8088
microkernel UNIX) to the **Apple IIGS** (65816, 2.8 MHz, up to 8 MB RAM),
using the **vbcc 65816** cross-compiler toolchain.

This is a real, bare-metal port: Minix replaces GS/OS and owns the machine
— no Toolbox, no ProDOS runtime. The IIGS is booted into 65816 native mode
and Minix's kernel/MM/FS run as message-passing processes, exactly as on the
PC it was written for.

## Why this is feasible

Minix 1.2 was written for the 8088/8086: a 16-bit word, segmented 20-bit
address space, no MMU, message-passing microkernel. The 65816 is a 16-bit
CPU with a 24-bit (banked) address space and no MMU — a very similar target.
The mapping has been discussed since the machine shipped
([comp.os.minix, 1989](https://groups.google.com/g/comp.os.minix/c/fRikj9II0e4),
[6502.org, 2021](https://6502.org/forum/viewtopic.php?t=6536)) but never
completed, partly because no capable 65816 C toolchain existed. That changed
when Volker Barthelmann released **vbcc for 65816** (2025) with an Apple IIGS
library target.

| Minix 1.2 (PC)         | Apple IIGS                  |
|------------------------|-----------------------------|
| 8088 @ 4.77 MHz        | 65816 @ 2.8 MHz             |
| 20-bit address space   | 24-bit address space (banks)|
| 16-bit registers       | 16-bit registers (native)   |
| No MMU                 | No MMU                      |
| INT 0x21-ish syscalls  | native BRK trap ($FFE6)   |
| 8259 PIC               | Mega II IRQ controller    |
| 8253 timer             | VBL interrupt (~60 Hz)    |
| 6845 MDA/CGA text      | VGC 80-col text mode      |
| PC keyboard + BIOS     | ADB keyboard                |
| floppy + ST-506/IDE    | SmartPort (3.5" floppy, RAM, ProDOS devices) |

## Status

Work in progress, being brought up bottom-up. The kernel boots bare-metal in
the **GSSquared** emulator: the 80-column console works (true mixed case via
the ALT charset), and the MINIX 1.2 scheduler code is ported with three
kernel tasks (clock, A, B) wired up for round-robin. The round-robin is
driven by the VBL interrupt, and that 60 Hz ticker is currently being
revalidated on the stock (unpatched) emulator via the ROM trampoline path —
see AGENTS.md.

- [x] vbcc 65816 toolchain built for macOS arm64 (compiler + `dtgen`)
- [x] 65816 data model generated (`dt.h`: 16-bit `int`, 32-bit `long`, 64-bit `long long`, 16-bit near pointer)
- [x] vasm 65816 + vlink built for macOS
- [x] Toolchain smoke test (rawbin link at $020000, correct 24-bit bank bytes)
- [x] Boot loader / raw block-0 bootstrap (ProDOS 8 boot block + SmartPort, 800K image)
- [x] Kernel bring-up: 65816 startup, bank-0 kernel stack, M1 banner in 80-col text
- [x] Console driver (80-column text mode, aux/main interleave, true lowercase via ALT charset)
- [~] Interrupt entry: 60 Hz `jiffies` ticker worked only with the reverted emulator patches; must be revalidated on stock GSSquared via the ROM trampoline path ($C074 / $E1:0010)
- [~] Microkernel scheduler + IPC: `proc.c` port in place, 3 kernel tasks (clock, A, B) round-robin; runtime debugging via dbg_mark/STALL probes
- [ ] ADB keyboard driver
- [ ] SmartPort block device driver (read path works for real ProDOS; our driver still hangs at the IWM sync poll)
- [ ] `kernel`, `mm`, `fs` processes and IPC
- [ ] `init`, shell, basic commands
- [ ] Bootable image tested under GSplus

### Known quirks

- **`-O=0` only.** vbcc's 65816 backend at `-O>=2` mishandles stack-arg
  passing; all kernel C is built at `-O=0` (args passed in registers A/X + a
  trailing `pea`), which has been verified empirically for multi-arg and
  pointer-arg calls.
- **Lowercase rendering needs the ALT charset.** GSSquared's `CharRom`
  maps screen codes `$40-$7F` through the Apple-II flash table, garbling
  lowercase; the kernel enables the ALT charset (`$C00F`) and folds
  `$40-$5F` to `$00-$1F` so both cases render from the linear glyph table.
  This is a kernel-side workaround for a stock-emulator quirk (see AGENTS.md).
- **Boot is non-deterministic (~1 in 3-4 hangs).** The firmware's SmartPort
  read sometimes spins forever at the IWM sync poll; relaunching the emulator
  retries the boot. See AGENTS.md.

## Architecture

Minix 1.2 is three independent programs plus userland, talking only through
a tiny kernel message mechanism:

```
+--------------------------------------------------------------+
|  user processes (init, sh, ls, ...)                          |
+--------------------------------------------------------------+
|  MM (memory manager)   |   FS (file system)                  |
|  fork/exec/brk/signal  |   open/read/write/mount/...         |
+--------------------------------------------------------------+
|  KERNEL (microkernel: clock, tty, floppy, syscall + msg code) |
+--------------------------------------------------------------+
|  IIGS hardware (VGC, VIA, ADB, SmartPort, Ensoniq)           |
+--------------------------------------------------------------+
```

Each Minix process gets its own 65816 bank(s). Message passing is the
copy-data-then-send model of Minix 1.x (`sys_call`/`mini_send`/
`mini_receive`), which maps cleanly onto banked memory and avoids needing
shared address space.

### Memory model

vbcc 65816 supports **near / far / huge** pointers and memory models. The
port plan:

- **near (16-bit) pointers**: default within a process's own 64 KB bank
- **far (24-bit) pointers**: `__far` for cross-process message buffers and
  the message array in the kernel
- `long` (32-bit) for everything Minix uses `long` for — times, disk
  addresses — matching Minix 1.2's own 32-bit `long` on the 8088
- `unsigned short` for the 16-bit quantities Minix used `int` for

### Process layout (one bank each)

```
   bank n+1  user  (program text/data/stack)
   bank n    per-process kernel frame: regs, mem map, msgbuf
   ...
```

`kernel` lives in a low bank; MM and FS each get a bank; up to 16 user
processes. The 65816 has a 16-bit stack pointer — each process switch swaps
`S`/`PB`/`DB`/DP and restores its register frame from its own bank.

### Bank layout (current)

```
bank $00  main RAM + I/O ($C000-$CFFF) + LC RAM ($D000-$FFFF, vectors)
bank $01  aux text buffer (80-col odd/even interleave)
bank $02  kernel text/data + zpage ($020000-$0200FF)
bank $03  kernel data/stack (future)
bank $04+ processes/tasks (future)
```

No MMU — a 64 KB bank per process is the memory protection. The hardware
stack is always in bank 0; per-task kernel stacks live at $A000-$ABFF and
the kernel stack at $8000-$BFFF (bank 0). Text pages ($0400/$0500) and I/O
($C000-$CFFF) are bank-0 only, reached from bank-$02 kernel code with
`__far` 24-bit pointers.

### Boot flow

The firmware loads the ProDOS 8 boot block (block 0) to $0800 and runs it in
emulation mode. The boot block switches to native mode, reads the raw kernel
image from the SmartPort drive into bank $02, then `jml >$020100` into
`_start`. `_start` sets up the 16-bit native state and calls `kmain`.

## Toolchain

The official vbcc 65816 distribution ships Windows and Linux binaries only.
This project builds everything from source on macOS (arm64):

- **vbcc** (compiler, incl. `machines/65816` backend): `www.compilers.de/vbcc.html`
- **vasm** (assembler, `cpu=65816`): 65816 support
- **vlink** (linker): Apple IIGS OMF output support

`dtgen` is interactive; the project pins the answers needed for the 65816
data model (see `tools/`).

### Build recipe (macOS arm64)

```sh
# vbcc
curl -L -o /tmp/vbcc.tar.gz http://www.ibaug.de/vbcc/vbcc.tar.gz
tar xzf /tmp/vbcc.tar.gz
cd vbcc
make TARGET=65816
# answer dtgen prompts for: char, unsigned char, short, unsigned short,
# int(16-bit), long(32-bit), long long(64-bit), float, double
```

> Note: the current vbcc snapshot's `supp.h` no longer defines the `zchar`..
> `zullong` typedefs that the 65816 `machine.h` union still uses — add them
> (or use the `dt.h` typedefs) if the build fails at `machine.h:70`.

## Repository layout

```
Minix-GS/
├── README.md              # this file
├── AGENTS.md              # working notes: toolchain, memory model, bring-up facts
├── old-minix-1.2/         # Minix 1.2 sources (reference; unchanged)
│   ├── include/           # public headers
│   └── src/
│       ├── kernel/        # microkernel (mpx88.s, klib88.s, proc.c, tty.c...)
│       ├── mm/            # memory manager
│       ├── fs/            # file system
│       ├── lib/           # C library
│       └── commands/      # userland (init, sh, ls, ...)
└── port/                  # IIGS port
    ├── boot/
    │   └── bootblock.s    # ProDOS 8 boot block (assembles for org $0800)
    ├── kernel/            # 65816 kernel: startup, console, int, scheduler (WIP)
    │   ├── startup.s      # zpage storage, native-mode entry
    │   ├── main.c         # kmain
    │   ├── console.c      # 80-col text via far pointers, ALT-charset glyph map
    │   ├── int.c/intentry.s   # VBL IRQ entry, timer (revalidation pending)
    │   └── ...
    ├── tools/             # mkdisk.py + gs2* debug probes for GSSquared
    ├── link.ld            # linker script (bank $02)
    └── Makefile           # build
```

## Building & running

Requires the mac-built toolchain (`VBCC=/Users/sah/6502/vbcc65816-mac`, vasm,
vlink — see AGENTS.md), then:

```sh
cd port
make                    # builds bootblock.bin + kernel.raw, packs minixgs.po
```

`make minixgs.po` produces an 800K disk image: block 0 is the custom ProDOS
boot block, blocks 1..N the raw kernel. Boot it in **GSSquared** (which maps
the image into slot 5) and the kernel prints its banner in 80-column text.

On success the machine shows the classic:

```
Minix GS M1: scheduler bring-up
tasks: clock, A, B -- round robin @ 6 ticks
```

The scheduler's clock tick comes from the VBL interrupt; that path is being
revalidated on the stock emulator (see AGENTS.md).

## Credits

- **Idea:** Sean Stein
- **vbcc 65816 toolchain:** Volker Barthelmann
- **GSSquared emulator:** [JawaidBazyar2](https://github.com/jawaidbazyar2) — the 65816 Apple IIgs emulator used for all bring-up testing

## References

- Minix 1.2 source: `old-minix-1.2/` (1987 Prentice-Hall book edition)
- vbcc 65816: <http://www.compilers.de/vbcc.html>
- vasm/vlink: <http://sun.hasenbraten.de/~frank/projects/>
- 65816 Minix discussion: <https://6502.org/forum/viewtopic.php?t=6536>
- Apple IIgs hardware refs: Apple IIgs Technical Reference, 2nd ed.
- GSplus emulator: <https://github.com/kevtris/GSplus>
- GSSquared emulator: <https://github.com/jawaidbazyar2/gssquared>
