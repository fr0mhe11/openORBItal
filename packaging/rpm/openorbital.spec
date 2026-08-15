%global __requires_exclude_from ^/usr/lib/openorbital/.*$
%global __provides_exclude_from ^/usr/lib/openorbital/.*$
%global debug_package %{nil}
%global __os_install_post %{nil}

Name:           openorbital
Version:        0.1.0
Release:        1%{?dist}
Summary:        Desktop manager for your own orbi.kr posts and comments
License:        Proprietary
URL:            https://orbi.kr
Source0:        %{name}-%{version}.tar.gz
BuildArch:      x86_64

%description
View, back up, or delete your own orbi.kr posts through a checkbox-driven
desktop GUI. Dry-run is on by default and deletions require typed
confirmation.

%prep
%setup -q

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a usr %{buildroot}/

%files
/usr/bin/openorbital
/usr/lib/openorbital
/usr/share/applications/openorbital.desktop
/usr/share/icons/hicolor/128x128/apps/openorbital.png
/usr/share/icons/hicolor/256x256/apps/openorbital.png
/usr/share/icons/hicolor/512x512/apps/openorbital.png

%changelog
* Sat Aug 15 2026 OpenOrbital <noreply@example.com> - 0.1.0-1
- Initial packaged release
