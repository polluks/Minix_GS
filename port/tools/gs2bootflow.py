#!/usr/bin/env python3
"""Boot-flow test with CURRENT bootblock addresses (0839 ret / 085C done / 0877 err / 020100 kernel)."""
import os, socket, struct, subprocess, sys, time

APP = os.environ.get("GS2_BIN") or os.path.expandvars(
    "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared")
SOCK = "/tmp/gs2debug.sock"


def frame(t, s, p=b""):
    return struct.pack("<III", t, s, len(p)) + p


def rx(s, n):
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c:
            raise IOError("closed")
        d += c
    return d


def rf(s):
    t, q, l = struct.unpack("<III", rx(s, 12))
    return t, q, rx(s, l) if l else b""


def main():
    image = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "build/minixgs.po")
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
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
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(15)
        s.connect(SOCK)
        state = {"q": 1, "pend": []}

        def req(t, p=b""):
            q = state["q"]; state["q"] = q + 1
            s.sendall(frame(t, q, p))
            while True:
                r, rq, rd = rf(s)
                if r == 0x04:
                    state["pend"].append(rd)
                    continue
                return rd

        def next_event(timeout=3):
            if state["pend"]:
                return state["pend"].pop(0)
            s.settimeout(timeout)
            r, rq, rd = rf(s)
            if r == 0x04:
                return rd
            raise IOError("expected EVENT, got %#x" % r)

        def bp(addr, dom=0):
            return req(0x401, struct.pack("<BBBBIIIIIII", 1, 1, 0, 0, dom, addr,
                                          1, 0xFFFFFFFF, 0, 0xFF, 0))

        req(0x01, struct.pack("<II", 1, 0))
        for a, nm in ((0x0833, "read-ret"), (0x0841, "done_load"), (0x0874, "boot_err"),
                      (0x020100, "kernel")):
            bid = bp(a, 4 if a == 0x020100 else 0)
            print("bp %-10s %06X -> id %d" % (nm, a, struct.unpack("<I", bid)[0]))
        req(0x102, struct.pack("<I", 0))
        print("RESET sent; watching 150s...")
        deadline = time.time() + dur
        n = 0
        while time.time() < deadline:
            try:
                ev = next_event(3)
            except socket.timeout:
                continue
            eid = struct.unpack("<I", ev[:4])[0]
            if eid != 1:
                print("EVENT id=%d" % eid)
                continue
            reason, bid = struct.unpack("<II", ev[4:12])
            pc = struct.unpack("<I", ev[12:16])[0]
            t = ev[32:32+40]
            p, db, pb = t[13], t[14], t[15]
            pcw, a, x, y, sp = struct.unpack("<HHHHH", t[16:26])
            print("[%s] bp%d hitpc=%06X pb=%02X pc=%04X a=%04X x=%04X y=%04X sp=%04X p=%02X"
                  % (time.strftime("%M:%S"), bid, pc, pb, pcw, a, x, y, sp, p))
            n += 1
            if pc == 0x020100:
                m = req(0x301, struct.pack("<III", 4, 0x20000, 0x40))
                print("   bank02:$0000:", m[:32].hex())
                m = req(0x301, struct.pack("<III", 0, 0x0C00, 0x200))
                print("   stag0C00:", m[:16].hex(), "...")
            req(0x104)
        print("total stops:", n)
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass


if __name__ == "__main__":
    main()
