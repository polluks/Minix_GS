#!/usr/bin/env python3
"""Boot minixgs.po, wait for kernel bp, let it run, dump main+aux text pages."""
import os, socket, struct, subprocess, sys, time

APP = os.path.expandvars("$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared")
SOCK = "/tmp/gs2debug.sock"

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

ROWS = [0x00, 0x80, 0x100, 0x180, 0x200, 0x280, 0x300, 0x380,
        0x28, 0xA8, 0x128, 0x1A8, 0x228, 0x2A8, 0x328, 0x3A8,
        0x50, 0xD0, 0x150, 0x1D0, 0x250, 0x2D0, 0x350, 0x3D0]

def main():
    image = os.path.abspath(sys.argv[1])
    run_after = float(sys.argv[2]) if len(sys.argv) > 2 else 12
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
        req(0x01, struct.pack("<II", 1, 0))
        bid = req(0x401, struct.pack("<BBBBIIIIIII", 1, 1, 0, 0, 0, 0x020100, 1, 0xFFFFFFFF, 0, 0xFF, 0))
        print("kernel bp id", struct.unpack("<I", bid)[0])
        req(0x102, struct.pack("<I", 0))
        while True:
            ev = next_event(60)
            if struct.unpack("<I", ev[:4])[0] != 1: continue
            reason, b = struct.unpack("<II", ev[4:12])
            if b == struct.unpack("<I", bid)[0]: break
        print("kernel reached; running %.0fs..." % run_after)
        req(0x104)
        time.sleep(run_after)
        m = req(0x301, struct.pack("<III", 0, 0x0400, 0x400))
        a = req(0x301, struct.pack("<III", 0, 0x010400, 0x400))
        def show(buf, label):
            print("== %s ==" % label)
            for r in range(24):
                o = ROWS[r]
                line = bytes(buf[o + c] for c in range(40))
                print("%02d: %s" % (r, line.decode("latin1")))
        show(m, "main $0400")
        show(a, "aux  $010400")
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass

main()
