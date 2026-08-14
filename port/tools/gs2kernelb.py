#!/usr/bin/env python3
"""BP on console_init entry, its main/aux store instructions, and kernel entry."""
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
        bids = {}
        for addr, name in ((0x020100, "kernel"), (0x020156, "console_init"),
                           (0x0201C2, "main_store"), (0x02020D, "aux_store"),
                           (0x020332, "console_puts")):
            b = req(0x401, struct.pack("<BBBBIIIIIII", 1, 1, 0, 0, 0, addr, 1, 0xFFFFFFFF, 0, 0xFF, 0))
            bids[struct.unpack("<I", b)[0]] = name
        req(0x102, struct.pack("<I", 0))
        print("booting...")
        hits = {}
        deadline = time.time() + 180
        while time.time() < deadline and len(hits) < len(bids):
            ev = next_event(20)
            t = struct.unpack("<I", ev[:4])[0]
            if t != 1: continue
            reason, b = struct.unpack("<II", ev[4:12])
            name = bids.get(b, "?")
            pb = ev[15]; pc = struct.unpack("<H", ev[16:18])[0]
            a = struct.unpack("<H", ev[18:20])[0]
            db = ev[14]
            print("HIT %-12s bp=%d PB:%02X PC:%04X A:%04X DB:%02X (reason %d)" % (name, b, pb, pc, a, db, reason))
            hits[name] = hits.get(name, 0) + 1
            req(0x104)
        print("done, hits:", hits)
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass

main()
