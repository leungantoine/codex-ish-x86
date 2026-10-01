# Patched upstream dependency metadata

The source preparation selects a checksum-verified local Tokio 1.52.3 vendor.
[Bazel metadata verification run 36932313300](https://github.com/leungantoine/codex-ish-x86/actions/runs/36932313300) ran upstream `just bazel-lock-update` successfully against OpenAI commit `a956835d020762cb2b570053af06f643a11c0ecc` with these manifest changes.

`bazel-dependency-lock.patch` records the generated `MODULE.bazel.lock` update. It changes the Tokio registry entry to the local vendor entry; it is not a hand-written approximation. It applies to the pinned upstream root:

```sh
git -C upstream apply ../metadata/bazel-dependency-lock.patch
```

The metadata workflow has read-only repository permission. Its artifact and log export are reviewed before this patch is committed; it does not write to the branch itself. Regenerate when source or dependency changes.
