# Codex for App Store iSH (32-bit x86)

Work in progress: a port of OpenAI's real Codex CLI to standard App Store iSH's 32-bit x86 Alpine guest. This repository is separate from the ARM64 iSH-AOK build.

Pinned starting source: OpenAI `rust-v0.159.3`, commit `01fc69f4026735edfdf6789820549727a4867b11`. Planned target: `i586-unknown-linux-musl`, with direct shell tools and the daemon and V8 code-mode host disabled.

No working x86 binary has been published yet. Compilation, static ELF verification, and subprocess tests in unmodified standard iSH are required before an installable Release. Authentication, performance, and iOS background behavior require physical-device testing.
