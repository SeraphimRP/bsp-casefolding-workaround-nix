# BSP Casefolding Workaround (Nix)

**Warning**: This is a work-in-progress. It is functional (on my system), but odds are I haven't accounted for every quirk that could exist.

This is a background service for NixOS to run a modified version of [Gedweb's BSP Extractor](https://github.com/Gedweb/Source-Linux-BSP-Case-Folding).

There are some modifications to Gedweb's script that I intend to file a PR upstream:
- Skip maps with invalidly named subdirectories (an example I had was one named `e:`).
- Support watching multiple directories (meaning multiple Source 1 games).

## Requirements

- Must be running on nixpkgs unstable (until vpkedit eventually makes it into a stable release)
- Must have a NixOS configuration managed by flakes.
- Must have home-manager (also managed by flakes).

## Installation

*Note: Nix is a funky language, there are many ways that one has arranged their configuration. This is one of many possibilities for installation, you know your system best. You don't need to pay attention to nix-colors, nixvim, and lanzaboote in these examples. This is just what I have in my own system configuration, it is not required for this workaround.*

Install `vpkedit` through an `environment.systemPackages = with pkgs; []` call somewhere in your Nix configuration.

In your configuration's flake.nix, add the following to your `inputs`:

```nix
bsp-casefolding-workaround = { url = "github:SeraphimRP/bsp-casefolding-workaround-nix/stable"; };
```

Then make the module available to your homeManagerConfiguration, in my case it is like:

```nix
outputs = { nixpkgs, home-manager, nix-colors, nixvim, lanzaboote, bsp-casefolding-workaround, ... } @ inputs: {
    nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
        specialArgs = { inherit inputs nixvim lanzaboote; };
        modules = [
            ...
            ];
        };

    homeConfigurations."srp@nixos" = home-manager.lib.homeManagerConfiguration {
        pkgs = nixpkgs.legacyPackages.x86_64-linux;
        extraSpecialArgs = { inherit inputs nix-colors nixvim bsp-casefolding-workaround; };
        modules = [
            ./home.nix
            ./nixpkgs.nix
        ];
    };

    home-manager.backupFileExtension = "bak";	
    home-manager.useGlobalPkgs = true;
    home-manager.useUserPackages = true;
};
```

And in `home.nix` I have the following:

```nix
{ config, inputs, pkgs, nix-colors, nixvim, bsp-casefolding-workaround, ... }:

{
    imports = [ nix-colors.homeManagerModules.default nixvim.homeManagerModules.nixvim bsp-casefolding-workaround.nixosModules.default ];

    ...

    services.bsp-casefolding-workaround = {
        enable = true;
        
        watch_dirs = [
            "/home/srp/media/Second M.2/SteamLibrary/steamapps/common/Counter-Strike Source/cstrike/download"
            "/home/srp/media/Second M.2/test"
        ];
    };

    ...
}
```



## Acknowledgments

- To [@Gedweb](https://github.com/Gedweb) for his [BSP extraction + file watching script](https://github.com/Gedweb/Source-Linux-BSP-Case-Folding).
- Michael Lynch for inspiration from his post "[Run a Simple Go Web Service on NixOS](https://mtlynch.io/notes/simple-go-web-service-nixos/)".