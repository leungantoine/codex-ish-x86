# OpenAI Codex for App Store iSH (32-bit x86)

This repository ports **OpenAI's real Codex CLI** to standard [App Store iSH](https://apps.apple.com/us/app/ish-shell/id1436902243), which emulates 32-bit x86. It is separate from [codex-ish](https://github.com/leungantoine/codex-ish), the ARM64 iSH-AOK project. Neither binary can be used in the other guest architecture.

**Status: real x86 binaries compiled; standard iSH compatibility verification is in progress. No installable Release yet.** The workflow must build the real executable and pass static ELF checks, QEMU and standard-iSH shell tests before it publishes a Release. Do not interpret the existence of a workflow or installer as a working port.

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

**Use this only after an installable Release appears.** In standard iSH's x86 Alpine root:

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

Only a successful build and emulator verification allow Release publication. Physical-device authentication and shell testing remain an additional check. Recorded preliminary checks: [dependency metadata run 36932313300](https://github.com/leungantoine/codex-ish-x86/actions/runs/36932313300) passed and its generated patch is committed under `metadata/`. [Build attempt 36932975814](https://github.com/leungantoine/codex-ish-x86/actions/runs/36932975814) passed all 62 native PTY tests, all three syscall-fallback harness modes, and a static ELF32 Rust program under QEMU; it stopped on a build-script environment assignment before compiling Codex. That assignment is fixed in the next run. These checks do not establish a working Codex x86 binary. Detailed build and emulator results will be recorded when available.

## Troubleshooting

```sh
uname -m
codex --version
"$HOME/.local/opt/codex-ish-x86/diagnostics/ish-syscall-probe"
```

- `codex: not found`: run `export PATH="$HOME/.local/bin:$PATH"`, or reopen the login shell after setup.
- `Exec format error`: this package requires 32-bit x86 iSH. ARM64 and x86_64 packages do not work there.
- Missing Release/download failure: the port has not passed publication gates or connectivity to GitHub failed. Do not bypass checksum errors.
- Slow startup or app termination: keep the app foregrounded, start with a small task, record the operation and crash time. Share private diagnostics safely; never publish authentication files or private task contents.
- Shell failure: retain the actual error and syscall probe output. QEMU passing alone does not establish iSH support.

## Maintenance

Inspect the pinned upstream source and dependencies before upgrading. Recreate only still-needed compatibility patches, refresh the matching model catalog, dependency lock metadata and input hashes, compile actual binaries, repeat the verification gates, and then publish. Follow `AGENTS.md` here and in upstream. This is an independent compatibility port, not an official OpenAI or iSH distribution.

### Current compilation finding

The first full attempt compiled static OpenSSL and initial Rust dependencies, then `ring` 0.17.14 rejected the i586 target because it requires SSE/SSE2. The port now uses the canonical i686 musl target with a Pentium 4 / SSE2 baseline. This does not establish emulator compatibility; execution in released standard iSH remains a publication gate.

### Standard iSH runtime findings

[Preflight run 36936566523](https://github.com/leungantoine/codex-ish-x86/actions/runs/36936566523) passed actual ELF32 Rust startup, clock, floating point, four worker threads, and real worker shell commands returning output and exit status 17 inside unmodified standard iSH 494. The minimal test root filesystem needed `/dev/null` and the other device nodes normally supplied by the iOS app. This test did not run a finished Codex binary.

The same run's raw diagnostic probe then encountered `SIGSYS` on missing `pidfd_open` (syscall 434). The new Tokio kernel check avoids that call on iSH; a focused native and standard-iSH Tokio harness is testing this patch before the next full build. [Dependency metadata run 36936516270](https://github.com/leungantoine/codex-ish-x86/actions/runs/36936516270) passed with BLAKE3's `pure` feature; the regenerated Bazel lock patch was identical.

### Host timing differences

The unmodified 494 Linux-hosted CLI creates futex conditions with the default realtime clock but calculates timed waits using a monotonic timestamp. A 50 ms condition wait therefore expired immediately in the Linux emulator. The iOS/Darwin path uses `pthread_cond_timedwait_relative_np` instead. The final standard-iSH checks use the unmodified Darwin ARM64 backend to exercise the app's timing and CPU paths; no emulator source workaround is applied. Normal Linux behavior is separately checked with QEMU and native ELF32 execution. These remain cloud tests, with no UIKit, device authentication, or physical iOS memory/background verification.

[Darwin runtime run 36940632684](https://github.com/leungantoine/codex-ish-x86/actions/runs/36940632684) passed startup and worker shell commands on the unmodified ARM64 emulator. The rebuilt runtime correctly waited for a 50 ms timeout, then exposed missing `clock_nanosleep` (267) in a worker sleep. The next runtime patch selects supported `nanosleep` on iSH before that call. [Full build 36936516185](https://github.com/leungantoine/codex-ish-x86/actions/runs/36936516185) compiled Codex core but failed in upstream seccompiler callers that assumed 64-bit syscall constants; the x86 path now returns an explicit unsupported-architecture error. These fixes require further verification; no finished binary is claimed.

### Focused runtime verification passed

[Darwin runtime verification 36942647548](https://github.com/leungantoine/codex-ish-x86/actions/runs/36942647548) passed with the unmodified iSH 494 source and default logging, using the exact rebuilt ELF32 probes from [36942031271](https://github.com/leungantoine/codex-ish-x86/actions/runs/36942031271). It verified startup, clocks, floating point, worker threads, 50 ms timed waits, notifications after sleep, 20 real worker shell commands with stdout/stderr and exit status 17, ENOENT and EPERM subprocess errors, and kill/reap cleanup. The diagnostic confirmed normal SIGCHLD registration and the iSH pidfd bypass. Native injected error modes and the rebuilt runtime under QEMU also passed. This is a runtime harness result; full Codex CLI compilation and tool-loop verification remain pending.

Enabling the released emulator's optional syscall trace logger under the cloud compiler caused query-only `rt_sigaction` calls to fail with EFAULT. Its log expression reads an uninitialized action when the input pointer is null. The exact same guest binaries passed with default logging; no emulator source was changed. Verification uses default logging and records guest stderr separately. The disposable macOS runner also uses a short hostname to fit the guest's 65-byte uname field.

### Final link finding

[Build 36941651734](https://github.com/leungantoine/codex-ish-x86/actions/runs/36941651734) passed all 62 PTY and 162 Linux sandbox library tests, compiled the complete real Rust CLI and dependencies, then failed at final linking because Zig's empty libatomic lacks `__atomic_is_lock_free`, referenced by OpenSSL. The x86 linker now adds the query subset of [LLVM compiler-rt 19.1.7](https://github.com/llvm/llvm-project/blob/llvmorg-19.1.7/compiler-rt/lib/builtins/atomic.c). It uses the target compiler's atomic capability and pointer alignment to preserve the choice between real atomics and OpenSSL's existing locks. The source hash and LLVM license are packaged. A concurrent 32-bit probe verifies aligned atomics, the 4-byte-aligned 64-bit locking fallback, and SHA256 before the CLI link. The compiled Rust cache was saved; the retry still must pass all release gates.

### Atomic and runtime verification passed

[Focused verification 36952380152](https://github.com/leungantoine/codex-ish-x86/actions/runs/36952380152) passed both QEMU and the unmodified standard iSH 494 Darwin ARM64 backend. The exact static OpenSSL 3.6.4 library linked successfully with the LLVM query. Four concurrent workers completed 4,000 aligned atomic updates and 4,000 updates using the existing lock fallback, with SHA256 digest checks. The rebuilt Rust/Tokio harness also passed timed waits, notifications, 20 worker shell commands, error propagation and cleanup. This verifies the runtime and atomic fix; the full Codex build and its CLI tool tests remain in progress.

### Full binary and SQLite findings

[Full build 36952350602](https://github.com/leungantoine/codex-ish-x86/actions/runs/36952350602) produced the actual CLI, proxy, ripgrep and diagnostic executables. All four passed ELF32, static-link and checksum checks, and the CLI reported `codex-cli 0.160.0` under QEMU and inside unmodified standard iSH. Native Linux passed all four mocked model tool loops and the installed `codex` launcher. Publication was correctly blocked because the first standard-iSH model loop hit unsupported `CVTDQ2PD` in SQLite's `computeYMD_HMS` date conversion. [Binary inspection 36958418972](https://github.com/leungantoine/codex-ish-x86/actions/runs/36958418972) identified the exact function and instruction.

[SQLite verification 36958879061](https://github.com/leungantoine/codex-ish-x86/actions/runs/36958879061) passed real date, leap-year, Julian-day, current-timestamp and floating-point checks under QEMU and unmodified standard iSH. The compiler wrapper now appends `-O0` only when compiling `sqlite3.c`; the locked SQLite source, CPU features and floating-point ABI are unchanged. Rust and the other C libraries keep their optimization settings. SQLite performance may be lower; physical-device performance remains untested. An earlier experiment disabling SSE for SQLite failed its QEMU check and is not used. The complete CLI is being rebuilt with the verified SQLite setting and must repeat all release gates.

### Event notification fence finding

The restarted [build 36959204334](https://github.com/leungantoine/codex-ish-x86/actions/runs/36959204334) passed compilation, static checks and all native model-tool/installer tests with the SQLite fix. Standard iSH then rejected `LOCK NOT` in event-listener's hand-written notification fence. [Binary inspection 36970010378](https://github.com/leungantoine/codex-ish-x86/actions/runs/36970010378) identified the exact operation. The patched 32-bit fence uses supported `LOCK OR` and preserves the full barrier. The existing harness now checks 20 notifications with shared-memory visibility and 200 bounded-channel messages from four concurrent producers, in addition to its subprocess checks. These changes still require the new build and emulator verification before publication.

### Unbounded queue fence finding

[Build 36971004602](https://github.com/leungantoine/codex-ish-x86/actions/runs/36971004602) produced all four binaries and passed static, QEMU, native model-tool and installer checks. Its full iSH loop exposed the same unsupported `LOCK NOT` in `concurrent-queue` 2.5.0's unbounded queue, confirmed by [binary inspection 36980097401](https://github.com/leungantoine/codex-ish-x86/actions/runs/36980097401). This crate now receives the same checksum-verified 32-bit locked OR fence patch, retaining the full barrier and declaring flag changes. The focused harness tests both bounded and unbounded channels with four concurrent producers and 200 unique messages each. Final CLI verification is still required before publication. The earlier event notification/runtime harness passed on rerun; two additional ordinary runs passed, while one initial native emulator SIGSEGV remains unexplained.
