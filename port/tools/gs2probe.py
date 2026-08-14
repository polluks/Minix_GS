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
    dur = float(sys.argv[2])
    bplist = [(int(a,16), nm, dom) for a, nm, dom in
              (x.split(",") for x in sys.argv[3:])]
    for p in (SOCK,):
        try: os.unlink(p)
        except FileNotFoundError: pass
    proc = subprocess.Popen([APP, "-p", "5", "-ds5d1=" + image, "-D", SOCK, "--no-quit-confirm"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            if os.path.exists(SOCK): break
            if proc.poll() is not None: sys.exit("early exit")
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
        def next_event(timeout=3):
            if state["pend"]: return state["pend"].pop(0)
            s.settimeout(timeout)
            r, rq, rd = rf(s)
            if r == 0x04: return rd
            raise IOError("not event")
        req(0x01, struct.pack("<II", 1, 0))
        for a, nm, dom in bplist:
            bid = req(0x401, struct.pack("<BBBBIIIIIII", 1, 1, 0, 0, int(dom), a, 1, 0xFFFFFFFF, 0, 0xFF, 0))
            print("bp %-10s %06X -> %d" % (nm, a, struct.unpack("<I", bid)[0]))
        req(0x102, struct.pack("<I", 0))
        deadline = time.time() + dur
        n = 0
        while time.time() < deadline:
            try:
                ev = next_event(3)
            except socket.timeout:
                continue
            eid = struct.unpack("<I", ev[:4])[0]
            if eid != 1: continue
            reason, bid = struct.unpack("<II", ev[4:12])
            pc = struct.unpack("<I", ev[12:16])[0]
            m = req(0x301, struct.pack("<III", 0, 0x0C00, 0x40))
            print("[%s] bp%d hitpc=%06X  $0C00: %s" % (time.strftime("%M:%S"), bid, pc, m[:40].hex()))
            n += 1
            req(0x104)
        print("stops:", n)
        req(0x05)
    finally:
        time.sleep(0.3)
        try: proc.terminate()
        except ProcessLookupError: pass

main()
