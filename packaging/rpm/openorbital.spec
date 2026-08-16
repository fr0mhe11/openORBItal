%global __requires_exclude_from ^/usr/lib/openorbital/.*$
%global __provides_exclude_from ^/usr/lib/openorbital/.*$
%global debug_package %{nil}
%global __os_install_post %{nil}

Name:           openorbital
Version:        0.1.0
Release:        1%{?dist}
Summary:        Desktop manager for your own orbi.kr posts and comments
License:        GPL-3.0-only
URL:            https://github.com/fr0mhe11/openORBItal
Source0:        %{name}-%{version}.tar.gz
BuildArch:      x86_64

%description
View, back up, or delete your own orbi.kr posts through a checkbox-driven
desktop GUI. Deletions are irreversible and require the exact number of
selected rows to be typed before they run; an optional dry-run reports
what would be sent without sending it.

%prep
%setup -q

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a usr %{buildroot}/

%files
%license /usr/share/licenses/openorbital/LICENSE
/usr/share/doc/openorbital/copyright
/usr/bin/openorbital
/usr/lib/openorbital
/usr/share/applications/openorbital.desktop
/usr/share/icons/hicolor/128x128/apps/openorbital.png
/usr/share/icons/hicolor/256x256/apps/openorbital.png
/usr/share/icons/hicolor/512x512/apps/openorbital.png

%changelog
* Sun Aug 16 2026 OpenOrbital <noreply@example.com> - 0.2.0-1
- Treat a redirected delete as a lost session instead of a success
- Ship the GPL-3.0 text and correct the License tag
- Describe the delete guardrails as they actually behave

* Sat Aug 15 2026 OpenOrbital <noreply@example.com> - 0.1.0-1
- Initial packaged release
