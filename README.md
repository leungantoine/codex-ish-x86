# OpenAI Codex for App Store iSH (32-bit x86)

This repository ports **OpenAI's real Codex CLI** to standard [App Store iSH](https://apps.apple.com/us/app/ish-shell/id1436902243), which emulates 32-bit x86. It is separate from [codex-ish](https://github.com/leungantoine/codex-ish), the ARM64 iSH-AOK project. Neither binary can be used in the other guest architecture.

**Status: Codex 0.160.0 binaries are published; a physical-device interactive startup failure is under investigation.** Static ELF32 checks, QEMU, native Linux, and noninteractive shell/app-server tests in unmodified standard iSH passed. A user reported `Illegal instruction` when launching plain `codex` in the App Store app; those earlier checks did not cover the interactive TUI startup path. Physical iOS authentication, interactive tasks, performance and background behavior remain to be tested. [Download the latest Release](https://github.com/leungantoine/codex-ish-x86/releases/latest).

## Source and target

- OpenAI stable tag: `rust-v0.160.0`
- Exact source commit: `a956835d020762cb2b570053af06f643a11c0ecc`
- Rust: `1.95.0`
- Target: `i686-unknown-linux-musl` (ELF32 Intel 80386)
- C/C++ cross compiler: Zig `0.14.0`, x86 musl, Pentium 4 / SSE2 baseline
- OpenSSL: upstream installer's checksum-pinned `3.6.4`, extended to `linux-generic32`, static portable C
- Ripgrep: `15.2.0`, compiled from its locked source crate for the same target

The package builds `codex`, `codex-responses-api-proxy`, `codex-path/rg`, and `diagnostics/ish-syscall-probe`. It includes source-input hashes, a matching GPT-6/GPT-6.1 direct-tool catalog, checksums, `BUILDINFO`, licenses and this guide. It omits the separate V8 code-mode host and Linux sandbox helper. Direct shell and patch tools use the real Codex implementation.

## Install or upgrade with one command

In standard iSH's x86 Alpine root:

```sh
apk add --no-cache ca-certificates curl tar coreutils git bash && curl -fsSL --retry 3 https://raw.githubusercontent.com/leungantoine/codex-ish-x86/main/setup.sh -o /tmp/setup-codex-x86.sh && sh /tmp/setup-codex-x86.sh && export PATH="$HOME/.local/bin:$PATH"
```

Then, including after reopening iSH:

```sh
codex
```

The installer checks the guest architecture, verifies the Release archive and all internal file checksums, installs to `~/.local/opt/codex-ish-x86`, creates `~/.local/bin/codex`, and saves PATH in shell startup files. It does not automatically launch Codex when iSH opens. Existing authentication and configuration in `~/.codex` are retained. Repeating the command upgrades the package and launcher. Do not install this over an ARM64 guest.

The launcher selects GPT-6-Luna with medium reasoning, disables the daemon and V8 code mode, and supplies this release's direct-tool catalog. To select another model:

```sh
codex --model gpt-6-sol
codex --model gpt-6.1-sol
codex --model gpt-6-astra
```

Model availability depends on your account. The catalog changes tool-mode preferences for existing model entries; it does not change model identity or create account access.

## Authentication and physical-device smoke test

For first sign-in:

```sh
codex login --device-auth
mkdir -p "$HOME/codex-test"
cd "$HOME/codex-test"
codex
```

Ask it:

```text
Actually execute printf 'ish-x86-shell-ok\n' using the shell tool. Show the actual output and exit status. Do not predict the output.
```

A passing test needs a real tool execution, output `ish-x86-shell-ok`, and exit status 0. Record your iSH version/build, device, and `codex --version`. Start with a small task and keep the app visible during work. Device login, interactive operation, performance and background reliability are not established by cloud tests.

## Security and supported operation

Standard iSH lacks the kernel facilities required by Codex's normal Linux sandbox. The launcher uses `sandbox_mode="danger-full-access"` and `approval_policy="on-request"`. **Commands can access guest files and network.** Review actions before approving and keep sensitive files out of the guest. No credentials are embedded in the repository, build or archive.

Daemon mode, local V8 execution, and sandboxed Linux execution are unsupported. This port does not patch the signed iOS app or its suspension behavior. iOS may suspend or terminate the app when backgrounded or under memory pressure; no guest patch here is claimed to prevent that.

## Compatibility changes

1. `utils/pty/src/process_group.rs`: if `prctl(PR_SET_PDEATHSIG, SIGTERM)` returns `EINVAL`, return success and skip the parent-PID guard because no death signal was armed. Normal Linux behavior is preserved and other errors propagate.
2. Vendored Tokio `1.52.3`: a kernel release ending in `-ish` selects the existing SIGCHLD reaper before calling `pidfd_open`, because the App Store release raises `SIGSYS` for that missing syscall. Other Linux kernels retain the normal pidfd path. After `pidfd_open`, probe `waitid(P_PIDFD)` with `WEXITED | WNOHANG | WNOWAIT`. On `EINVAL`, close the descriptor and use the existing SIGCHLD reaper. The download is verified against upstream's Cargo.lock checksum.
3. Extend upstream's OpenSSL installer to the 32-bit musl target and use portable C. No authentication or model inference code is replaced.
4. Select BLAKE3's upstream `pure` feature to omit its AVX-512 C backend; no checksum or dependency version is changed.
5. Rebuild the exact Rust 1.95.0 standard library for the x86 target. On an iSH kernel only, `SOCK_SEQPACKET` error-channel failure falls back to `SOCK_STREAM` when pidfd transfer was not requested; partial error frames are accumulated. `FUTEX_WAIT_BITSET` returning `ENOSYS` selects basic `FUTEX_WAIT` with the original monotonic deadline preserved. Other Linux kernels retain their normal behavior. On iSH, thread sleeps use supported `nanosleep` before the missing `clock_nanosleep` syscall; signal interruptions retain the remainder. All three original standard-library files are SHA-256 pinned.
6. On 32-bit x86, requests for seccompiler network filters fail explicitly with its unsupported-architecture error. The existing 64-bit filters are unchanged; requesting a filter never silently succeeds. This port runs with full guest access as documented above.
7. Generate the direct catalog from the pinned source by changing only `tool_mode` for the seven existing GPT-6/GPT-6.1/GPT-5.6 entries. The command disables code mode and uses Codex's existing direct tools.

8. Vendored checksum-pinned `event-listener` 5.4.1 and `concurrent-queue` 2.5.0: use `LOCK OR` on a local word for the 32-bit full memory fence because standard iSH rejects `LOCK NOT`. Declare the condition-code clobber; retain the full memory barrier. The x86-64 implementation is unchanged.

9. Descriptor cleanup detects the iSH kernel with a stack-only `uname` call and uses upstream's existing `/proc/self/fd` fallback before `close_range`, which raises SIGSYS on this guest. Stdio, explicitly preserved descriptors, and the spawn error channel retain their normal treatment. Real Linux keeps its original path.

10. The i686 compiler wrapper compiles only `regex_automata` 0.4.13 with `-C opt-level=0`. LLVM's optimized integer bitset comparison emitted `MOVMSKPS`, which standard iSH rejects. CPU features and floating-point ABI stay unchanged. Other crates retain their normal optimization settings. A Cargo release package override also records this setting so cached optimized objects are invalidated. Native compiler invocations receive no wrapper flags. Regex compilation and searching may be slower. The wrapper and its hash are packaged; the focused harness compiles and searches ASCII and Unicode expressions.

11. Add LLVM compiler-rt 19.1.7's atomic size/alignment query at links requesting libatomic; preserve real atomics and OpenSSL's existing lock fallback. Source hash and LLVM license are included.
12. Compile only `sqlite3.c` with `-O0` to avoid unsupported `CVTDQ2PD` in optimized date conversion. The locked source, CPU features and floating ABI are unchanged. SQLite performance may be lower.

`scripts/prepare-source.py` checks the exact source commit before patching. `compat/PATCHINFO.json` in the archive records source, original Tokio checksum, catalog changes and final patched input hashes. `compat/RUSTSTDINFO.json` and `compat/rust-std.patch` record the runtime source pins and exact patch; Rust licenses are included. Do not apply the ARM64 project's historical overlay to this source.

## Build and verification

The workflow uses Ubuntu 24.04 x86_64, one Cargo build job, release optimization 2, debug 0, LTO off and 16 codegen units. Scoped overrides keep `zbus` and `codex-model-provider` at one codegen unit. Compilation caches survive failed attempts. A source snapshot records SHA256, file mode and nanosecond timestamps for Codex and the rebuilt Rust standard library. On the next build, timestamps are restored only when the contents, mode and absolute source roots match; changed files retain fresh timestamps. Cargo still checks dependencies, compiler settings and features. The first snapshot-producing build remains a full rebuild; subsequent unchanged inputs can reuse their compiled outputs. Canceled jobs skip cache saving to avoid racing active compiler outputs.

Required checks before publication:

1. Native tests of the patched PTY crate and a subprocess harness exercising normal Linux, injected `EINVAL`, fatal `EPERM`, injected iSH kernel identity, worker-thread spawning and child cleanup.
2. A tiny static 32-bit Rust link test before the full compilation.
3. All four executables must be ELF32 Intel 80386, with no `PT_INTERP` and no shared-library `DT_NEEDED` entries. Verify internal and outer checksums.
4. QEMU version, ripgrep and syscall diagnostics checks.
5. Real CLI execution in **unmodified standard iSH release `builds/494`**, commit `216cf98a7cda1d68221add374630ede00aae9cd4`, using its Darwin ARM64 backend on a macOS ARM64 runner, corresponding to the public May 2023 release. Apple currently lists iSH 1.3.2. The emulator does not exercise UIKit, iOS memory limits or suspension.
6. For GPT-6-Luna, Sol, GPT-6.1-Sol and Astra, a local mock Responses server requests a random-marker shell command. Check the actual marker and exit status 17 return in the next model request, on native Linux and inside iSH. These tests establish the execution path, not authenticated service acceptance or a real model's tool choice.
7. App-server pipe and PTY shell calls, captured output and exit status 17 inside standard iSH. Installer/startup checks use actual ELF32 executables on Linux; their architecture detection is supplied by a test-only `uname` wrapper.

Verified in [full build 37057721035](https://github.com/leungantoine/codex-ish-x86/actions/runs/37057721035): 62 PTY tests and 162 Linux sandbox library tests; native subprocess modes for normal Linux, injected EINVAL, fatal EPERM and iSH kernel identity; all four static ELF32 executables and checksums; QEMU version and diagnostics; four actual CLI shell loops using mocked GPT-6/GPT-6.1 tool requests on Linux and unmodified standard iSH; real app-server pipe and PTY output with exit status 17. The final documentation package additionally verifies fresh bash and ash startup PATH, the installed plain `codex` shell loop and repeated installation without duplicate PATH entries. Mocked inference does not establish live service acceptance or account/model access.

Supporting focused checks: [Rust/Tokio and OpenSSL atomics](https://github.com/leungantoine/codex-ish-x86/actions/runs/36952380152), [SQLite date and floating point](https://github.com/leungantoine/codex-ish-x86/actions/runs/36958879061), and [dependency lock metadata](https://github.com/leungantoine/codex-ish-x86/actions/runs/36936516270) passed. Earlier [full build 36952350602](https://github.com/leungantoine/codex-ish-x86/actions/runs/36952350602) exposed SQLite's unsupported optimized conversion; publication was blocked until the replacement build passed.

## Troubleshooting

```sh
uname -m
codex --version
"$HOME/.local/opt/codex-ish-x86/diagnostics/ish-syscall-probe"
```

- `codex: not found`: run `export PATH="$HOME/.local/bin:$PATH"`, or reopen the login shell after setup.
- `Exec format error`: this package requires 32-bit x86 iSH. ARM64 and x86_64 packages do not work there.
- Release/download failure: check connectivity to GitHub and the latest Release assets. Do not bypass checksum errors.
- Slow startup or app termination: keep the app foregrounded, start with a small task, record the operation and crash time. Share private diagnostics safely; never publish authentication files or private task contents.
- Shell failure: retain the actual error and syscall probe output. QEMU passing alone does not establish iSH support.

## Maintenance

Inspect the pinned upstream source and dependencies before upgrading. Recreate only still-needed compatibility patches, refresh the matching model catalog, dependency lock metadata and input hashes, compile actual binaries, repeat the verification gates, and then publish. Follow `AGENTS.md` here and in upstream. This is an independent compatibility port, not an official OpenAI or iSH distribution.
