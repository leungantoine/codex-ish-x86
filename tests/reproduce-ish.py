#!/usr/bin/env python3
"""Run real Codex shell APIs without credentials, under Linux or iSH's CLI."""
import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time

label, *command = sys.argv[1:]
messages = queue.Queue()
with open(f"{label}-stderr.log", "w") as errors:
    os.dup2(errors.fileno(), 666)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, bufsize=1, pass_fds=(666,))
    os.close(666)

    def read_stderr():
        for line in process.stderr:
            errors.write(line)
            errors.flush()

    threading.Thread(target=read_stderr, daemon=True).start()

    def read_stdout():
        for line in process.stdout:
            print(f"{label}: {line.rstrip()}", flush=True)
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                pass
        messages.put(None)

    threading.Thread(target=read_stdout, daemon=True).start()

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def response(request_id, seconds=300):
        end = time.monotonic() + seconds
        output = b""
        while time.monotonic() < end:
            message = messages.get(timeout=max(0.01, end - time.monotonic()))
            if message is None:
                try:
                    status = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    status = "stdout closed while emulator remains running"
                raise RuntimeError(f"{label}: server exited; status={status}")
            if message.get("method") == "command/exec/outputDelta":
                output += base64.b64decode(message["params"]["deltaBase64"])
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"], output
        raise TimeoutError(f"{label}: response {request_id} timed out")

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "ish_repro", "version": "1"},
            "capabilities": {"experimentalApi": True}}})
        response(1)
        send({"method": "initialized", "params": {}})
        for request_id, tty in [(2, False), (3, True)]:
            send({"id": request_id, "method": "command/exec", "params": {
                "command": ["/bin/sh", "-c", "printf 'ish-shell-ok\\n'; exit 17"],
                "cwd": "/", "timeoutMs": 30000, "tty": tty,
                "processId": f"probe-{request_id}",
                "sandboxPolicy": {"type": "dangerFullAccess"}}})
            result, output = response(request_id)
            assert result["exitCode"] == 17, result
            if not tty:
                assert result["stdout"] == "ish-shell-ok\n", result
            else:
                assert b"ish-shell-ok" in output, output
            print(f"PASS: {label}: tty={tty}: real Codex shell output and exit", flush=True)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
