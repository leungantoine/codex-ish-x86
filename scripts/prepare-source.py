#!/usr/bin/env python3
"""Patch the checked upstream checkout, without replacing its manifests."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
import urllib.request

kit = Path(__file__).resolve().parents[1]
root = Path(sys.argv[1]).resolve()
assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() == "a956835d020762cb2b570053af06f643a11c0ecc"
subprocess.run(["git", "apply", str(kit / "patches/process-group.patch")], cwd=root, check=True)

lock_path = root / "codex-rs/Cargo.lock"
lock_text = lock_path.read_text()
tokio = next(p for p in tomllib.loads(lock_text)["package"] if p["name"] == "tokio")
assert tokio["version"] == "1.52.3"
data = urllib.request.urlopen("https://static.crates.io/crates/tokio/tokio-1.52.3.crate", timeout=60).read()
assert hashlib.sha256(data).hexdigest() == tokio["checksum"]
vendor = root / "codex-rs/vendor"
vendor.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(data)) as archive:
    archive.extractall(vendor, filter="data")
pidfd = vendor / "tokio-1.52.3/src/process/unix/pidfd_reaper.rs"
s = pidfd.read_text()
old = """        } else {
            // Safety: pidfd_open returns -1 on error or a valid fd with ownership."""
new = """        } else {
            // iSH implements pidfd_open but rejects waitid(P_PIDFD). Probe
            // reaping support before selecting this path; WNOWAIT preserves
            // an already exited child for the normal try_wait call.
            let mut info = std::mem::MaybeUninit::<libc::siginfo_t>::zeroed();
            let wait_result = unsafe {
                libc::waitid(
                    libc::P_PIDFD,
                    fd as libc::id_t,
                    info.as_mut_ptr(),
                    libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
                )
            };
            if wait_result == -1 && io::Error::last_os_error().raw_os_error() == Some(libc::EINVAL) {
                unsafe { libc::close(fd as i32) };
                NO_PIDFD_SUPPORT.store(true, Relaxed);
                return None;
            }
            // Safety: pidfd_open returns -1 on error or a valid fd with ownership."""
assert s.count(old) == 1
pidfd.write_text(s.replace(old, new))
s = pidfd.read_text()
anchor = "        // Safety: The following function calls invovkes syscall pidfd_open,"
assert s.count(anchor) == 1
s = s.replace(anchor, """        // Standard iSH raises SIGSYS for missing pidfd_open rather than
        // returning ENOSYS. Detect its kernel before making that syscall.
        // Real Linux keeps the normal pidfd path, including the waitid probe.
        static IS_ISH: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
        let is_ish = *IS_ISH.get_or_init(|| {
            let mut uts = std::mem::MaybeUninit::<libc::utsname>::zeroed();
            if unsafe { libc::uname(uts.as_mut_ptr()) } != 0 {
                return false;
            }
            let uts = unsafe { uts.assume_init() };
            unsafe { std::ffi::CStr::from_ptr(uts.release.as_ptr()) }
                .to_bytes()
                .ends_with(b"-ish")
        });
        if is_ish {
            NO_PIDFD_SUPPORT.store(true, Relaxed);
            return None;
        }

""" + anchor)
pidfd.write_text(s)

manifest = root / "codex-rs/Cargo.toml"
s = manifest.read_text()
assert s.count("[patch.crates-io]") == 1
s = s.replace("[patch.crates-io]", '[patch.crates-io]\ntokio = { path = "vendor/tokio-1.52.3" }')
assert s.count('blake3 = "1.8.2"') == 1
# The upstream pure feature omits the AVX-512 C backend; Rust implementations
# still select supported instruction sets at runtime in the x86 emulator.
s = s.replace('blake3 = "1.8.2"', 'blake3 = { version = "1.8.2", features = ["pure"] }')
s += "\n[profile.release.package.zbus]\ncodegen-units = 1\n\n[profile.release.package.codex-model-provider]\ncodegen-units = 1\n"
manifest.write_text(s)
blocks = lock_text.split("[[package]]")
for i, block in enumerate(blocks):
    if '\nname = "tokio"\n' in block:
        blocks[i] = "\n".join(line for line in block.split("\n") if not line.startswith(("source = ", "checksum = ")))
lock_path.write_text("[[package]]".join(blocks))

# seccompiler does not implement the 32-bit x86 architecture. Keep the
# existing 64-bit filters intact; explicitly fail requests on x86 rather
# than compiling nonexistent syscall constants or silently omitting a filter.
landlock = root / "codex-rs/linux-sandbox/src/landlock.rs"
s = landlock.read_text()
anchor = "fn install_network_seccomp_filter_on_current_thread("
assert s.count(anchor) == 1
fallback = """#[cfg(target_arch = "x86")]
fn install_network_seccomp_filter_on_current_thread(
    _mode: NetworkSeccompMode,
    _managed_network: Option<&ManagedNetworkSandboxContext>,
) -> std::result::Result<(), SandboxErr> {
    Err(SandboxErr::SeccompBackend(
        seccompiler::BackendError::InvalidTargetArch("x86".to_string()),
    ))
}

#[cfg(not(target_arch = "x86"))]
"""
landlock.write_text(s.replace(anchor, fallback + anchor))

catalog = json.loads((root / "codex-rs/models-manager/models.json").read_text())
changed = []
for model in catalog["models"]:
    if model["slug"].startswith(("gpt-6-", "gpt-6.", "gpt-5.6-")):
        assert model["tool_mode"] == "code_mode_only"
        model["tool_mode"] = "direct"
        changed.append(model["slug"])
compat = root / "ish-compat"
compat.mkdir()
(compat / "models-direct.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
(compat / "PATCHINFO.json").write_text(json.dumps({
    "upstream_commit": "a956835d020762cb2b570053af06f643a11c0ecc",
    "upstream_tag": "rust-v0.160.0",
    "tokio_registry_sha256": tokio["checksum"],
    "direct_tool_models": changed,
    "patched_source_sha256": {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "codex-rs/utils/pty/src/process_group.rs", pidfd,
                  manifest, lock_path, landlock, compat / "models-direct.json")
    },
}, indent=2) + "\n")
print("Prepared checked source, Tokio, manifests, and direct models:", changed)

# Extend the upstream OpenSSL installer to this 32-bit musl target.
openssl = root / ".github/scripts/install-musl-openssl.sh"
s = openssl.read_text()
anchor = '  x86_64-unknown-linux-musl) openssl_target="linux-x86_64" ;;'
assert s.count(anchor) == 1
s = s.replace(anchor, '  i686-unknown-linux-musl) openssl_target="linux-generic32" ;;\n' + anchor)
# Use portable C for OpenSSL in the x86 guest.
s = s.replace('no-shared no-module no-tests', 'no-asm no-shared no-module no-tests')
openssl.write_text(s)

info_path = compat / "PATCHINFO.json"
info = json.loads(info_path.read_text())
info["x86_seccomp_policy"] = "Unsupported x86 filter requests fail with InvalidTargetArch; normal 64-bit filters unchanged"
info["atomic_query_original_sha256"] = "9fcf5fc6f0cb1da23f004fa9bc3af1cfcb5589f0c8d20e7b6de863591b60eb98"
info["atomic_query_sha256"] = hashlib.sha256((kit / "build-tools/atomic-query.c").read_bytes()).hexdigest()
info["target"] = "i686-unknown-linux-musl"
sqlite = next(p for p in tomllib.loads(lock_path.read_text())["package"] if p["name"] == "libsqlite3-sys")
assert sqlite["version"] == "0.37.0"
assert sqlite["checksum"] == "b1f111c8c41e7c61a49cd34e44c7619462967221a6443b0ec299e0ac30cfb9b1"
info["sqlite_registry_sha256"] = sqlite["checksum"]
info["sqlite_codegen_policy"] = "Only sqlite3.c uses -O0 to avoid unsupported CVTDQ2PD; CPU features and floating ABI unchanged"
info["zigcc_sha256"] = hashlib.sha256((kit / "build-tools/zigcc").read_bytes()).hexdigest()
info["blake3_features"] = ["pure"]
info["standard_ish_pidfd_policy"] = "uname release suffix -ish selects SIGCHLD before pidfd_open"
info["omitted_executables"] = ["codex-code-mode-host"]
info["patched_source_sha256"][str(openssl.relative_to(root))] = hashlib.sha256(openssl.read_bytes()).hexdigest()
info_path.write_text(json.dumps(info, indent=2) + "\n")

# Include the generated Bazel lock update in prepared source when available.
bazel_patch = kit / "metadata/bazel-dependency-lock.patch"
if bazel_patch.exists():
    subprocess.run(["git", "apply", str(bazel_patch)], cwd=root, check=True)
