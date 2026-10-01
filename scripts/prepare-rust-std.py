#!/usr/bin/env python3
"""Patch checksum-pinned Rust 1.95.0 runtime facilities unsupported by standard iSH."""
import hashlib
import difflib
import json
from pathlib import Path
import subprocess
import sys

original_sha = "7a3649b2fea96ff61773a91aee306e08ed35c552fe7a2f4d6deac47361a27785"
assert subprocess.check_output(["rustc", "--version"], text=True).startswith("rustc 1.95.0 ")
sysroot = Path(subprocess.check_output(["rustc", "--print", "sysroot"], text=True).strip())
path = sysroot / "lib/rustlib/src/rust/library/std/src/sys/pal/unix/futex.rs"
original = path.read_bytes()
assert hashlib.sha256(original).hexdigest() == original_sha, "Unexpected Rust standard source"
s = original.decode()
old = """    let timespec = timeout
        .and_then(|d| Timespec::now(libc::CLOCK_MONOTONIC).checked_add_duration(&d))
        .and_then(|t| t.to_timespec());"""
new = """    let deadline = timeout
        .and_then(|d| Timespec::now(libc::CLOCK_MONOTONIC).checked_add_duration(&d));
    let timespec = deadline.and_then(|t| t.to_timespec());"""
assert s.count(old) == 1
s = s.replace(old, new)
old = """                    // Use FUTEX_WAIT_BITSET rather than FUTEX_WAIT to be able to give an
                    // absolute time rather than a relative time.
                    libc::syscall(
                        libc::SYS_futex,
                        futex as *const Atomic<u32>,
                        libc::FUTEX_WAIT_BITSET | libc::FUTEX_PRIVATE_FLAG,
                        expected,
                        timespec.as_ref().map_or(null(), |t| t as *const libc::timespec),
                        null::<u32>(), // This argument is unused for FUTEX_WAIT_BITSET.
                        !0u32,         // A full bitmask, to make it behave like a regular FUTEX_WAIT.
                    )"""
new = """                    // Standard iSH supports WAIT but not WAIT_BITSET. Keep the normal
                    // Linux path until ENOSYS, then use relative waits with the same
                    // original deadline even after signals and spurious wakeups.
                    static BASIC_WAIT: crate::sync::atomic::AtomicBool =
                        crate::sync::atomic::AtomicBool::new(false);
                    let basic = BASIC_WAIT.load(Relaxed);
                    let relative = if basic {
                        deadline.and_then(|end| {
                            let remaining = end
                                .sub_timespec(&Timespec::now(libc::CLOCK_MONOTONIC))
                                .unwrap_or(Duration::ZERO);
                            Timespec::zero().checked_add_duration(&remaining)
                                .and_then(|t| t.to_timespec())
                        })
                    } else {
                        None
                    };
                    let wait_timeout = if basic { &relative } else { &timespec };
                    let operation = if basic { libc::FUTEX_WAIT } else { libc::FUTEX_WAIT_BITSET };
                    let result = libc::syscall(
                        libc::SYS_futex,
                        futex as *const Atomic<u32>,
                        operation | libc::FUTEX_PRIVATE_FLAG,
                        expected,
                        wait_timeout.as_ref().map_or(null(), |t| t as *const libc::timespec),
                        null::<u32>(),
                        !0u32,
                    );
                    if !basic && result < 0 && crate::sys::io::errno() == libc::ENOSYS {
                        BASIC_WAIT.store(true, Relaxed);
                        continue;
                    }
                    result"""
assert s.count(old) == 1
path.write_text(s.replace(old, new))
subprocess.run(["rustfmt", "--edition", "2024", str(path)], check=True)
process_path = sysroot / "lib/rustlib/src/rust/library/std/src/sys/process/unix/unix.rs"
process_original = process_path.read_bytes()
process_sha = "cabba94153bcdae7674f5743886d518db848710aee0ee20abfecf8bb159d3c4b"
assert hashlib.sha256(process_original).hexdigest() == process_sha
p = process_original.decode()
old = "        let (input, output) = sys::net::Socket::new_pair(libc::AF_UNIX, libc::SOCK_SEQPACKET)?;"
new = """        let (input, output, use_stream) = match sys::net::Socket::new_pair(libc::AF_UNIX, libc::SOCK_SEQPACKET) {
            Ok((input, output)) => (input, output, false),
            Err(error) => {
                // iSH lacks SEQPACKET. A stream is sufficient for the fixed
                // error frame when pidfd descriptor transfer was not requested.
                let mut uts = mem::MaybeUninit::<libc::utsname>::zeroed();
                let is_ish = unsafe { libc::uname(uts.as_mut_ptr()) } == 0
                    && unsafe { crate::ffi::CStr::from_ptr(uts.assume_init().release.as_ptr()) }
                        .to_bytes().ends_with(b"-ish");
                if error.raw_os_error() != Some(libc::EINVAL) || self.get_create_pidfd() || !is_ish {
                    return Err(error);
                }
                let (input, output) = sys::net::Socket::new_pair(libc::AF_UNIX, libc::SOCK_STREAM)?;
                (input, output, true)
            }
        };"""
