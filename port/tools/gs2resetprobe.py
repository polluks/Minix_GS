#!/usr/bin/env python3
"""Set SmartPort breakpoints, then RESET to force a fresh boot; watch for hits."""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared"
)
SOCK = "/tmp/gs2debug.sock"
HELLO, ERROR, QUIT, EVENT = 0x01, 0x03, 0x05, 0x04
GET_STATUS, CONTINUE, PAUSE, RESET = 0x101, 0x104, 0x103, 0x102
GET_REGS = 0x202
BP_SET, BP_CLEAR_ALL = 0x401, 0x403
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

    def bp(self, addr, kind=1):
        p = struct.pack("<BBBBIIIIIII", kind, 1, 0, 0, DOM_MAIN, addr,
                        1, 0xFFFFFFFF, 0, 0xFF, 0)
        return self.req(BP_SET, p)

    def read(self, a, n):
        return self.req(READMEM, struct.pack("<III", DOM_MAIN, a, n))


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
        b1 = gs.bp(0xC50D)
        b2 = gs.bp(0xC50A)
        print("bps:", b1, b2)
        gs.req(RESET, struct.pack("<I", 0))   # warm reset, breakpoints survive
        print("RESET sent")
        hits = 0
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                ev = gs.next_event(2)
            except socket.timeout:
                continue
            eid = struct.unpack("<I", ev[:4])[0]
            if eid == 1:
                r = gs.regs()
                hits += 1
                print("STOP %02X:%04X p=%02X sp=%04X a=%04X x=%04X y=%04X"
                      % (r['pb'], r['pc'], r['p'], r['sp'], r['a'], r['x'], r['y']))
                stack = gs.read(0x100 + (r['sp'] & 0xFF), 12)
                print("   stack: %s" % stack.hex())
                ra = struct.unpack("<H", stack[:2])[0]
                print("   call-site @%04X: %s" % (ra, gs.read(ra, 24).hex()))
                gs.req(CONTINUE)
            else:
                print("EVENT id=%d len=%d" % (eid, len(ev)))
        print("hits=%d" % hits)
        gs.req(QUIT)
    finally:
        time.sleep(0.5)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
