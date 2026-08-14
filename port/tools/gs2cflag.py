#!/usr/bin/env python3
"""BP after the SmartPort call ($080E bcs) and at boot_err ($083C); watch C flag."""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared")
SOCK = "/tmp/gs2debug.sock"
HELLO, ERROR, QUIT, EVENT = 0x01, 0x03, 0x05, 0x04
GET_REGS, CONTINUE, RESET = 0x202, 0x104, 0x102
BP_SET = 0x401
READMEM = 0x301
DOM_MAIN, DOM_RAW = 0, 4


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
        self.pending = []

    def req(self, t, p=b""):
        q = self.q; self.q += 1
        self.s.sendall(frame(t, q, p))
        while True:
            r, rq, rd = read_frame(self.s)
            if r == EVENT:
                self.pending.append(rd)
                continue
            if r == ERROR:
                raise IOError("ERROR seq%d: %r" % (rq, rd))
            return rd

    def next_event(self, timeout=5):
        if self.pending:
            return self.pending.pop(0)
        self.s.settimeout(timeout)
        r, rq, rd = read_frame(self.s)
        if r == EVENT:
            return rd
        raise IOError("expected EVENT, got %#x" % r)

    def regs(self):
        d = self.req(GET_REGS)
        p = d[13]; db = d[14]; pb = d[15]
        pc, a, x, y, sp, dp = struct.unpack("<HHHHHH", d[16:28])
        return dict(pb=pb, pc=pc, p=p, db=db, a=a, x=x, y=y, sp=sp, d=dp)

    def bp(self, addr, kind=1, dom=0):
        p = struct.pack("<BBBBIIIIIII", kind, 1, 0, 0, dom, addr,
                        1, 0xFFFFFFFF, 0, 0xFF, 0)
        return self.req(BP_SET, p)

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
        gs.bp(0x080E)   # bcs boot_err (right after SmartPort return)
        gs.bp(0x083C)   # boot_err
        gs.req(RESET, struct.pack("<I", 0))
        print("RESET sent")
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                ev = gs.next_event(2)
            except socket.timeout:
                continue
            eid = struct.unpack("<I", ev[:4])[0]
            if eid == 1:
                r = gs.regs()
                c = r['p'] & 1
                mark = "C=1->boot_err" if r['pc'] == 0x083C else (
                    "C=%d->read %s" % (c, "FAIL" if c else "OK"))
                print("STOP %02X:%04X p=%02X C=%d a=%04X x=%04X y=%04X  [%s]"
                      % (r['pb'], r['pc'], r['p'], c, r['a'], r['x'], r['y'], mark))
                b2 = gs.read(0x20000, 16, DOM_RAW)
                print("   bank02:0000: %s" % b2.hex(" "))
                pl = gs.read(0x083F, 12)
                print("   parlist:    %s" % pl.hex(" "))
                gs.req(CONTINUE)
            else:
                print("EVENT id=%d" % eid)
        gs.req(QUIT)
    finally:
        time.sleep(0.5)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
