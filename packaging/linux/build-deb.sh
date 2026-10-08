#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 DEBIAN_VERSION" >&2
    exit 2
fi
version=$1
case "$version" in
    *[!a-zA-Z0-9.+:~\-]*|"") echo "invalid Debian version: $version" >&2; exit 2 ;;
esac
dpkg --validate-version "$version"

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"
if [ ! -x dist/ohr-engine/ohr-engine ]; then
    echo "build dist/ohr-engine first with packaging/linux/ohr-engine.spec" >&2
    exit 2
fi

architecture=$(dpkg --print-architecture)
stage="build/debian/ohr-engine_${version}_${architecture}"
rm -rf "$stage"
install -d "$stage/DEBIAN" "$stage/opt/ohr-engine" "$stage/usr/bin" \
    "$stage/usr/share/applications" "$stage/usr/share/doc/ohr-engine"
cp -a dist/ohr-engine/. "$stage/opt/ohr-engine/"
install -m 755 packaging/linux/ohr-engine-launch "$stage/usr/bin/ohr-engine-launch"
ln -s /opt/ohr-engine/ohr-engine "$stage/usr/bin/ohr-engine"
install -m 644 packaging/linux/ohr-engine.desktop "$stage/usr/share/applications/ohr-engine.desktop"
install -m 644 LICENSE "$stage/usr/share/doc/ohr-engine/LICENSE"
install -m 644 LEGAL.md "$stage/usr/share/doc/ohr-engine/LEGAL.md"
install -m 644 packaging/THIRD_PARTY_NOTICES.md "$stage/usr/share/doc/ohr-engine/THIRD_PARTY_NOTICES.md"
install -m 644 packaging/licenses/LGPL-2.1.txt "$stage/usr/share/doc/ohr-engine/LGPL-2.1.txt"
install -m 644 packaging/licenses/Apache-2.0.txt "$stage/usr/share/doc/ohr-engine/Apache-2.0.txt"
install -d "$stage/usr/share/doc/ohr-engine/third-party-licenses"
install -m 644 packaging/licenses/third-party/* "$stage/usr/share/doc/ohr-engine/third-party-licenses/"

cat > "$stage/DEBIAN/control" <<EOF
Package: ohr-engine
Version: $version
Section: games
Priority: optional
Architecture: $architecture
Maintainer: Open Horned Rat project <noreply@github.com>
Depends: libc6 (>= 2.36), libgl1, libx11-6
Description: Open Horned Rat launcher and engine for Shadow of the Horned Rat
 An open-source engine for a legally owned copy of Warhammer: Shadow of the
 Horned Rat. Original game files are not included.
EOF

install -d dist/debian
dpkg-deb --build --root-owner-group "$stage" "dist/debian/ohr-engine_${version}_${architecture}.deb"
