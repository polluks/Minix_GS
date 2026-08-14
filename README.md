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
| INT 0x21-ish syscalls  | COP / custom trap           |
| 8259 PIC               | 6522 VIAs + IWM/Mega II IRQ |
| 8253 timer             | VIA2 timer 1                |
| 6845 MDA/CGA text      | VGC 80-col text mode        |
| PC keyboard + BIOS     | ADB keyboard                |
| floppy + ST-506/IDE    | SmartPort (3.5" floppy, RAM, ProDOS devices) |

## Status

Work in progress. Nothing boots yet — this is being brought up bottom-up.

- [x] vbcc 65816 toolchain built for macOS arm64 (compiler + `dtgen`)
- [x] 65816 data model generated (`dt.h`: 16-bit `int`, 32-bit `long`, 64-bit `long long`, 16-bit near pointer)
- [ ] vasm 65816 + vlink built for macOS
- [ ] Toolchain smoke test (IIgs hello world)
- [ ] Boot loader / raw block-0 bootstrap
- [ ] Kernel bring-up: 65816 startup, vectors, context switch
- [ ] VIA2 timer + interrupt dispatch
- [ ] Console driver (VGC 80-column text mode)
- [ ] ADB keyboard driver
- [ ] SmartPort block device driver
- [ ] `kernel`, `mm`, `fs` processes and IPC
- [ ] `init`, shell, basic commands
- [ ] Bootable ProDOS/SmartPort image tested under GSplus

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
├── old-minix-1.2/         # Minix 1.2 sources (reference; unchanged)
│   ├── include/           # public headers
│   └── src/
│       ├── kernel/        # microkernel (mpx88.s, klib88.s, proc.c, tty.c...)
│       ├── mm/            # memory manager
│       ├── fs/            # file system
│       ├── lib/           # C library
│       └── commands/      # userland (init, sh, ls, ...)
├── port/                  # IIGS-specific port code (planned)
│   ├── boot/              # boot block, loader
│   ├── kernel/            # 65816 startup/vectors, mpx816.s, klib816.s
│   ├── drivers/           # console, keyboard, smartport, timer
│   └── tools/             # build scripts, dtgen answers, image tooling
└── tools/                 # cross-build makefiles
```

## Building & running

(Not yet working — placeholder until the toolchain smoke test passes.)

The goal is a bootable raw image loadable by GSplus/MAME (and burnable to a
3.5" disk / FlashRAM) that boots straight into Minix and prints the classic:

```
MINIX 1.2 -- Copyright 1987 Prentice-Hall, Inc.
```

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
