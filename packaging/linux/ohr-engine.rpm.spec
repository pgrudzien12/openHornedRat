%global debug_package %{nil}

Name:           ohr-engine
Version:        %{pkg_version}
Release:        1%{?dist}
Summary:        Open Horned Rat launcher and engine for Shadow of the Horned Rat
License:        GPL-3.0-or-later
URL:            https://github.com/pgrudzien12/openHornedRat
AutoReqProv:    no
Requires:       glibc >= 2.34, libglvnd-glx, libX11
Recommends:     innoextract

%description
An open-source engine for a legally owned copy of Warhammer: Shadow of the
Horned Rat. Original game files are not included.

%prep
:

%build
:

%install
mkdir -p "%{buildroot}/opt/ohr-engine" "%{buildroot}%{_bindir}" \
    "%{buildroot}%{_datadir}/applications" "%{buildroot}%{_datadir}/doc/ohr-engine"
cp -a "%{bundle_dir}/." "%{buildroot}/opt/ohr-engine/"
install -m 755 "%{repository_root}/packaging/linux/ohr-engine-launch" "%{buildroot}%{_bindir}/ohr-engine-launch"
ln -s /opt/ohr-engine/ohr-engine "%{buildroot}%{_bindir}/ohr-engine"
install -m 644 "%{repository_root}/packaging/linux/ohr-engine.desktop" "%{buildroot}%{_datadir}/applications/ohr-engine.desktop"
for size in 16 24 32 48 64 128 256 512; do
    install -d "%{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps"
    install -m 644 "%{repository_root}/whshr/icons/ohr-${size}.png" "%{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/ohr-engine.png"
done
install -m 644 "%{repository_root}/LICENSE" "%{buildroot}%{_datadir}/doc/ohr-engine/LICENSE"
install -m 644 "%{repository_root}/LEGAL.md" "%{buildroot}%{_datadir}/doc/ohr-engine/LEGAL.md"
install -m 644 "%{repository_root}/packaging/THIRD_PARTY_NOTICES.md" "%{buildroot}%{_datadir}/doc/ohr-engine/THIRD_PARTY_NOTICES.md"
install -m 644 "%{repository_root}/packaging/licenses/LGPL-2.1.txt" "%{buildroot}%{_datadir}/doc/ohr-engine/LGPL-2.1.txt"
install -m 644 "%{repository_root}/packaging/licenses/Apache-2.0.txt" "%{buildroot}%{_datadir}/doc/ohr-engine/Apache-2.0.txt"
install -d "%{buildroot}%{_datadir}/doc/ohr-engine/third-party-licenses"
install -m 644 "%{repository_root}"/packaging/licenses/third-party/* "%{buildroot}%{_datadir}/doc/ohr-engine/third-party-licenses/"

%files
/opt/ohr-engine
%{_bindir}/ohr-engine
%{_bindir}/ohr-engine-launch
%{_datadir}/applications/ohr-engine.desktop
%{_datadir}/icons/hicolor/*/apps/ohr-engine.png
%dir %{_datadir}/doc/ohr-engine
%license %{_datadir}/doc/ohr-engine/LICENSE
%{_datadir}/doc/ohr-engine/LEGAL.md
%{_datadir}/doc/ohr-engine/THIRD_PARTY_NOTICES.md
%{_datadir}/doc/ohr-engine/LGPL-2.1.txt
%{_datadir}/doc/ohr-engine/Apache-2.0.txt
%{_datadir}/doc/ohr-engine/third-party-licenses
