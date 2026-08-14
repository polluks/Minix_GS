#!/usr/bin/env python3
"""Full banner check: after kernel runs, dump main/aux text pages + VIDEO_TEXT all modes + regs."""
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
        def rdmem(dom, addr, n): return req(0x301, struct.pack("<III", dom, addr, n))[:n]
        req(0x01, struct.pack("<II", 1, 0))
        bid = req(0x401, struct.pack("<BBBBIIIIIII", 1, 1, 0, 0, 0, 0x020100, 1, 0xFFFFFFFF, 0, 0xFF, 0))
        bid = struct.unpack("<I", bid)[0]
        req(0x102, struct.pack("<I", 0))
        while True:
            ev = next_event(120)
            if struct.unpack("<I", ev[:4])[0] != 1: continue
            reason, b = struct.unpack("<II", ev[4:12])
            if b == bid: break
        req(0x104)
        time.sleep(wait)
        regs = req(0x202)
        print("regs: PB:%02X PC:%04X A:%04X X:%04X Y:%04X SP:%04X D:%04X DB:%02X P:%02X" % (
            regs[15], struct.unpack("<H", regs[16:18])[0], struct.unpack("<H", regs[18:20])[0],
            struct.unpack("<H", regs[20:22])[0], struct.unpack("<H", regs[22:24])[0],
            struct.unpack("<H", regs[24:26])[0], struct.unpack("<H", regs[26:28])[0],
            regs[14], regs[13]))
        m = rdmem(0, 0x0400, 0x400)
        a = rdmem(0, 0x010400, 0x400)
        def show(name, d):
            nonascii = sum(1 for b in d if not (32 <= b < 127))
            print("%s: first64 %s" % (name, d[:64].hex()))
            print("   printable: %r ... last32 %s" % (d[:64], d[-32:].hex()))
        show("main $0400", m)
        show("aux  $010400", a)
        for mode in (0, 1, 2):
            r = req(0x701, struct.pack("<II", 0, mode))
            if len(r) < 20: continue
            cols, rows, page, got_mode, flags = struct.unpack("<IIIII", r[:20])
            chars = r[20:]
            print("== VIDEO mode=%d (req %d) page=%d cols=%d rows=%d flags=%08X ==" % (got_mode, mode, page, cols, rows, flags))
            for i in range(min(rows, 24)):
                line = chars[i * cols:(i + 1) * cols]
                print("%02d: %r" % (i, line.decode("latin1")))
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass

main()
