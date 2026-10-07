#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: $0 VERSION" >&2
    exit 2
fi
version=$1
case "$version" in
    *[!a-zA-Z0-9.+~-]*|"") echo "invalid RPM version: $version" >&2; exit 2 ;;
esac
# RPM uses a tilde for prereleases and does not permit a hyphen in Version.
rpm_version=$(printf '%s' "$version" | tr '-' '~')

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repository_root"
if [ ! -x dist/ohr-engine/ohr-engine ]; then
    echo "build dist/ohr-engine first with packaging/linux/ohr-engine.spec" >&2
    exit 2
fi
command -v rpmbuild >/dev/null 2>&1 || {
    echo "rpmbuild is required" >&2
    exit 2
}

rm -rf build/rpm/RPMS build/rpm/BUILDROOT
for directory in BUILD BUILDROOT RPMS SOURCES SPECS SRPMS; do
    install -d "build/rpm/$directory"
done
install -d dist/rpm
rm -f dist/rpm/*.rpm
rpmbuild -bb \
    --define "_topdir $repository_root/build/rpm" \
    --define "pkg_version $rpm_version" \
    --define "bundle_dir $repository_root/dist/ohr-engine" \
    --define "repository_root $repository_root" \
    packaging/linux/ohr-engine.rpm.spec
set -- build/rpm/RPMS/*/*.rpm
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo "expected exactly one RPM in build/rpm/RPMS" >&2
    exit 1
fi
cp -f "$1" dist/rpm/
