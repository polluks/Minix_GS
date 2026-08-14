#!/usr/bin/env python3
"""Verify the VBL timer: set a breakpoint on _irq_handler, run, and confirm
the IRQ fires (handler hit) and jiffies counts up; also dump the 80-col text."""
import os, socket, struct, subprocess, sys, time

APP = os.path.expandvars("$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared")
SOCK = "/tmp/gs2debug.sock"
IRQ_HANDLER = 0x0202E7   # _irq_handler
JIFFIES     = 0x020474   # _jiffies (bank 2)

def frame(t, s, p=b""): return struct.pack("<III", t, s, len(p)) + p
def rx(s, n):
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c: raise IOError("closed")
        d += c
    return d
def rf(s):
    t, q, l = struct.unpack("<III", rx(s, 12))
    return t, q, rx(s, l) if l else b""

def main():
    image = os.path.abspath(sys.argv[1])
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    for p in (SOCK,):
        try: os.unlink(p)
        except FileNotFoundError: pass
    proc = subprocess.Popen([APP, "-p", "5", "-ds5d1=" + image, "-D", SOCK, "--no-quit-confirm"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            if os.path.exists(SOCK): break
            time.sleep(0.5)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10); s.connect(SOCK)
        state = {"q": 1, "pend": []}
        def req(t, p=b""):
            q = state["q"]; state["q"] = q + 1
            s.sendall(frame(t, q, p))
            while True:
                r, rq, rd = rf(s)
                if r == 0x04:
                    state["pend"].append(rd); continue
                return rd
        def next_event(timeout=2):
            if state["pend"]: return state["pend"].pop(0)
            s.settimeout(timeout)
            r, rq, rd = rf(s)
            if r == 0x04: return rd
            raise IOError("not event")
        def rdmem(dom, addr, n): return req(0x301, struct.pack("<III", dom, addr, n))[:n]
        def rd16(dom, addr): return struct.unpack("<H", rdmem(dom, addr, 2))[0]

        req(0x01, struct.pack("<II", 1, 0))
        bid = req(0x401, struct.pack("<BBBBIIIIIII", 1, 1, 0, 0, 0, IRQ_HANDLER, 1, 0xFFFFFFFF, 0, 0xFF, 0))
        bid = struct.unpack("<I", bid)[0]
        print("irq_handler bp id", bid)
        req(0x102, struct.pack("<I", 0))
        # wait for the first IRQ-handler hit
        got = None
        deadline = time.time() + wait
        while time.time() < deadline:
            try:
                ev = next_event(2)
            except IOError:
                continue
            if struct.unpack("<I", ev[:4])[0] != 1: continue
            reason, b = struct.unpack("<II", ev[4:12])
            if b == bid:
                got = time.time()
                break
        if got is None:
            print("TIMEOUT: _irq_handler never hit -- VBL interrupt did not fire")
        else:
            print("IRQ fired after %.2fs: _irq_handler hit" % (got - (time.time() - wait)))
            print("jiffies at first hit:", rd16(4, JIFFIES))
            time.sleep(1.0)
            print("jiffies +1s:        ", rd16(4, JIFFIES))
        # still show the banner
        r = req(0x701, struct.pack("<II", 0, 2))
        if len(r) >= 20:
            cols, rows, page, got_mode, flags = struct.unpack("<IIIII", r[:20])
            chars = r[20:]
            print("== VIDEO mode=%d page=%d %dx%d ==" % (got_mode, page, cols, rows))
            for y in range(rows):
                print("%02d: %r" % (y, chars[y*cols:(y+1)*cols]))
        req(0x05)
    finally:
        proc.terminate()

if __name__ == "__main__":
    main()
