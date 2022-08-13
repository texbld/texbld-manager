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
          buildInputs = with pkgs; [ python3 python3Packages.autopep8 scc ];
        };
        formatter = nixpkgs.legacyPackages."${system}".nixfmt;
      });
}
