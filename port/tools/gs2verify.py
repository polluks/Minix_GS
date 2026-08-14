#!/usr/bin/env python3
"""Boot-test harness for Minix GS on GSSquared.

Launches the GSSquared app with the built disk image mounted as the internal
3.5" drive (slot 5, drive 1), connects over the debug protocol Unix socket,
and reads the 80-column text screen (VIDEO_TEXT) until the Minix GS banner
appears. Usage:

    python3 tools/gs2verify.py [--dry-run] [--timeout 60]

Prints the linearized 80x24 screen and the raw MAIN/aux text-page bytes.
"""
import os
import socket
import struct
import subprocess
import sys
import time

APP = os.environ.get("GS2_BIN") or (
    os.path.expandvars(
        "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared"
    )
    if "TMPDIR" in os.environ
    else "$TMPDIR/opencode/gs2src/build/GSSquared.app/Contents/MacOS/GSSquared"
)
SOCK = "/tmp/gs2debug.sock"
EXPECT = b"Minix GS M1"

HELLO, PING, ERROR, QUIT = 0x01, 0x02, 0x03, 0x05
GET_STATUS, PAUSE, CONTINUE = 0x101, 0x103, 0x104
READMEM = 0x301
VIDEO_TEXT = 0x701

DOMAIN_MAIN_RAW = 5

BANNER1 = b"Minix GS M1: 65816 native, bank 0 I/O reachable\r\n"
BANNER2 = b"kernel in bank $02, 80-col text via far pointers\r\n"


def frame(type_, seq, payload=b""):
    return struct.pack("<III", type_, seq, len(payload)) + payload


def recv_exact(s, n):
    data = b""
    while len(data) < n:
        chunk = s.recv(n - len(data))
        if not chunk:
            raise IOError("socket closed")
        data += chunk
    return data


def read_frame(s):
    t, seq, ln = struct.unpack("<III", recv_exact(s, 12))
    return t, seq, recv_exact(s, ln) if ln else b""


class GS2:
    def __init__(self, path):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(15)
        self.s.connect(path)
        self.seq = 1

    def req(self, type_, payload=b""):
        seq = self.seq
        self.seq += 1
        self.s.sendall(frame(type_, seq, payload))
        rtype, rseq, rdata = read_frame(self.s)
        if rtype == ERROR:
            raise IOError("server ERROR (seq %d): %r" % (rseq, rdata))
        assert rseq == seq, "seq mismatch %d vs %d" % (rseq, seq)
        return rtype, rdata

    def hello(self):
        t, d = self.req(HELLO, struct.pack("<II", 1, 0))
        return struct.unpack("<III", d)

    def status(self):
        t, d = self.req(GET_STATUS)
        return struct.unpack("<II", d[:8])

    def video_text(self, page=1, mode=2):
        t, d = self.req(VIDEO_TEXT, struct.pack("<II", page, mode))
        cols, rows, rpage, rmode, flags = struct.unpack("<IIIII", d[:20])
        return (cols, rows), d[20:]

    def readmem(self, domain, addr, ln):
        t, d = self.req(READMEM, struct.pack("<III", domain, addr, ln))
        return d

    def quit(self):
        try:
            self.req(QUIT)
        except (IOError, OSError):
            pass


def render(meta, chars):
    cols, rows = meta
    lines = []
    for r in range(rows):
        row = chars[r * cols:(r + 1) * cols]
        lines.append("|" + row.decode("latin-1").replace("\r", "").rstrip() + "|")
    return "\n".join(lines)


def main():
    dry = "--dry-run" in sys.argv
    timeout = 60
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    image = os.path.abspath(sys.argv[sys.argv.index("--image") + 1]) if "--image" in sys.argv else os.path.abspath("build/minixgs.po")
    if not os.path.exists(image):
        sys.exit("missing %s - run make first" % image)

    for sock in (SOCK,):
        try:
            os.unlink(sock)
        except FileNotFoundError:
            pass

    args = [APP, "-p", "5", "-ds5d1=%s" % image, "-D", SOCK, "--no-quit-confirm"]
    print("launching:", " ".join(args))
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    try:
        for _ in range(40):
            if os.path.exists(SOCK):
                break
            if proc.poll() is not None:
                sys.exit("GSSquared exited early:\n" + proc.stdout.read().decode("utf-8", "replace"))
            time.sleep(0.5)
        else:
            sys.exit("debug socket never appeared")

        time.sleep(1.0)
        gs = GS2(SOCK)
        print("HELLO ->", gs.hello())
        print("GET_STATUS ->", gs.status())

        deadline = time.time() + (3 if dry else timeout)
        got = None
        while time.time() < deadline:
            try:
                meta, chars = gs.video_text()
            except OSError:
                break
            got = (meta, chars)
            if EXPECT in chars:
                print("=== BANNER FOUND ===")
                print(render(meta, chars))
                main_ = gs.readmem(DOMAIN_MAIN_RAW, 0x400, 40)
                aux_ = gs.readmem(DOMAIN_MAIN_RAW, 0x10400, 40)
                print("main row0 raw:", main_.hex())
                print("aux  row0 raw:", aux_.hex())
                gs.quit()
                print("RESULT: BOOT OK")
                return 0
            time.sleep(1.5)

        if got:
            print("=== no banner yet (%ds); last screen ===" % int(deadline - time.time() + timeout))
            print(render(*got))
            main_ = gs.readmem(DOMAIN_MAIN_RAW, 0x400, 40)
            aux_ = gs.readmem(DOMAIN_MAIN_RAW, 0x10400, 40)
            print("main row0 raw:", main_.hex())
            print("aux  row0 raw:", aux_.hex())
        else:
            print("=== no video_text reply ===")
        gs.quit()
        print("RESULT: BOOT FAIL (no banner)")
        return 1
    finally:
        time.sleep(0.5)
        try:
            proc.terminate()
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    sys.exit(main())
