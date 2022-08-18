{
  description = "TeXbld Manager";
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = import nixpkgs { inherit system; };
      in {
        devShell = pkgs.mkShell {
          buildInputs = with pkgs; [ python39 python39Packages.autopep8 scc ];
        };
        defaultPackage = pkgs.stdenv.mkDerivation rec {
          name = "texbld-manager";
          version = "";
          src = ./.;
          buildInputs = with pkgs; [python39];
          installPhase = ''
            mkdir -p $out/bin
            cp $src/texbld-manager $out/bin
          '';
        };
        formatter = nixpkgs.legacyPackages."${system}".nixfmt;
      });
}
