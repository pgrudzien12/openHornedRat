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
if [ ! -x dist/ohr-engine/ohr-engine ]; then
    echo "build dist/ohr-engine first with packaging/linux/ohr-engine.spec" >&2
    exit 2
fi

arch=$(uname -m)
case "$arch" in
    arm64|x86_64) ;;
    *) echo "unsupported macOS architecture: $arch" >&2; exit 2 ;;
esac

# Apple package receipts require a numeric version. Keep the full source version
# in the release asset name, including the commit suffix for weekly builds.
receipt_version=$(printf '%s\n' "$version" | sed -E 's/^([0-9]+(\.[0-9]+)*).*/\1/')
case "$receipt_version" in
    *[!0-9.]*|"") echo "invalid receipt version: $version" >&2; exit 2 ;;
esac

stage=build/macos/package-root
rm -rf "$stage"
install -d "$stage/usr/local/lib/ohr-engine" "$stage/usr/local/bin" \
    "$stage/usr/local/share/doc/ohr-engine" dist/macos
ditto dist/ohr-engine "$stage/usr/local/lib/ohr-engine"
ln -s ../lib/ohr-engine/ohr-engine "$stage/usr/local/bin/ohr-engine"
install -m 644 LICENSE "$stage/usr/local/share/doc/ohr-engine/LICENSE"
install -m 644 LEGAL.md "$stage/usr/local/share/doc/ohr-engine/LEGAL.md"
install -m 644 packaging/THIRD_PARTY_NOTICES.md "$stage/usr/local/share/doc/ohr-engine/THIRD_PARTY_NOTICES.md"
install -m 644 packaging/licenses/LGPL-2.1.txt "$stage/usr/local/share/doc/ohr-engine/LGPL-2.1.txt"

pkgbuild --root "$stage" --identifier org.openhornedrat.engine \
    --version "$receipt_version" --install-location / \
    "dist/macos/ohr-engine-$version-macos-$arch.pkg"
