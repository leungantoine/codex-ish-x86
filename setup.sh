#!/bin/sh
set -eu
case "$(uname -m)" in i386|i486|i586|i686) ;; *) echo 'Use the 32-bit x86 Alpine guest in standard iSH.' >&2; exit 1 ;; esac
for name in curl sha256sum tar mktemp; do
  command -v "$name" >/dev/null 2>&1 || { echo 'Run: apk add ca-certificates curl tar coreutils git bash' >&2; exit 1; }
done
base=${CODEX_ISH_RELEASE_BASE:-https://github.com/leungantoine/codex-ish-x86/releases/latest/download}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
archive=codex-ish-x86.tar.gz
curl -fL --retry 3 "$base/$archive" -o "$work/$archive"
curl -fL --retry 3 "$base/$archive.sha256" -o "$work/$archive.sha256"
(cd "$work" && sha256sum -c "$archive.sha256")
mkdir -p "$HOME/.local/opt" "$HOME/.local/bin"
stage="$HOME/.local/opt/.codex-ish-x86-new-$$"
mkdir "$stage"
tar -xzf "$work/$archive" -C "$stage"
(cd "$stage" && sha256sum -c SHA256SUMS)
for name in codex codex-responses-api-proxy codex-path/rg diagnostics/ish-syscall-probe; do
  test -x "$stage/$name" || { echo "Missing $name" >&2; exit 1; }
done
destination="$HOME/.local/opt/codex-ish-x86"
backup="$HOME/.local/opt/.codex-ish-x86-old-$$"
if [ -d "$destination" ]; then mv "$destination" "$backup"; fi
mv "$stage" "$destination"
launcher="$HOME/.local/bin/.codex-x86-new-$$"
cat > "$launcher" <<'SH'
#!/bin/sh
exec "$HOME/.local/opt/codex-ish-x86/codex" \
  --no-daemon --disable code_mode_host --disable code_mode --disable code_mode_only \
  -c 'tui.animations=false' \
  -c 'model="gpt-6-luna"' -c 'model_reasoning_effort="medium"' \
  -c 'sandbox_mode="danger-full-access"' -c 'approval_policy="on-request"' \
  -c "model_catalog_json=\"$HOME/.local/opt/codex-ish-x86/compat/models-direct.json\"" "$@"
SH
chmod 0755 "$launcher"
mv -f "$launcher" "$HOME/.local/bin/codex"
ln -sfn "$destination/codex-path/rg" "$HOME/.local/bin/rg"
path_line='export PATH="$HOME/.local/bin:$PATH"'
for profile in .profile .bashrc .zshrc .bash_profile .bash_login; do
  case "$profile" in .bash_profile|.bash_login) [ -f "$HOME/$profile" ] || continue ;; esac
  if ! grep -Fqx "$path_line" "$HOME/$profile" 2>/dev/null; then printf '\n# Codex for standard iSH\n%s\n' "$path_line" >> "$HOME/$profile"; fi
done
if [ -d "$backup" ]; then rm -rf "$backup"; fi
echo 'Installed. Run: codex'
echo 'For this session: export PATH="$HOME/.local/bin:$PATH"'
echo 'Commands can access guest files and network. First sign-in: codex login --device-auth'
