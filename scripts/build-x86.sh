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
OPENSSL_CC="$CC" OPENSSL_BUILD_JOBS=2 bash .github/scripts/install-musl-openssl.sh
set -a
source "$GITHUB_ENV"
set +a
# Select the actual CLI and proxy; the separate V8 host is not built.
cargo build --manifest-path codex-rs/Cargo.toml --locked --release --target "$TARGET" -j 1 \
  --bin codex --bin codex-responses-api-proxy
cargo install ripgrep --version 15.2.0 --locked --target "$TARGET" --root "$RUNNER_TEMP/rg-x86" -j 1
package="$kit/dist/codex-ish-x86"
mkdir -p "$package"/{codex-path,codex-resources,diagnostics,compat,licenses/ripgrep}
for name in codex codex-responses-api-proxy; do
  install -m 0755 "codex-rs/target/$TARGET/release/$name" "$package/$name"
done
install -m 0755 "$RUNNER_TEMP/rg-x86/bin/rg" "$package/codex-path/rg"
"$CC" -O2 -static "$kit/tests/ish-syscall-probe.c" -o "$package/diagnostics/ish-syscall-probe"
cp "$kit/tests/ish-syscall-probe.c" "$package/diagnostics/"
cp ish-compat/*.json "$package/compat/"
cp LICENSE NOTICE "$package/"
cp "$kit/README.md" "$package/README.md"
cp "$kit/setup.sh" "$package/setup.sh"
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
Direct tools; no V8 host, daemon, or Linux sandbox support in standard iSH.
Physical iOS authentication, performance, and background behavior require device tests.
INFO
(cd "$package" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -czf "$kit/dist/codex-ish-x86.tar.gz" -C "$package" .
(cd "$kit/dist" && sha256sum codex-ish-x86.tar.gz > codex-ish-x86.tar.gz.sha256)
