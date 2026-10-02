# Patched upstream dependency metadata

The source preparation selects checksum-verified local Tokio 1.52.3 and event-listener 5.4.1 vendors.
[Verification run 36936516270](https://github.com/leungantoine/codex-ish-x86/actions/runs/36936516270) regenerated this patch with BLAKE3's `pure` feature selected. The generated patch was byte-for-byte identical; no dependency versions changed.
[Bazel metadata verification run 36932313300](https://github.com/leungantoine/codex-ish-x86/actions/runs/36932313300) ran upstream `just bazel-lock-update` successfully against OpenAI commit `a956835d020762cb2b570053af06f643a11c0ecc` with these manifest changes.

`bazel-dependency-lock.patch` records the generated `MODULE.bazel.lock` update. It changes the Tokio and event-listener registry entries to their local vendor entries; it is not a hand-written approximation. It applies to the pinned upstream root:

```sh
git -C upstream apply ../metadata/bazel-dependency-lock.patch
```

The metadata workflow has read-only repository permission. Its artifact and log export are reviewed before this patch is committed; it does not write to the branch itself. Regenerate when source or dependency changes.

The event-listener fence patch's generated dependency lock passed [metadata run 36971004586](https://github.com/leungantoine/codex-ish-x86/actions/runs/36971004586). Its 29,460-byte patch was reviewed, applied to the exact upstream commit, parsed as JSON, and committed through the connector. The metadata workflow retains read-only permission.
