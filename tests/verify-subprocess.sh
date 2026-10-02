#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/inputs" "$work/harness/src"
if [[ -n "${ISH_PATCHED_SOURCE:-}" ]]; then
  mkdir -p "$work/inputs/codex-rs/vendor"
  cp -a "$ISH_PATCHED_SOURCE/codex-rs/vendor/tokio-1.52.3" "$work/inputs/codex-rs/vendor/"
  cp -a "$ISH_PATCHED_SOURCE/codex-rs/vendor/event-listener-5.4.1" "$work/inputs/codex-rs/vendor/"
  cp -a "$ISH_PATCHED_SOURCE/codex-rs/vendor/concurrent-queue-2.5.0" "$work/inputs/codex-rs/vendor/"
  mkdir -p "$work/inputs/codex-rs/utils/pty/src"
  cp "$ISH_PATCHED_SOURCE/codex-rs/utils/pty/src/process_group.rs" "$work/inputs/codex-rs/utils/pty/src/"
  cp "$ISH_PATCHED_SOURCE/codex-rs/utils/pty/src/linux_fds.rs" "$work/inputs/codex-rs/utils/pty/src/"
else
  tar -xzf "$repo_root/ish-overlay.tar.gz" -C "$work/inputs"
fi
cp "$work/inputs/codex-rs/utils/pty/src/process_group.rs" "$work/harness/src/process_group.rs"
cp "$work/inputs/codex-rs/utils/pty/src/linux_fds.rs" "$work/harness/src/linux_fds.rs"
cat > "$work/harness/Cargo.toml" <<EOF
[package]
name = "ish-subprocess-verification"
version = "0.1.0"
edition = "2024"
[dependencies]
libc = "=0.2.186"
tokio = { path = "$work/inputs/codex-rs/vendor/tokio-1.52.3", features = ["process", "rt-multi-thread", "macros", "time"] }
event-listener = { path = "$work/inputs/codex-rs/vendor/event-listener-5.4.1" }
async-channel = "=2.5.0"
regex = "=1.12.3"
regex-automata = "=0.4.13"
[patch.crates-io]
event-listener = { path = "$work/inputs/codex-rs/vendor/event-listener-5.4.1" }
concurrent-queue = { path = "$work/inputs/codex-rs/vendor/concurrent-queue-2.5.0" }
EOF
cat > "$work/harness/src/main.rs" <<'RS'
#[allow(dead_code)]
mod process_group;
#[allow(dead_code)]
mod linux_fds;
use std::time::Duration;
use tokio::process::Command;
use event_listener::{Event, IntoNotification, Listener};

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() {
    for (pattern, text, expected) in [
        (r"[a-zA-Z0-9_]+", "ish-shell-ok_17", "ish"),
        (r"(?:ish|codex)-shell-[a-z]+", "prefix codex-shell-ok suffix", "codex-shell-ok"),
        (r"\p{Greek}+", "hello αβγ world", "αβγ"),
        (r"(?m)^exit=[0-9]+$", "start\nexit=17\nend", "exit=17"),
    ] {
        let regex = regex::Regex::new(pattern).unwrap();
        assert_eq!(regex.find(text).unwrap().as_str(), expected);
        assert!(!regex.is_match("!"));
    }
    println!("PASS: actual regex-automata compilation and ASCII/Unicode/search checks");
    for _ in 0..20 {
        let event = std::sync::Arc::new(Event::new());
        let value = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let listener = event.listen();
        let worker_event = event.clone();
        let worker_value = value.clone();
        let worker = std::thread::spawn(move || {
            worker_value.store(17, std::sync::atomic::Ordering::Release);
            worker_event.notify(1.additional());
        });
        listener.wait_timeout(Duration::from_secs(2)).expect("event notification timed out");
        assert_eq!(value.load(std::sync::atomic::Ordering::Acquire), 17);
        worker.join().unwrap();
    }
    for unbounded in [false, true] {
        let (sender, receiver) = if unbounded { async_channel::unbounded() } else { async_channel::bounded(1) };
        let mut workers = Vec::new();
        for worker in 0..4 {
            let sender = sender.clone();
            workers.push(std::thread::spawn(move || {
                for item in 0..50 { sender.send_blocking(worker * 50 + item).unwrap(); }
            }));
        }
        drop(sender);
        let mut seen = std::collections::HashSet::new();
        while let Ok(item) = receiver.recv_blocking() { assert!(seen.insert(item)); }
        for worker in workers { worker.join().unwrap(); }
        assert_eq!(seen.len(), 200);
    }
    println!("PASS: patched event-listener notifications and 200 bounded and 200 unbounded concurrent-channel messages");
    // Exercise timed futex waits and wakeups, including the rebuilt std fallback.
    let pair = std::sync::Arc::new((std::sync::Mutex::new(()), std::sync::Condvar::new()));
    let start = std::time::Instant::now();
    let (guard, timeout) = pair.1.wait_timeout(pair.0.lock().unwrap(), Duration::from_millis(50)).unwrap();
    assert!(timeout.timed_out());
    assert!(start.elapsed() >= Duration::from_millis(40));
    drop(guard);
    let wake_pair = pair.clone();
    let wake = std::thread::spawn(move || {
        let start = std::time::Instant::now();
        std::thread::sleep(Duration::from_millis(20));
        assert!(start.elapsed() >= Duration::from_millis(15));
        let _guard = wake_pair.0.lock().unwrap();
        wake_pair.1.notify_one();
    });
    let (guard, timeout) = pair.1.wait_timeout(pair.0.lock().unwrap(), Duration::from_secs(2)).unwrap();
    assert!(!timeout.timed_out());
    drop(guard);
    wake.join().unwrap();
    println!("PASS: standard library timed wait and wake checks");
    let mode = std::env::var("ISH_TEST_MODE").unwrap_or_default();
    let wrong_parent = mode == "einval";
    let expect_error = mode == "eperm";
    for _ in 0..20 {
        tokio::spawn(async move {
            let parent = if wrong_parent { -1 } else { unsafe { libc::getpid() } };
            let mut command = Command::new("/bin/sh");
            command.args(["-c", "printf 'ish-shell-ok\n'; printf 'ish-stderr-ok\n' >&2; exit 17"]);
            command.kill_on_drop(true);
            unsafe {
                command.pre_exec(move || {
                    linux_fds::close_inherited_fds_except(&[]);
                    process_group::detach_from_tty()?;
                    process_group::set_parent_death_signal(parent)
                });
            }
            let result = tokio::time::timeout(Duration::from_secs(10), command.output()).await.unwrap();
            if expect_error {
                assert_eq!(result.unwrap_err().raw_os_error(), Some(libc::EPERM));
            } else {
                let output = result.unwrap();
                assert_eq!(output.status.code(), Some(17));
                assert_eq!(output.stdout, b"ish-shell-ok\n");
                assert_eq!(output.stderr, b"ish-stderr-ok\n");
            }
        }).await.unwrap();
    }
    if !expect_error {
        tokio::spawn(async {
            let mut bad = Command::new("/definitely-missing-ish-test-command");
            unsafe { bad.pre_exec(|| Ok(())); }
            assert_eq!(bad.spawn().unwrap_err().raw_os_error(), Some(libc::ENOENT));
            let mut denied = Command::new("/bin/sh");
            unsafe { denied.pre_exec(|| Err(std::io::Error::from_raw_os_error(libc::EPERM))); }
            assert_eq!(denied.spawn().unwrap_err().raw_os_error(), Some(libc::EPERM));
        }).await.unwrap();
        tokio::spawn(async {
            let mut child = Command::new("/bin/sleep").arg("30").kill_on_drop(true).spawn().unwrap();
            child.kill().await.unwrap();
            let status = tokio::time::timeout(Duration::from_secs(10), child.wait()).await.unwrap().unwrap();
            assert!(!status.success());
        }).await.unwrap();
    }
    println!("PASS: mode={mode:?}; 20 worker-thread shell spawns; output, exit and cleanup checks");
}
RS
# Test-only syscall shim. The Release executables never load this library.
cat > "$work/shim.c" <<'C'
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>
int uname(struct utsname *uts) {
    const char *mode = getenv("ISH_TEST_MODE");
    if (mode && strcmp(mode,"ish")==0) {
        memset(uts,0,sizeof(*uts));
        strcpy(uts->sysname,"Linux");
        strcpy(uts->release,"4.20.69-ish");
        const char marker[]="PASS: injected standard iSH kernel identity\n";
        write(STDERR_FILENO,marker,sizeof(marker)-1);
        return 0;
    }
    int (*real_uname)(struct utsname *) = dlsym(RTLD_NEXT,"uname");
    return real_uname(uts);
}
int prctl(int option, ...) {
    const char *mode = getenv("ISH_TEST_MODE");
    if (option == PR_SET_PDEATHSIG && mode && strcmp(mode,"einval")==0) { errno=EINVAL; return -1; }
    if (option == PR_SET_PDEATHSIG && mode && strcmp(mode,"eperm")==0) { errno=EPERM; return -1; }
    va_list args; va_start(args,option);
    unsigned long value=va_arg(args,unsigned long); va_end(args);
    if (option==PR_SET_PDEATHSIG || option==PR_SET_NAME || option==PR_GET_NAME)
        return syscall(SYS_prctl,option,value,0,0,0);
    errno=ENOSYS; return -1;
}
int waitid(idtype_t type, id_t id, siginfo_t *info, int options) {
    const char *mode=getenv("ISH_TEST_MODE");
    if (type==P_PIDFD && mode && strcmp(mode,"ish")==0) {
        const char marker[]="FAIL: iSH kernel selected the pidfd reaper\n";
        write(STDERR_FILENO,marker,sizeof(marker)-1);
        _exit(90);
    }
    if (type==P_PIDFD && mode && strcmp(mode,"einval")==0) {
        const char marker[]="PASS: injected waitid(P_PIDFD) EINVAL\n";
        write(STDERR_FILENO,marker,sizeof(marker)-1);
        errno=EINVAL; return -1;
    }
    return syscall(SYS_waitid,type,id,info,options,0);
}
C
cc -shared -fPIC -O2 "$work/shim.c" -o "$work/shim.so" -ldl
cargo build --manifest-path "$work/harness/Cargo.toml" -j 1
"$work/harness/target/debug/ish-subprocess-verification"
ISH_TEST_MODE=einval LD_PRELOAD="$work/shim.so" "$work/harness/target/debug/ish-subprocess-verification" 2>&1 | tee "$work/einval.log"
grep -Fxq 'PASS: injected waitid(P_PIDFD) EINVAL' "$work/einval.log"
ISH_TEST_MODE=eperm LD_PRELOAD="$work/shim.so" "$work/harness/target/debug/ish-subprocess-verification"
ISH_TEST_MODE=ish LD_PRELOAD="$work/shim.so" "$work/harness/target/debug/ish-subprocess-verification" 2>&1 | tee "$work/ish.log"
grep -Fxq 'PASS: injected standard iSH kernel identity' "$work/ish.log"
if [[ -n "${ISH_X86_HARNESS_OUT:-}" ]]; then
  RUSTC_WRAPPER="$repo_root/build-tools/rustc-wrapper" \
  CARGO_TARGET_I686_UNKNOWN_LINUX_MUSL_LINKER="$repo_root/build-tools/zigcc" \
  CARGO_TARGET_I686_UNKNOWN_LINUX_MUSL_RUSTFLAGS='-C link-self-contained=no -C target-cpu=pentium4' \
  RUSTC_BOOTSTRAP=1 cargo -Z build-std=std,panic_abort build --manifest-path "$work/harness/Cargo.toml" --release --target i686-unknown-linux-musl -j 1
  cp "$work/harness/target/i686-unknown-linux-musl/release/ish-subprocess-verification" "$ISH_X86_HARNESS_OUT"
fi
