#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/inputs" "$work/harness/src"
if [[ -n "${ISH_PATCHED_SOURCE:-}" ]]; then
  mkdir -p "$work/inputs/codex-rs/vendor"
  cp -a "$ISH_PATCHED_SOURCE/codex-rs/vendor/tokio-1.52.3" "$work/inputs/codex-rs/vendor/"
  mkdir -p "$work/inputs/codex-rs/utils/pty/src"
  cp "$ISH_PATCHED_SOURCE/codex-rs/utils/pty/src/process_group.rs" "$work/inputs/codex-rs/utils/pty/src/"
else
  tar -xzf "$repo_root/ish-overlay.tar.gz" -C "$work/inputs"
fi
cp "$work/inputs/codex-rs/utils/pty/src/process_group.rs" "$work/harness/src/process_group.rs"
cat > "$work/harness/Cargo.toml" <<EOF
[package]
name = "ish-subprocess-verification"
version = "0.1.0"
edition = "2024"
[dependencies]
libc = "=0.2.186"
tokio = { path = "$work/inputs/codex-rs/vendor/tokio-1.52.3", features = ["process", "rt-multi-thread", "macros", "time"] }
EOF
cat > "$work/harness/src/main.rs" <<'RS'
#[allow(dead_code)]
mod process_group;
use std::time::Duration;
use tokio::process::Command;

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() {
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
#include <errno.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
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
    if (type==P_PIDFD && mode && strcmp(mode,"einval")==0) {
        const char marker[]="PASS: injected waitid(P_PIDFD) EINVAL\n";
        write(STDERR_FILENO,marker,sizeof(marker)-1);
        errno=EINVAL; return -1;
    }
    return syscall(SYS_waitid,type,id,info,options,0);
}
C
cc -shared -fPIC -O2 "$work/shim.c" -o "$work/shim.so"
cargo build --manifest-path "$work/harness/Cargo.toml" -j 1
"$work/harness/target/debug/ish-subprocess-verification"
ISH_TEST_MODE=einval LD_PRELOAD="$work/shim.so" "$work/harness/target/debug/ish-subprocess-verification" 2>&1 | tee "$work/einval.log"
grep -Fxq 'PASS: injected waitid(P_PIDFD) EINVAL' "$work/einval.log"
ISH_TEST_MODE=eperm LD_PRELOAD="$work/shim.so" "$work/harness/target/debug/ish-subprocess-verification"
