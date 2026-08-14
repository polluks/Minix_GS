#!/usr/bin/env python3
"""After boot attempt, dump kernel memory ($02:0000) and CPU state."""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared"
)
SOCK = "/tmp/gs2debug.sock"
HELLO, ERROR, QUIT = 0x01, 0x03, 0x05
GET_STATUS, GET_REGS = 0x101, 0x202
READMEM = 0x301
DOM_RAW = 4  # MAIN_RAW: IIgs FPI physical RAM, bank * 0x10000 + offset


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
        while True:
            r, rq, rd = read_frame(self.s)
            if r == ERROR:
                raise IOError("ERROR %r" % rd)
            return rd

    def regs(self):
        d = self.req(GET_REGS)
        p = d[13]; db = d[14]; pb = d[15]
        pc, a, x, y, sp, dp = struct.unpack("<HHHHHH", d[16:28])
        return dict(pb=pb, pc=pc, p=p, db=db, a=a, x=x, y=y, sp=sp, d=dp)

    def read(self, a, n, dom=0):
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
        gs = GS2(SOCK)
        gs.req(HELLO, struct.pack("<II", 1, 0))
        time.sleep(6)
        r = gs.regs()
        print("REGS pb=%02X pc=%04X p=%02X db=%02X sp=%04X a=%04X x=%04X y=%04X d=%04X"
              % (r['pb'], r['pc'], r['p'], r['db'], r['sp'], r['a'], r['x'], r['y'], r['d']))
        mem = gs.read(0x20000, 0x80, DOM_RAW)
        print("bank02:0000: %s" % mem.hex())
        mem = gs.read(0x20100, 0x40, DOM_RAW)
        print("bank02:0100: %s" % mem.hex())
        mem = gs.read(0x0800, 64)
        print("bank00:0800: %s" % mem.hex())
        gs.req(QUIT)
    finally:
        time.sleep(0.5)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
