{
  description = "A NixOS background service for extracting BSP data in Source games.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    dream2nix.url = "github:nix-community/dream2nix";
  };

  outputs =
    {
      self,
      nixpkgs,
      dream2nix,
    }:
    let
      nixosModule =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        {
          options.services.bsp-casefolding-workaround = {
            enable = lib.mkEnableOption "BSP casefolding workaround service";

            watch_dirs = lib.mkOption {
              type = lib.types.listOf lib.types.str;
              default = null;
              example = lib.options.literalExpression ''
                [
                                  "/home/user/.steam/steamapps/common/Counter-Strike Source/cstrike/download"
                                ];'';
              description = "A list of download directories to watch for BSPs.";
            };
          };

          config = lib.mkIf config.services.bsp-casefolding-workaround.enable {
            systemd.user.services.bsp-casefolding-workaround = {
              Unit = {
                Description = "BSP casefolding workaround service";
              };
              Install = {
                WantedBy = [ "default.target" ];
              };
              Service = {
                ExecStart = "${
                  self.packages.${pkgs.system}.default
                }/bin/bsp-casefolding-workaround ${lib.escapeShellArgs config.services.bsp-casefolding-workaround.watch_dirs}";
                Restart = "always";
                Type = "simple";
              };
            };
          };
        };
      eachSystem = nixpkgs.lib.genAttrs [ "x86_64-linux" ];
    in
    {
      packages = eachSystem (system: {
        default = dream2nix.lib.evalModules {
          packageSets.nixpkgs = nixpkgs.legacyPackages.${system};
          modules = [
            ./default.nix
            {
              paths.projectRoot = ./.;
              paths.projectRootFile = "flake.nix";
              paths.package = ./.;
            }
          ];
        };
      });

      nixosModules.default = nixosModule;
    };
}
