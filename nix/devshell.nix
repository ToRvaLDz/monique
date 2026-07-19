{
  pkgs,
  monique,
}:
pkgs.mkShell {
  inputsFrom = [ monique ];

  packages = with pkgs; [
    python3
  ];
}
