#!/usr/bin/env python3
"""Boot minixgs.po, let the kernel run, then read live regs to see where it is."""
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

def main():
    image = os.path.abspath(sys.argv[1])
    wait = float(sys.argv[2]) if len(sys.argv) > 2 else 8
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
        bid = struct.unpack("<I", bid)[0]
        print("kernel bp id", bid)
        req(0x102, struct.pack("<I", 0))
        while True:
            ev = next_event(60)
            if struct.unpack("<I", ev[:4])[0] != 1: continue
            reason, b = struct.unpack("<II", ev[4:12])
            if b == bid: break
        req(0x104)
        time.sleep(wait)
        t = req(0x202)
        pb = t[15]; pc = struct.unpack("<H", t[16:18])[0]
        a = struct.unpack("<H", t[18:20])[0]; x = struct.unpack("<H", t[20:22])[0]
        y = struct.unpack("<H", t[22:24])[0]; sp = struct.unpack("<H", t[24:26])[0]
        d = struct.unpack("<H", t[26:28])[0]; p = t[13]; db = t[14]
        print("PC=%02X:%04X A=%04X X=%04X Y=%04X SP=%04X D=%04X P=%02X DB=%02X" %
              (pb, pc, a, x, y, sp, d, p, db))
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass

main()
