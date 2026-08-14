#!/usr/bin/env python3
"""Inspect CPU state + slot-5 SmartPort ROM while GSSquared boots Minix GS."""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared"
)
SOCK = "/tmp/gs2debug.sock"
HELLO, ERROR, QUIT = 0x01, 0x03, 0x05
GET_STATUS, PAUSE, CONTINUE = 0x101, 0x103, 0x104
GET_REGS = 0x202
READMEM = 0x301
DOM_MAIN = 0


def frame(t, s, p=b""):
    return struct.pack("<III", t, s, len(p)) + p


def recv_exact(s, n):
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c:
            raise IOError("closed")
        d += c
    return d


def read_frame(s):
    t, q, ln = struct.unpack("<III", recv_exact(s, 12))
    return t, q, recv_exact(s, ln) if ln else b""


class GS2:
    def __init__(self, path):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(20)
        self.s.connect(path)
        self.q = 1

    def req(self, t, p=b""):
        q = self.q; self.q += 1
        self.s.sendall(frame(t, q, p))
        r, rq, rd = read_frame(self.s)
        if r == ERROR:
            raise IOError("ERROR seq%d: %r" % (rq, rd))
        return rd

    def regs(self):
        d = self.req(GET_REGS)  # 40-byte trace layout
        opcode = d[12]; p = d[13]; db = d[14]; pb = d[15]
        pc, a, x, y, sp, dp = struct.unpack("<HHHHHH", d[16:28])
        return dict(opcode=opcode, p=p, db=db, pb=pb, pc=pc, a=a, x=x, y=y, sp=sp, d=dp)

    def read(self, dom, a, n):
        return self.req(READMEM, struct.pack("<III", dom, a, n))


def main():
    image = os.path.abspath("build/minixgs.po")
    for p in (SOCK,):
        try: os.unlink(p)
        except FileNotFoundError: pass
    proc = subprocess.Popen([APP, "-p", "5", "-ds5d1=" + image, "-D", SOCK,
                             "--no-quit-confirm"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            if os.path.exists(SOCK): break
            if proc.poll() is not None:
                sys.exit("early exit")
            time.sleep(0.5)
        else:
            sys.exit("no socket")
        gs = GS2(SOCK)
        gs.req(HELLO, struct.pack("<II", 1, 0))
        rom = gs.read(DOM_MAIN, 0xC500, 0x110)
        print("$C500-$C50F:", rom[:16].hex())
        print("$C50D: %02X  $C5FF: %02X (expect 0A)" % (rom[0x0D], rom[0xFF]))
        for i in range(6):
            r = gs.regs()
            print("t%02d %02X:%04X p=%02X E=%d db=%02X op=%02X sp=%04X d=%04X a=%04X x=%04X y=%04X"
                  % (i, r['pb'], r['pc'], r['p'], r['p'] >> 5 & 1, r['db'], r['opcode'],
                     r['sp'], r['d'], r['a'], r['x'], r['y']))
            if i == 2:
                bb = gs.read(DOM_MAIN, 0x2000, 16)
                print("boot block @$2000:", bb.hex())
            time.sleep(1)
        gs.req(QUIT)
    finally:
        time.sleep(0.5)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
