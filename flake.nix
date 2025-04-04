{
    description = "A NixOS background service for extracting BSP data in Source games.";

    inputs = {
        nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
        flake-utils.url = "github:numtide/flake-utils";
        mach-nix.url = "github:davhau/mach-nix";
    }

    outputs = { self, nixpkgs, mach-nix, flake-utils }: let nixosModule = { config, lib, pkgs, ... }: {
        options.services.bsp-casefolding-workaround = {
            enable = lib.mkEnableOption "BSP casefolding workaround service";

            watch_dirs = lib.mkOption {
                type = lib.types.listOf path;
                example = lib.options.literalExpression ''[
                  "/home/user/.steam/steamapps/common/Counter-Strike\ Source/cstrike/download"
                ];'';
                description = "A list of download directories to watch for BSPs.";
            };
            
            config = lib.mkIf config.services.bsp-casefolding-workaround.enable {
                systemd.services.bsp-casefolding-workaround = {
                    description = "BSP casefolding workaround service";
                    wantedBy = ["multi-user.target"];
                    after = ["network.target"];
                    serviceConfig = {
                        ExecStart = "${self.packages.${pkgs.system}.default}/bin/bsp-casefolding-workaround ${lib.strings.concatStringsSep " " lib.option.getValues [ watch_dirs ]}";
                        Restart = "always";
                        Type = "simple";
                        DynamicUser = "yes";
                    };
                };
            };
        };
        let pythonVersion = "python313"; in flake-utils.lib.eachDefaultSystem (system:
            let
                pkgs = nixpkgs.legacyPackages.${system};
                mach = mach-nix.lib.${system};

                pythonApp = mach.buildPythonApplication ./.;
                pythonAppEnv = mach.mkPython {
                    python = pythonVersion;
                    requirements = builtins.readFile ./requirements.txt;
                };
            in
            rec
            {
                packages = {
                    pythonPkg = pythonApp;
                    default = packages.pythonPkg;
                };

                apps.default = {
                    type = "app";
                    program = "${packages.pythonPkg}/bin/bsp-casefolding-workaround";
                };
            };
        )
    }
}