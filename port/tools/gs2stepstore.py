#!/usr/bin/env python3
"""BP on main store $0201C2: read $0400 before, STEP_INTO the store, read after."""
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
        def rdmem(dom, addr, n):
            return req(0x301, struct.pack("<III", dom, addr, n))[:n]
        req(0x01, struct.pack("<II", 1, 0))
        b = req(0x401, struct.pack("<BBBBIIIIIII", 1, 1, 0, 0, 0, 0x0201C2, 1, 0xFFFFFFFF, 0, 0xFF, 0))
        bid = struct.unpack("<I", b)[0]
        req(0x102, struct.pack("<I", 0))
        while True:
            ev = next_event(120)
            if struct.unpack("<I", ev[:4])[0] != 1: continue
            reason, bb = struct.unpack("<II", ev[4:12])
            if bb == bid: break
        regs = req(0x202)
        print("at store: PB:%02X PC:%04X A:%04X DB:%02X P:%02X SP:%04X" % (
            regs[15], struct.unpack("<H", regs[16:18])[0], struct.unpack("<H", regs[18:20])[0],
            regs[14], regs[13], struct.unpack("<H", regs[24:26])[0]))
        b0 = rdmem(0, 0x0400, 8); b1 = rdmem(0, 0x010400, 8)
        print("BEFORE main $0400:", b0.hex(), " aux $010400:", b1.hex())
        req(0x105, struct.pack("<I", 1))
        b0 = rdmem(0, 0x0400, 8); b1 = rdmem(0, 0x010400, 8)
        print("AFTER  main $0400:", b0.hex(), " aux $010400:", b1.hex())
        r2 = req(0x202)
        print("after step: PB:%02X PC:%04X A:%04X P:%02X" % (r2[15], struct.unpack("<H", r2[16:18])[0],
              struct.unpack("<H", r2[18:20])[0], r2[13]))
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass

main()
