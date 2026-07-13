{
  description = "MONitor Integrated QUick Editor — graphical monitor configurator for Hyprland and Sway";

  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-unstable/nixexprs.tar.xz";

  outputs =
    { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;

      forEachSystem =
        perSystem:
        lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (
          system: perSystem nixpkgs.legacyPackages.${system} system
        );
    in
    {
      overlays.default = final: _prev: {
        monique = final.callPackage ./nix/package.nix { };
      };

      packages = forEachSystem (
        pkgs: _system: {
          default = pkgs.callPackage ./nix/package.nix { };
        }
      );

      devShells = forEachSystem (
        pkgs: system: {
          default = pkgs.callPackage ./nix/devshell.nix {
            monique = self.packages.${system}.default;
          };
        }
      );

      nixosModules.default =
        { pkgs, lib, ... }:
        {
          imports = [ ./nix/nixos-module.nix ];
          programs.monique.package = lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        };
    };
}
