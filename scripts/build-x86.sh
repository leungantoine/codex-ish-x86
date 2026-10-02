#!/usr/bin/env bash
set -euo pipefail
kit=$(cd "$(dirname "$0")/.." && pwd)
source_root=$(cd "${1:?upstream source directory required}" && pwd)
export TARGET=i686-unknown-linux-musl
export RUNNER_TEMP="${RUNNER_TEMP:-/tmp}"
export CC="$kit/build-tools/zigcc" CXX="$kit/build-tools/zigcxx"
export CC_i686_unknown_linux_musl="$CC" CXX_i686_unknown_linux_musl="$CXX"
export CARGO_TARGET_I686_UNKNOWN_LINUX_MUSL_LINKER="$CC"
export CARGO_TARGET_I686_UNKNOWN_LINUX_MUSL_RUSTFLAGS='-C link-self-contained=no -C target-cpu=pentium4'
export TARGET_CC="$CC" TARGET_CXX="$CXX"
export CMAKE_C_COMPILER="$CC" CMAKE_CXX_COMPILER="$CXX"
export CFLAGS='-pthread -Wno-error=frame-larger-than'
export CXXFLAGS="$CFLAGS"
export AWS_LC_SYS_NO_JITTER_ENTROPY=1 AWS_LC_SYS_NO_JITTER_ENTROPY_i686_unknown_linux_musl=1
export PKG_CONFIG_ALLOW_CROSS=1
export CARGO_BUILD_JOBS=1 CARGO_PROFILE_RELEASE_DEBUG=0 CARGO_PROFILE_RELEASE_LTO=off
export CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16 CARGO_PROFILE_RELEASE_OPT_LEVEL=2
export GITHUB_ENV=$(mktemp)
trap 'rm -f "$GITHUB_ENV"' EXIT
cd "$source_root"
python3 "$kit/scripts/prepare-rust-std.py" "$source_root/ish-compat"
python3 "$kit/scripts/cache-input-mtimes.py" restore "$source_root" "$kit/.build-input-mtimes.json"
OPENSSL_CC="$CC" OPENSSL_BUILD_JOBS=2 bash .github/scripts/install-musl-openssl.sh
set -a
source "$GITHUB_ENV"
set +a
# Exercise the same static crypto library and query shim before the final link.
openssl_prefix=$I686_UNKNOWN_LINUX_MUSL_OPENSSL_DIR
"$CC" -O2 -static -pthread -I"$openssl_prefix/include" \
  "$kit/tests/atomic-runtime-probe.c" -L"$openssl_prefix/lib" -lcrypto -latomic \
  -o "$RUNNER_TEMP/atomic-runtime-probe"
qemu-i386-static "$RUNNER_TEMP/atomic-runtime-probe"
# Select the actual CLI and proxy; the separate V8 host is not built.
RUSTC_BOOTSTRAP=1 cargo -Z build-std=std,panic_abort build --manifest-path codex-rs/Cargo.toml --locked --release --target "$TARGET" -j 1 \
  --bin codex --bin codex-responses-api-proxy
RUSTC_BOOTSTRAP=1 cargo -Z build-std=std,panic_abort install ripgrep --version 15.2.0 --locked --target "$TARGET" --root "$RUNNER_TEMP/rg-x86" -j 1
sqlite_source=$(find "$HOME/.cargo/registry/src" -type d -name libsqlite3-sys-0.37.0 -print -quit)
test -n "$sqlite_source"
"$CC" -O2 -static -pthread -DSQLITE_THREADSAFE=1 -DSQLITE_ENABLE_MATH_FUNCTIONS \
  -I"$sqlite_source/sqlite3" "$sqlite_source/sqlite3/sqlite3.c" \
  "$kit/tests/sqlite-runtime-probe.c" -lm -o "$RUNNER_TEMP/sqlite-runtime-probe"
