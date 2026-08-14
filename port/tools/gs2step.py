#!/usr/bin/env python3
"""STEP_INTO through the SmartPort call from the boot block's JSR."""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared")
SOCK = "/tmp/gs2debug.sock"
HELLO, ERROR, QUIT, EVENT = 0x01, 0x03, 0x05, 0x04
GET_REGS, CONTINUE, RESET, STEP = 0x202, 0x104, 0x102, 0x105
BP_SET, BP_CLEAR_ALL = 0x401, 0x403
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
        gs.bp(0x0806)   # our jsr $C50D
        gs.req(RESET, struct.pack("<I", 0))
        # wait for first stop at 0806
        for _ in range(60):
            try:
                ev = gs.next_event(2)
            except socket.timeout:
                continue
            eid = struct.unpack("<I", ev[:4])[0]
            if eid == 1:
                r = gs.regs()
                if r['pc'] == 0x0806 and r['pb'] == 0:
                    break
                gs.req(CONTINUE)
        print("at jsr $C50D")
        steps = []
        for i in range(400):
            gs.req(STEP, struct.pack("<I", 1))
            try:
                ev = gs.next_event(5)
            except socket.timeout:
                print("timeout at step %d" % i)
                break
            if struct.unpack("<I", ev[:4])[0] != 1:
                continue
            r = gs.regs()
            steps.append(r)
            if len(steps) % 20 == 0:
                print("  step %d: pb=%02X pc=%04X p=%02X a=%04X x=%04X y=%04X sp=%04X"
                      % (i, r['pb'], r['pc'], r['p'], r['a'], r['x'], r['y'], r['sp']))
            if r['pc'] == 0x083C and r['pb'] == 0:
                print("reached boot_err at step %d" % i)
                break
        print("total steps recorded: %d" % len(steps))
        for r in steps:
            print("%04X %02X p=%02X a=%04X x=%04X y=%04X sp=%04X db=%02X"
                  % (r['pc'], r['pb'], r['p'], r['a'], r['x'], r['y'], r['sp'], r['db']))
        gs.req(QUIT)
    finally:
        time.sleep(0.5)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
