#!/usr/bin/env bash
# Build AppImage + .deb + .rpm from the PyInstaller bundle.
# Usage: packaging/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION=$(sed -nE 's/^version = "([^"]+)"/\1/p' pyproject.toml | head -1)
PKG="openorbital"
TOOLDIR="$ROOT/packaging/tools"
APPIMAGETOOL="$TOOLDIR/appimagetool"

mkdir -p "$TOOLDIR" dist_pkgs

# --- 0. appimagetool 준비 (없으면 다운로드) ------------------------------------
if [ ! -x "$APPIMAGETOOL" ]; then
  echo "==> appimagetool 다운로드"
  curl -fL -o "$APPIMAGETOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$APPIMAGETOOL"
fi

# --- 1. PyInstaller 번들 -------------------------------------------------------
echo "==> PyInstaller 빌드"
rm -rf build dist
./.venv/bin/pyinstaller --noconfirm packaging/pyinstaller.spec --distpath dist --workpath build

# --- 2. 아이콘 준비 -------------------------------------------------------------
echo "==> 아이콘 리사이즈"
mkdir -p packaging/icons
for size in 128 256 512; do
  convert logo.png -resize "${size}x${size}" "packaging/icons/${PKG}-${size}.png"
done

# --- 3. AppImage ---------------------------------------------------------------
echo "==> AppImage 빌드"
rm -rf packaging/AppDir
mkdir -p packaging/AppDir/usr/bin
cp -a "dist/${PKG}/." packaging/AppDir/usr/bin/
cp "packaging/${PKG}.desktop" "packaging/AppDir/${PKG}.desktop"
cp "packaging/icons/${PKG}-256.png" "packaging/AppDir/${PKG}.png"
cat > packaging/AppDir/AppRun << EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
exec "\${HERE}/usr/bin/${PKG}" "\$@"
EOF
chmod +x packaging/AppDir/AppRun
ARCH=x86_64 "$APPIMAGETOOL" packaging/AppDir "dist_pkgs/${PKG}-${VERSION}-x86_64.AppImage"

# --- 4. .deb ---------------------------------------------------------------
echo "==> .deb 빌드"
rm -rf packaging/deb
DEBROOT="packaging/deb"
mkdir -p "$DEBROOT/DEBIAN" \
         "$DEBROOT/usr/lib/${PKG}" \
         "$DEBROOT/usr/bin" \
         "$DEBROOT/usr/share/applications" \
         "$DEBROOT/usr/share/icons/hicolor/128x128/apps" \
         "$DEBROOT/usr/share/icons/hicolor/256x256/apps" \
         "$DEBROOT/usr/share/icons/hicolor/512x512/apps"

cp -a "dist/${PKG}/." "$DEBROOT/usr/lib/${PKG}/"
ln -s "../lib/${PKG}/${PKG}" "$DEBROOT/usr/bin/${PKG}"
cp "packaging/${PKG}.desktop" "$DEBROOT/usr/share/applications/${PKG}.desktop"
cp "packaging/icons/${PKG}-128.png" "$DEBROOT/usr/share/icons/hicolor/128x128/apps/${PKG}.png"
cp "packaging/icons/${PKG}-256.png" "$DEBROOT/usr/share/icons/hicolor/256x256/apps/${PKG}.png"
cp "packaging/icons/${PKG}-512.png" "$DEBROOT/usr/share/icons/hicolor/512x512/apps/${PKG}.png"

INSTALLED_SIZE=$(du -sk "$DEBROOT/usr" | cut -f1)
cat > "$DEBROOT/DEBIAN/control" << EOF
Package: ${PKG}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Installed-Size: ${INSTALLED_SIZE}
Maintainer: OpenOrbital <noreply@example.com>
Description: Desktop manager for your own orbi.kr posts and comments
 View, back up, or delete your own orbi.kr posts through a checkbox-driven
 desktop GUI. Dry-run is on by default and deletions require typed
 confirmation.
EOF
chmod 0644 "$DEBROOT/DEBIAN/control"

( cd "$DEBROOT" && find usr -type f -print0 | sort -z | xargs -0 md5sum > DEBIAN/md5sums )
chmod 0644 "$DEBROOT/DEBIAN/md5sums"

echo "2.0" > "$DEBROOT/debian-binary"
tar --numeric-owner --owner=0 --group=0 -C "$DEBROOT/DEBIAN" -czf "$DEBROOT/control.tar.gz" .
tar --numeric-owner --owner=0 --group=0 -C "$DEBROOT" -czf "$DEBROOT/data.tar.gz" usr

rm -f "dist_pkgs/${PKG}_${VERSION}_amd64.deb"
ar rc "dist_pkgs/${PKG}_${VERSION}_amd64.deb" \
  "$DEBROOT/debian-binary" "$DEBROOT/control.tar.gz" "$DEBROOT/data.tar.gz"

# --- 5. .rpm ---------------------------------------------------------------
echo "==> .rpm 빌드"
RPMTOP="$ROOT/build/rpmbuild"
rm -rf "$RPMTOP"
mkdir -p "$RPMTOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS,BUILDROOT}

RPMSRC="$ROOT/build/rpmsrc/${PKG}-${VERSION}"
rm -rf "$(dirname "$RPMSRC")"
mkdir -p "$RPMSRC"
cp -a "$DEBROOT/usr" "$RPMSRC/usr"
tar czf "$RPMTOP/SOURCES/${PKG}-${VERSION}.tar.gz" -C "$(dirname "$RPMSRC")" "${PKG}-${VERSION}"

sed "s/^Version:.*/Version:        ${VERSION}/" "packaging/rpm/${PKG}.spec" \
  > "$RPMTOP/SPECS/${PKG}.spec"

rpmbuild --define "_topdir $RPMTOP" -bb "$RPMTOP/SPECS/${PKG}.spec"
cp "$RPMTOP"/RPMS/x86_64/*.rpm dist_pkgs/

echo "==> 완료: dist_pkgs/"
ls -la dist_pkgs/
