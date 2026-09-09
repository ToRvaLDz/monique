# Maintainer: Marco Migozzi <torvaldz@gmail.com>
pkgname=monique
pkgver=0.8.0
pkgrel=1
pkgdesc='MONitor Integrated QUick Editor — graphical monitor configurator for Hyprland, Sway and Niri'
arch=('any')
license=('GPL-3.0-or-later')
depends=(
    'python'
    'python-gobject'
    'gtk4'
    'libadwaita'
)
optdepends=(
    'hyprland: Hyprland compositor support'
    'sway: Sway compositor support'
    'niri: Niri compositor support'
    'sddm: login screen layout sync via Xsetup'
    'polkit: passwordless SDDM Xsetup writes'
    'python-pyudev: hardware hotplug detection for Niri'
)
makedepends=(
    'python-build'
    'python-installer'
    'python-setuptools'
    'python-wheel'
)
source=()

build() {
    cd "$startdir"
    # dist/ persiste tra i build locali: i wheel di versioni precedenti
    # farebbero collidere l'installazione in package()
    rm -rf dist/
    python -m build --wheel --no-isolation
}

package() {
    cd "$startdir"
    python -m installer --destdir="$pkgdir" "dist/$pkgname-$pkgver-py3-none-any.whl"

    # Desktop entry
    install -Dm644 data/com.github.monique.desktop \
        "$pkgdir/usr/share/applications/com.github.monique.desktop"

    # Systemd user service
    install -Dm644 data/moniqued.service \
        "$pkgdir/usr/lib/systemd/user/moniqued.service"

    # Application icon
    install -Dm644 data/com.github.monique.svg \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/com.github.monique.svg"

    # Polkit rule for passwordless SDDM Xsetup writes
    install -Dm644 data/com.github.monique.rules \
        "$pkgdir/usr/share/polkit-1/rules.d/60-com.github.monique.rules"

    # License
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