assert p.count(old) == 1
p = p.replace(old, new)
old = "        let (input, output) = sys::pipe::pipe()?;"
assert p.count(old) == 1
p = p.replace(old, old + "\n\n        #[cfg(not(target_os = \"linux\"))]\n        let use_stream = false;")
old = """        let mut bytes = [0; 8];

        // loop to handle EINTR
        loop {
            match input.read(&mut bytes) {
                Ok(0) => return Ok((p, ours)),
                Ok(8) => {"""
new = """        let mut bytes = [0; 8];
        let mut received = 0;

        // Handle EINTR and partial stream reads without losing the error frame.
        loop {
            match input.read(&mut bytes[received..]) {
                Ok(0) if received == 0 => return Ok((p, ours)),
                Ok(0) => {
                    assert!(p.wait().is_ok(), "wait() should either return Ok or panic");
                    panic!("short read on the CLOEXEC pipe");
                }
                Ok(count) => {
                    received += count;
                    if received < bytes.len() {
                        if !use_stream {
                            assert!(p.wait().is_ok(), "wait() should either return Ok or panic");
                            panic!("short read on the CLOEXEC pipe");
                        }
                        continue;
                    }"""
assert p.count(old) == 1
p = p.replace(old, new)
old = """                Ok(..) => {
                    // pipe I/O up to PIPE_BUF bytes should be atomic
                    // similarly SOCK_SEQPACKET messages should arrive whole
                    assert!(p.wait().is_ok(), "wait() should either return Ok or panic");
                    panic!("short read on the CLOEXEC pipe")
                }
"""
assert p.count(old) == 1
process_path.write_text(p.replace(old, ""))
subprocess.run(["rustfmt", "--edition", "2024", str(process_path)], check=True)
thread_path = sysroot / "lib/rustlib/src/rust/library/std/src/sys/thread/unix.rs"
thread_original = thread_path.read_bytes()
thread_sha = "95920ddfd37a3864783624e0fa8df849fe919a8c5a9b733892e1bea38c0f411d"
assert hashlib.sha256(thread_original).hexdigest() == thread_sha
t = thread_original.decode()
t = """#[cfg(target_os = "linux")]
fn is_ish_kernel() -> bool {
    static IS_ISH: crate::sync::OnceLock<bool> = crate::sync::OnceLock::new();
    *IS_ISH.get_or_init(|| {
        let mut uts = mem::MaybeUninit::<libc::utsname>::zeroed();
        (unsafe { libc::uname(uts.as_mut_ptr()) }) == 0
            && unsafe { crate::ffi::CStr::from_ptr(uts.assume_init().release.as_ptr()) }
                .to_bytes().ends_with(b"-ish")
    })
}

""" + t
old = """                unsafe { libc::clock_nanosleep(crate::sys::time::Instant::CLOCK_ID, 0, rqtp, rmtp) }"""
new = """                // iSH raises SIGSYS for missing clock_nanosleep. Select
                // its existing nanosleep before attempting that syscall.
                #[cfg(target_os = "linux")]
                if is_ish_kernel() {
                    let result = unsafe { libc::nanosleep(rqtp, rmtp) };
                    return if result == 0 { 0 } else { sys::io::errno() };
                }
                unsafe { libc::clock_nanosleep(crate::sys::time::Instant::CLOCK_ID, 0, rqtp, rmtp) }"""
assert t.count(old) == 1
t = t.replace(old, new)
old = """pub fn sleep_until(deadline: crate::time::Instant) {
    use crate::time::Instant;
"""
new = old + """
    #[cfg(target_os = "linux")]
    if is_ish_kernel() {
        if let Some(delay) = deadline.checked_duration_since(Instant::now()) {
            sleep(delay);
        }
        return;
    }
"""
assert t.count(old) == 1
thread_path.write_text(t.replace(old, new))
subprocess.run(["rustfmt", "--edition", "2024", str(thread_path)], check=True)
info = {
    "rust_version": "1.95.0",
    "files": {
        "library/std/src/sys/pal/unix/futex.rs": {
            "original_sha256": original_sha,
            "patched_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        "library/std/src/sys/thread/unix.rs": {
            "original_sha256": thread_sha,
            "patched_sha256": hashlib.sha256(thread_path.read_bytes()).hexdigest(),
        },
        "library/std/src/sys/process/unix/unix.rs": {
            "original_sha256": process_sha,
            "patched_sha256": hashlib.sha256(process_path.read_bytes()).hexdigest(),
        },
    },
    "policies": ["iSH selects nanosleep before missing clock_nanosleep; retain EINTR remainder","FUTEX_WAIT_BITSET ENOSYS selects FUTEX_WAIT; preserve monotonic deadline",
                 "iSH SEQPACKET EINVAL selects STREAM only without pidfd transfer; accumulate error frame"],
    "build": "RUSTC_BOOTSTRAP=1 cargo -Z build-std=std,panic_abort for i686 only",
}
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
(output / "RUSTSTDINFO.json").write_text(json.dumps(info, indent=2) + "\n")
patch = ""
for source, before, name in [(path, original, "library/std/src/sys/pal/unix/futex.rs"),
                             (process_path, process_original, "library/std/src/sys/process/unix/unix.rs"),
                             (thread_path, thread_original, "library/std/src/sys/thread/unix.rs")]:
    patch += "".join(difflib.unified_diff(before.decode().splitlines(True), source.read_text().splitlines(True),
                                        fromfile="a/" + name, tofile="b/" + name))
(output / "rust-std.patch").write_text(patch)
print("Prepared exact Rust source and recorded its futex fallback hashes")
