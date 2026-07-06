{
  lib,
  python3Packages,
  gtk4,
  libadwaita,
  gobject-introspection,
  wrapGAppsHook4,
}:
let
  version = (fromTOML (builtins.readFile ../pyproject.toml)).project.version;
in
python3Packages.buildPythonPackage {
  pname = "monique";
  inherit version;
  format = "pyproject";

  src = lib.cleanSource ./..;

  nativeBuildInputs = [
    python3Packages.setuptools
    wrapGAppsHook4
    gobject-introspection
  ];

  buildInputs = [
    gtk4
    libadwaita
  ];

  propagatedBuildInputs = with python3Packages; [
    pygobject3
    pyudev
  ];

  postInstall = ''
    install -Dm644 data/com.github.monique.desktop \
      $out/share/applications/com.github.monique.desktop
    install -Dm644 data/com.github.monique.svg \
      $out/share/icons/hicolor/scalable/apps/com.github.monique.svg
    install -Dm644 data/moniqued.service \
      $out/lib/systemd/user/moniqued.service
  '';

  doCheck = false;

  meta = {
    description = "MONitor Integrated QUick Editor — graphical monitor configurator for Hyprland and Sway";
    homepage = "https://github.com/ToRvaLDz/monique";
    license = lib.licenses.gpl3Plus;
    platforms = lib.platforms.linux;
    mainProgram = "monique";
  };
}
