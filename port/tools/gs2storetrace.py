#!/usr/bin/env python3
"""Boot, let kernel run, then GET_TRACE and show store eaddrs (esp text-page far stores)."""
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
        req(0x102, struct.pack("<I", 0))
        while True:
            ev = next_event(120)
            if struct.unpack("<I", ev[:4])[0] != 1: continue
            reason, b = struct.unpack("<II", ev[4:12])
            if b == bid: break
        req(0x104)
        time.sleep(wait)
        tr = req(0x201, struct.pack("<II", 0, 8192))
        returned = struct.unpack("<I", tr[4:8])[0]
        print("trace returned", returned)
        stores = []
        for i in range(returned):
            e = tr[8 + i * 40:8 + (i + 1) * 40]
            opcode = e[12]; pb = e[15]; pc = struct.unpack("<H", e[16:18])[0]
            eaddr = struct.unpack("<I", e[30:34])[0]
            data = struct.unpack("<H", e[28:30])[0]
            f_write = (e[34] >> 4) & 1
            f_data_sz = (e[34] >> 3) & 1
            if f_write:
                stores.append((pb, pc, opcode, eaddr, data))
        print("stores:", len(stores))
        # classify by eaddr bank
        from collections import Counter
        banks = Counter(a >> 16 for _, _, _, a, _ in stores)
        print("store banks:", dict(banks))
        for st in stores[:30]:
            print("  write PB:%02X PC:%04X op=%02X eaddr=%06X data=%02X" % st)
        # find text-page stores (eaddr in 0400..07ff or 010400..0107ff)
        tp = [st for st in stores if ((st[3] & 0xFFFF) >= 0x0400 and (st[3] & 0xFFFF) <= 0x07FF)]
        print("text-page stores:", len(tp))
        for st in tp[:20]:
            print("  TP write PB:%02X PC:%04X op=%02X eaddr=%06X data=%02X" % st)
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass

main()
