#!/usr/bin/env python3
"""Capture interactive Codex startup on a real host terminal without credentials."""
import errno, fcntl, os, pty, select, signal, struct, sys, termios, time
from pathlib import Path

label, *command = sys.argv[1:]
assert label.replace('-', '').isalnum(), 'Use a simple artifact label'
log = open(f"{label}-kernel.log", "wb", buffering=0)
os.dup2(log.fileno(), 666)
os.set_inheritable(666, True)
pid, master = pty.fork()
if pid == 0:
    os.environ["TERM"] = "xterm-256color"
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("CODEX_API_KEY", None)
    os.execvp(command[0], command)
os.close(666)
fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", int(os.environ.get("TUI_ROWS", "44")), int(os.environ.get("TUI_COLS", "40")), 0, 0))
transcript = bytearray()
deadline = time.monotonic() + 90
entered = False
interrupted = False
status = None
pending = b""
while time.monotonic() < deadline:
    ready, _, _ = select.select([master], [], [], 0.25)
    if ready:
        try:
            data = os.read(master, 65536)
        except OSError as error:
            if error.errno != errno.EIO:
                raise
            break
        if not data:
            break
        transcript.extend(data)
        pending += data
        # Answer terminal queries; keep user input separate from replies.
        for query, reply in [(b"\x1b[6n", b"\x1b[1;1R"),
                             (b"\x1b[c", b"\x1b[?1;2c"),
                             (b"\x1b[>c", b"\x1b[>0;1;0c"),
                             (b"\x1b]10;?\x1b\\", b"\x1b]10;rgb:0000/0000/0000\x1b\\"),
                             (b"\x1b]11;?\x1b\\", b"\x1b]11;rgb:ffff/ffff/ffff\x1b\\")]:
            while query in pending:
                os.write(master, reply)
                pending = pending.replace(query, b"", 1)
        pending = pending[-100:]
    waited, result = os.waitpid(pid, os.WNOHANG)
    if waited:
        status = result
        break
    if os.environ.get("TUI_ENTER") == "1" and not entered and time.monotonic() > deadline - 80:
        os.write(master, b"\r")
        entered = True
    if not interrupted and time.monotonic() > deadline - 30:
        os.write(master, b"\x03\x03")
        interrupted = True
if status is None:
    waited, status_now = os.waitpid(pid, os.WNOHANG)
    if waited:
        status = status_now
    else:
        os.kill(pid, signal.SIGTERM)
        _, status = os.waitpid(pid, 0)
Path(f"{label}-terminal.log").write_bytes(transcript)
print("terminal transcript tail:", repr(bytes(transcript)[-3000:]))
print("kernel log:", Path(f"{label}-kernel.log").read_text(errors="replace"))
print("emulator exit:", os.waitstatus_to_exitcode(status))

assert os.waitstatus_to_exitcode(status) == 0, "Interactive Codex did not exit cleanly"
assert b"OpenAI Codex" in transcript or b"Welcome to" in transcript, "TUI was not drawn"
assert b"illegal instruction" not in Path(f"{label}-kernel.log").read_bytes()
print("PASS: actual interactive TUI drawn and exited 0 with animations disabled")