qemu-i386-static "$RUNNER_TEMP/sqlite-runtime-probe"
package="$kit/dist/codex-ish-x86"
mkdir -p "$package"/{codex-path,codex-resources,diagnostics,compat,licenses/ripgrep,licenses/rust,licenses/llvm}
mkdir -p "$package/licenses/event-listener" "$package/licenses/concurrent-queue"
for name in codex codex-responses-api-proxy; do
  install -m 0755 "codex-rs/target/$TARGET/release/$name" "$package/$name"
done
install -m 0755 "$RUNNER_TEMP/rg-x86/bin/rg" "$package/codex-path/rg"
"$CC" -O2 -static "$kit/tests/ish-syscall-probe.c" -o "$package/diagnostics/ish-syscall-probe"
cp "$kit/tests/ish-syscall-probe.c" "$package/diagnostics/"
cp ish-compat/*.json "$package/compat/"
cp ish-compat/rust-std.patch "$package/compat/"
cp LICENSE NOTICE "$package/"
cp "$kit/README.md" "$package/README.md"
cp "$kit/setup.sh" "$package/setup.sh"
cp "$kit/licenses/rust/"* "$package/licenses/rust/"
cp "$kit/licenses/llvm/LICENSE.TXT" "$package/licenses/llvm/"
cp "$kit/build-tools/atomic-query.c" "$package/compat/"
cp "$kit/build-tools/zigcc" "$package/compat/zigcc"
cp codex-rs/vendor/event-listener-5.4.1/src/notify.rs "$package/compat/event-listener-notify.rs"
find codex-rs/vendor/event-listener-5.4.1 -maxdepth 1 -iname '*license*' -type f -exec cp {} "$package/licenses/event-listener/" \;
test -n "$(find "$package/licenses/event-listener" -type f -print -quit)"
cp codex-rs/vendor/concurrent-queue-2.5.0/src/lib.rs "$package/compat/concurrent-queue-lib.rs"
find codex-rs/vendor/concurrent-queue-2.5.0 -maxdepth 1 -iname '*license*' -type f -exec cp {} "$package/licenses/concurrent-queue/" \;
test -n "$(find "$package/licenses/concurrent-queue" -type f -print -quit)"
rg_source=$(find "$HOME/.cargo/registry/src" -type d -name ripgrep-15.2.0 -print -quit)
for name in COPYING LICENSE-MIT UNLICENSE; do cp "$rg_source/$name" "$package/licenses/ripgrep/"; done
cat > "$package/BUILDINFO" <<INFO
OpenAI Codex rust-v0.160.0
Upstream commit: a956835d020762cb2b570053af06f643a11c0ecc
Target: $TARGET (32-bit x86)
Rust: $(rustc --version)
Zig: $(zig version)
OpenSSL: 3.6.4, upstream SHA-256 verified, portable C, static musl
Ripgrep: 15.2.0, built from its locked source crate
Rust std: rebuilt from exact 1.95.0 source; iSH socket error-channel, sleep and ENOSYS futex fallbacks
Atomic query: LLVM compiler-rt 19.1.7 size/alignment query; Zig link compatibility
SQLite: locked libsqlite3-sys 0.37.0; sqlite3.c only uses -O0 to avoid unsupported CVTDQ2PD
Event listener: locked 5.4.1 source; 32-bit full fence uses LOCK OR; x86-64 unchanged
BLAKE3: upstream pure feature, AVX-512 C backend omitted
Direct tools; no V8 host, daemon, or Linux sandbox support in standard iSH.
Physical iOS authentication, performance, and background behavior require device tests.
Concurrent-queue: checksum-pinned 2.5.0; 32-bit LOCK OR full barrier; x86-64 unchanged
INFO
(cd "$package" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -czf "$kit/dist/codex-ish-x86.tar.gz" -C "$package" .
(cd "$kit/dist" && sha256sum codex-ish-x86.tar.gz > codex-ish-x86.tar.gz.sha256)
