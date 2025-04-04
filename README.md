# BSP Casefolding Workaround (Nix)

**Warning**: This is not ready for use yet. Please wait until the `stable` branch exists before adding to any configurations.

This is a background service for NixOS to run a modified version of [Gedweb's BSP Extractor](https://github.com/Gedweb/Source-Linux-BSP-Case-Folding).

There are some modifications to Gedweb's script that I intend to file a PR upstream:
- Skip maps with invalidly named subdirectories (an example I had was one named `e:`).
- Support watching multiple Source games.

## Acknowledgments

- To [@Gedweb](https://github.com/Gedweb) for his [BSP extraction + file watching script](https://github.com/Gedweb/Source-Linux-BSP-Case-Folding).
- Michael Lynch for inspiration from his post "[Run a Simple Go Web Service on NixOS](https://mtlynch.io/notes/simple-go-web-service-nixos/)".