{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.programs.monique;
in
{
  options.programs.monique = {
    enable = lib.mkEnableOption "Monique monitor configurator";

    package = lib.mkOption {
      type = lib.types.nullOr lib.types.package;
      default = null;
      description = "The Monique package to install.";
    };

    enablePolkit = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = ''
        Install the polkit rule to allow writing to
        /usr/share/sddm/scripts/Xsetup and /etc/greetd/monique-monitors.conf
        without requiring a password.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = lib.optional (cfg.package != null) cfg.package;

    environment.etc."polkit-1/rules.d/60-com.github.monique.rules" = lib.mkIf cfg.enablePolkit {
      text = ''
        polkit.addRule(function(action, subject) {
          if (action.id === "org.freedesktop.policykit.exec" &&
              action.lookup("program") === "${pkgs.coreutils}/bin/tee" &&
              (action.lookup("command_line").indexOf("/usr/share/sddm/scripts/Xsetup") !== -1 ||
               action.lookup("command_line").indexOf("/etc/greetd/monique-monitors.conf") !== -1) &&
              subject.active === true &&
              subject.local  === true) {
            return polkit.Result.YES;
          }
        });
      '';
    };
  };
}
