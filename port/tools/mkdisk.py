#!/usr/bin/env python3
"""Build a bootable 800K (1600-block) disk image for Minix GS.

Layout: block 0 = custom ProDOS 8 boot block (loaded by the IIgs firmware to
$0800); block 1 unused; blocks 2..N+1 = kernel.raw (the rawbin link of the
bank-$02 kernel, placed at $020000). Kernel starts at block 2 because the
firmware's IWM driver fails to read block 1 in GSSquared (sys6's working boot
also starts at block 2). The boot block's NBLOCKS byte is patched to N.

Usage: mkdisk.py <bootblock.bin> <kernel.raw> <output.po>
"""
import sys

# READ BLOCK param list that the boot block always contains (padding to the
# full form the ROM reads, incl. the block hi/reserved bytes):
#   count=1, unit=1, buffer=$00:0C00, block number=2, res, res
#   ... then the NBLOCKS byte.
SIGNATURE = bytes([0x01, 0x01, 0x00, 0x0C, 0x02, 0x00, 0x00, 0x00, 0x00])


def build(boot_path, kernel_path, out_path):
    boot = bytearray(open(boot_path, 'rb').read())
    if len(boot) > 512:
        sys.exit('boot block too large: %d bytes' % len(boot))
    boot += bytes(512 - len(boot))

    kernel = open(kernel_path, 'rb').read()
    nblocks = (len(kernel) + 511) // 512
    if nblocks == 0:
        sys.exit('kernel image is empty')
    if nblocks > 128:  # bank $02 is 64 KB
        sys.exit('kernel too large: %d bytes (%d blocks)' % (len(kernel), nblocks))

    idx = boot.find(SIGNATURE)
    if idx < 0:
        sys.exit('boot block param-list signature not found')
    boot[idx + len(SIGNATURE)] = nblocks

    padded = kernel + bytes(nblocks * 512 - len(kernel))
    img = bytes(boot) + bytes(512) + padded   # block 0 = boot, block 1 unused
    img += bytes(1600 * 512 - len(img))

    with open(out_path, 'wb') as f:
        f.write(img)
    print('wrote %s (%d blocks kernel, NBLOCKS=%d patched)' %
          (out_path, nblocks, nblocks))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: mkdisk.py <bootblock.bin> <kernel.raw> <output.po>')
    build(sys.argv[1], sys.argv[2], sys.argv[3])
