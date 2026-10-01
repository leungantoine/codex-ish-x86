# Codex x86 port instructions

Build OpenAI's real pinned Codex source for standard App Store iSH's 32-bit x86 Alpine guest. Keep this repository separate from the ARM64 iSH-AOK project.

- Preserve the upstream commit pin and crate checksums. Keep compatibility changes narrow and preserve normal Linux behavior.
- Honor the upstream source's AGENTS.md when editing Rust. Run formatting and scoped tests; refresh Bazel dependency metadata when manifests change.
- Build the CLI, responses proxy, ripgrep, and syscall diagnostics for `i586-unknown-linux-musl`. The V8 host is omitted; direct tools are required.
- Verify ELF32 Intel 80386 architecture, static linking, checksums, and version before emulator tests.
- Test real shell output and exit status through pipe and PTY APIs and model tool loops in unmodified standard iSH. QEMU alone does not establish iSH compatibility.
- Publish installable binaries only after the build and emulator checks pass. Maintain one-command setup and startup PATH persistence.
- Never commit credentials, authentication files, or private device diagnostics. Distinguish mocked inference, emulator verification, and physical-device results in documentation.
- Do not claim iOS background crash fixes from guest patches. Keep unsupported features and remaining device tests explicit.
