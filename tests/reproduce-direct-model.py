#!/usr/bin/env python3
"""Verify actual model tool schemas and shell roundtrip against a local mock.

This tests the released Codex binary, not real OpenAI model behavior.
No credentials are used or read by the mock provider.
"""
import gzip
import http.server
import json
import os
import subprocess
import sys
import threading

label, catalog, model, *command = sys.argv[1:]
requests = []
failures = []
marker = "ish-direct-" + os.urandom(8).hex()


def tool_specs(body):
    specs = list(body.get("tools") or [])
    for item in body.get("input", []):
        if item.get("type") == "additional_tools":
            specs.extend(item.get("tools", []))
    return specs


def flatten(specs):
    for spec in specs:
        if spec.get("type") == "namespace":
            yield from flatten(spec.get("tools", []))
        else:
            yield spec


def completed(response_id):
    return {"type": "response.completed", "response": {
        "id": response_id, "usage": {"input_tokens": 0, "output_tokens": 0,
                                      "total_tokens": 0}}}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        try:
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            body = json.loads(raw)
            requests.append(body)
            assert body["model"] == model, body["model"]
            assert "Authorization" not in self.headers
            specs = list(flatten(tool_specs(body)))
            names = [s.get("name", s.get("type")) for s in specs]
            print(f"{label}: model={body['model']} advertised tools={names}", flush=True)
            assert "exec" not in names, "V8 code-mode exec was advertised"
            shell = next(s for s in specs if s.get("name") in
                         ("exec_command", "shell_command", "shell"))
            if len(requests) == 1:
                name = shell["name"]
                shell_command = f"printf '{marker}\\n'; exit 17"
                if name == "exec_command":
                    args = {"cmd": shell_command, "login": False, "yield_time_ms": 1000}
                elif name == "shell_command":
                    args = {"command": shell_command, "workdir": "/", "timeout_ms": 10000}
                else:
                    args = {"command": ["/bin/sh", "-c", shell_command],
                            "workdir": "/", "timeout_ms": 10000}
                events = [{"type": "response.created", "response": {"id": "resp-1"}},
                          {"type": "response.output_item.done", "item": {
                              "type": "function_call", "call_id": "ish-direct-shell",
                              "name": name, "arguments": json.dumps(args)}},
                          completed("resp-1")]
            else:
                assert len(requests) == 2, "Unexpected repeated model request"
                outputs = [i for i in body["input"] if i.get("type") == "function_call_output"
                           and i.get("call_id") == "ish-direct-shell"]
                assert len(outputs) == 1, body["input"]
                output = json.dumps(outputs[0]["output"])
                assert marker in output, output
                assert "17" in output, output
                print(f"PASS: {label}: actual direct shell output returned to model: {output}",
                      flush=True)
                events = [{"type": "response.output_item.done", "item": {
                    "type": "message", "id": "msg-2", "role": "assistant",
                    "content": [{"type": "output_text", "text": "verified shell result"}]}},
                    completed("resp-2")]
            data = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as error:
            failures.append(repr(error))
            self.send_error(400, str(error))


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]
overrides = ["--no-daemon", "--disable", "code_mode_host", "--disable", "code_mode",
             "--disable", "code_mode_only", "-c", f'model_catalog_json="{catalog}"',
             "-c", 'model_provider="ish_mock"', "-c",
             'model_providers.ish_mock={name="Local mock",'
             f'base_url="http://127.0.0.1:{port}/v1",'
             'wire_api="responses",requires_openai_auth=false,supports_websockets=false}',
             "-c", 'model_reasoning_effort="medium"', "exec", "--model", model,
             "--sandbox", "danger-full-access", "--skip-git-repo-check", "--json",
             "Execute the shell tool once and report the actual result."]
if "/.local/bin/" in command[-1] and command[-1].rsplit("/", 1)[-1] in ("codex-gpt6", "codex"):
    # Exercise the installed launcher's own runtime flags and catalog path.
    overrides = overrides[9:]
if label.startswith("setup-"):
    # Verify the startup launcher's sandbox default rather than supplying it here.
    index = overrides.index("--sandbox")
    del overrides[index:index + 2]
env = os.environ.copy()
env.pop("OPENAI_API_KEY", None)
env.pop("CODEX_API_KEY", None)
with open(f"{label}-stderr.log", "wb") as errors:
    os.dup2(errors.fileno(), 666)
    process = subprocess.Popen(command + overrides, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, pass_fds=(666,), env=env)
    os.close(666)
    try:
        stdout, stderr = process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        failures.append("Codex timed out")
    errors.write(stderr)
    errors.flush()
server.shutdown()
print(stdout.decode(errors="replace"), flush=True)
print(stderr.decode(errors="replace")[-4000:], flush=True)
assert not failures, failures
assert process.returncode == 0, process.returncode
assert len(requests) == 2, len(requests)
assert b"codex-code-mode-host" not in stderr, "Code-mode host was invoked"
print(f"PASS: {label}: {model} direct tool loop, no code-mode host, Codex exit 0", flush=True)
