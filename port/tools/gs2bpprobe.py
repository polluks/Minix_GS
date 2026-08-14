#!/usr/bin/env python3
"""Watch for the firmware boot path calling the slot-5 SmartPort dispatch."""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared"
)
SOCK = "/tmp/gs2debug.sock"
HELLO, ERROR, QUIT, EVENT = 0x01, 0x03, 0x05, 0x04
GET_STATUS, CONTINUE, PAUSE = 0x101, 0x104, 0x103
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

    def wait_event(self, timeout=10):
        self.s.settimeout(timeout)
        while True:
            r, rq, rd = read_frame(self.s)
            if r == EVENT:
                return rd
            if r == ERROR:
                raise IOError("ERROR %r" % rd)

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
        gs.pending = []
        gs.req(HELLO, struct.pack("<II", 1, 0))
        time.sleep(4)
        b1 = gs.bp(0xC50D)
        b2 = gs.bp(0xC50A)
        print("bps:", b1, b2)
        hits = []
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                ev = gs.wait_event(2)
            except socket.timeout:
                print("... no event (running)")
                continue
            eid = struct.unpack("<I", ev[:4])[0]
            print("EVENT id=%d" % eid)
            if eid == 1:  # EVT_STOPPED
                r = gs.regs()
                print("STOPPED at %02X:%04X p=%02X sp=%04X a=%04X x=%04X y=%04X"
                      % (r['pb'], r['pc'], r['p'], r['sp'], r['a'], r['x'], r['y']))
                stack = gs.read(0x100 + r['sp'], 16)
                print("  stack:", stack.hex())
                hits.append(r)
                gs.req(CONTINUE)
                if len(hits) >= 6:
                    break
        print("done, %d SmartPort calls observed" % len(hits))
        gs.req(QUIT)
    finally:
        time.sleep(0.5)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
