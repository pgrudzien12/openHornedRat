#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 VERSION" >&2
    exit 2
fi

version=$1
case "$version" in
    *[!a-zA-Z0-9.+~_-]*|"") echo "invalid package version: $version" >&2; exit 2 ;;
esac

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"
if [ ! -x 'dist/Open Horned Rat.app/Contents/MacOS/ohr-engine' ]; then
    echo "build dist/Open Horned Rat.app first with packaging/macos/ohr-engine.spec" >&2
    exit 2
fi

arch=$(uname -m)
case "$arch" in
    arm64|x86_64) ;;
    *) echo "unsupported macOS architecture: $arch" >&2; exit 2 ;;
esac

# Apple package receipts require a numeric version. Keep the full source version
# in the release asset name. A build between releases (X.Y.Z+gitN.SHA) gets the
# commit count as a fourth component (X.Y.Z.N) so it upgrades the release and the
# builds before it; a release (X.Y.Z, or X.Y.Z-rc1) keeps just X.Y.Z.
# Two plain sed calls: BSD sed on macOS reads a label after "t" to the end of the line.
receipt_base=$(printf '%s\n' "$version" | sed -E 's/^([0-9]+(\.[0-9]+)*).*/\1/')
receipt_commits=$(printf '%s\n' "$version" | sed -nE 's/^[0-9]+(\.[0-9]+)*\+git([0-9]+)\..*/\2/p')
receipt_version="$receipt_base${receipt_commits:+.$receipt_commits}"
case "$receipt_version" in
    *[!0-9.]*|"") echo "invalid receipt version: $version" >&2; exit 2 ;;
esac

stage=build/macos/package-root
rm -rf "$stage"
install -d "$stage/Applications" "$stage/usr/local/bin" \
    "$stage/usr/local/share/doc/ohr-engine" dist/macos
ditto 'dist/Open Horned Rat.app' "$stage/Applications/Open Horned Rat.app"
install -m 755 packaging/macos/ohr-engine-cli "$stage/usr/local/bin/ohr-engine"
install -m 644 LICENSE "$stage/usr/local/share/doc/ohr-engine/LICENSE"
install -m 644 LEGAL.md "$stage/usr/local/share/doc/ohr-engine/LEGAL.md"
install -m 644 packaging/THIRD_PARTY_NOTICES.md "$stage/usr/local/share/doc/ohr-engine/THIRD_PARTY_NOTICES.md"
install -m 644 packaging/licenses/LGPL-2.1.txt "$stage/usr/local/share/doc/ohr-engine/LGPL-2.1.txt"
install -m 644 packaging/licenses/Apache-2.0.txt "$stage/usr/local/share/doc/ohr-engine/Apache-2.0.txt"
install -d "$stage/usr/local/share/doc/ohr-engine/third-party-licenses"
install -m 644 packaging/licenses/third-party/* "$stage/usr/local/share/doc/ohr-engine/third-party-licenses/"

pkgbuild --root "$stage" --identifier org.openhornedrat.engine \
    --version "$receipt_version" --install-location / \
    "dist/macos/ohr-engine-$version-macos-$arch.pkg"
