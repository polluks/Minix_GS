#!/usr/bin/env python3
"""Instrument the SmartPort/IWM driver for sys6 vs minixgs and diff the flow.

BPs:
  FF:6AEB  block-device driver entry
  FF:6AF9  SmartPort handshake (LDA >$0006FD)
  FF:6B16  E10FB0 status check
  00:6E8F  JSL target (bank-0 driver)
  00:C628  slot firmware: LDX $2B
  00:C62E  direct IWM read
  00:C65E  IWM sync poll
  DATA W  $C031 (DISKREG)
Logs every stop: reason/pc/eaddr/value + A/X/Y/SP/P.
Also dumps the SmartPort regs + zpage on the 6AF9 stop.
"""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared")
SOCK = "/tmp/gs2debug.sock"
HELLO, ERROR, QUIT, EVENT = 0x01, 0x03, 0x05, 0x04
GET_REGS, CONTINUE, RESET = 0x202, 0x104, 0x102
BP_SET = 0x401
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

    def bp(self, addr, kind=1, access=0, flags=1, length=1,
           dmask=0xFF, dval=0, ignore=0):
        p = struct.pack("<BBBBIIIIIII", kind, flags, access, 0, DOM_MAIN,
                        addr, length, 0xFFFFFFFF, dval, dmask, ignore)
        return self.req(BP_SET, p)

    def read(self, a, n, dom=0):
        return self.req(READMEM, struct.pack("<III", dom, a, n))

    def regs(self):
        d = self.req(GET_REGS)
        p = d[13]; db = d[14]; pb = d[15]
        pc, a, x, y, sp, dp = struct.unpack("<HHHHHH", d[16:28])
        return dict(pb=pb, pc=pc, p=p, db=db, a=a, x=x, y=y, sp=sp, d=dp)


def trace_fields(ev):
    t = ev[32:32+40]
    cycle = struct.unpack("<Q", t[0:8])[0]
    operand = struct.unpack("<I", t[8:12])[0]
    opcode = t[12]
    p, db, pb = t[13], t[14], t[15]
    pc, a, x, y, sp, d, data = struct.unpack("<HHHHHHH", t[16:30])
    eaddr = struct.unpack("<I", t[30:34])[0]
    flags = struct.unpack("<H", t[34:36])[0]
    return dict(pb=pb, pc=pc, a=a, x=x, y=y, sp=sp, p=p, db=db, d=d,
                eaddr=eaddr, data=data, opcode=opcode, flags=flags,
                cycle=cycle)


def main():
    image = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "build/minixgs.po")
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 70.0
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
        ids = {}
        for name, addr in (("6AEB", 0xFF6AEB), ("6AF9", 0xFF6AF9),
                           ("6B16", 0xFF6B16), ("6E8F", 0x006E8F),
                           ("C628", 0x00C628), ("C62E", 0x00C62E),
                           ("C65E", 0x00C65E)):
            ids[name] = gs.bp(addr)
        ids["C031w"] = gs.bp(0x00C031, kind=2, access=2, length=1)
        print("bps:", {k: v for k, v in ids.items()})
        gs.req(RESET, struct.pack("<I", 0))
        print("RESET sent")
        name_by_id = {v: k for k, v in ids.items()}
        deadline = time.time() + dur
        stops = 0
        while time.time() < deadline:
            try:
                ev = gs.next_event(3)
            except socket.timeout:
                print("  (timeout waiting)")
                continue
            eid = struct.unpack("<I", ev[:4])[0]
            if eid == 1:
                reason, bid = struct.unpack("<II", ev[4:12])
                pc, eaddr, value = struct.unpack("<III", ev[12:24])
                access = ev[24]; kind = ev[25]
                tr = trace_fields(ev)
                who = name_by_id.get(bid, "?%d" % bid)
                r = gs.regs()
                print("[%s] %-6s hitpc=%06X pb=%02X pc=%04X a=%04X x=%04X y=%04X "
                      "sp=%04X p=%02X db=%02X eaddr=%06X v=%02X"
                      % (time.strftime("%M:%S"), who, pc, r['pb'], r['pc'],
                         r['a'], r['x'], r['y'], r['sp'], r['p'], r['db'],
                         eaddr, value))
                if who == "6AF9":
                    m = gs.read(0x0006FD, 4)
                    e = gs.read(0xE10FB6, 2)
                    f = gs.read(0xE10FB0, 1)
                    z = gs.read(0x42, 12)
                    print("    $06FD=%02X $06FE=%02X $06FF=%02X $E10FB6=%02X $E10FB7=%02X $E10FB0=%02X"
                          % (m[0], m[1], m[2], e[0], e[1], f[0]))
                    print("    z42..4D: %s" % " ".join("%02X" % b for b in z))
                gs.req(CONTINUE)
                stops += 1
                if stops > 6000:
                    print("stop cap reached")
                    break
            else:
                print("EVENT id=%d len=%d" % (eid, len(ev)))
        print("total stops: %d" % stops)
        gs.req(QUIT)
    finally:
        time.sleep(0.5)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
