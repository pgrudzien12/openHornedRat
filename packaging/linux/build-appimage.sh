#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: APPIMAGETOOL=/path/to/appimagetool APPIMAGE_RUNTIME_FILE=/path/to/runtime $0 VERSION" >&2
    exit 2
fi
version=$1
case "$version" in
    *[!a-zA-Z0-9.+~_-]*|"") echo "invalid AppImage version: $version" >&2; exit 2 ;;
esac
: "${APPIMAGETOOL:?set APPIMAGETOOL to the appimagetool executable}"
: "${APPIMAGE_RUNTIME_FILE:?set APPIMAGE_RUNTIME_FILE to a type 2 runtime}"

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"
if [ ! -x dist/ohr-engine/ohr-engine ]; then
    echo "build dist/ohr-engine first with packaging/linux/ohr-engine.spec" >&2
    exit 2
fi
if [ ! -x "$APPIMAGETOOL" ] || [ ! -f "$APPIMAGE_RUNTIME_FILE" ]; then
    echo "appimagetool or type 2 runtime is missing" >&2
    exit 2
fi

appdir=build/appimage/ohr-engine.AppDir
rm -rf "$appdir"
install -d "$appdir/usr/bin/ohr-engine" "$appdir/usr/share/applications" \
    "$appdir/usr/share/doc/ohr-engine" dist/appimage
rm -f dist/appimage/*.AppImage
cp -a dist/ohr-engine/. "$appdir/usr/bin/ohr-engine/"
install -m 755 packaging/linux/appimage/AppRun "$appdir/AppRun"
install -m 644 packaging/linux/appimage/ohr-engine.desktop "$appdir/ohr-engine.desktop"
install -m 644 packaging/linux/appimage/ohr-engine.desktop "$appdir/usr/share/applications/ohr-engine.desktop"
install -m 644 whshr/icons/ohr-256.png "$appdir/ohr-engine.png"
for size in 16 24 32 48 64 128 256 512; do
    install -d "$appdir/usr/share/icons/hicolor/${size}x${size}/apps"
    install -m 644 "whshr/icons/ohr-${size}.png" "$appdir/usr/share/icons/hicolor/${size}x${size}/apps/ohr-engine.png"
done
ln -s ohr-engine.png "$appdir/.DirIcon"
install -m 644 LICENSE "$appdir/usr/share/doc/ohr-engine/LICENSE"
install -m 644 LEGAL.md "$appdir/usr/share/doc/ohr-engine/LEGAL.md"
install -m 644 packaging/THIRD_PARTY_NOTICES.md "$appdir/usr/share/doc/ohr-engine/THIRD_PARTY_NOTICES.md"
install -m 644 packaging/licenses/LGPL-2.1.txt "$appdir/usr/share/doc/ohr-engine/LGPL-2.1.txt"
install -m 644 packaging/licenses/Apache-2.0.txt "$appdir/usr/share/doc/ohr-engine/Apache-2.0.txt"
install -d "$appdir/usr/share/doc/ohr-engine/third-party-licenses"
install -m 644 packaging/licenses/third-party/* "$appdir/usr/share/doc/ohr-engine/third-party-licenses/"

ARCH=x86_64 VERSION="$version" APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" \
    --runtime-file "$APPIMAGE_RUNTIME_FILE" "$appdir" "dist/appimage/ohr-engine-${version}-x86_64.AppImage"
