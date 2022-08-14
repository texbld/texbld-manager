# TeXbld Manager

WIP tool for installing and managing different TeXbld versions.
Check TODO.md to see upcoming features of this project.

## Installation

```sh
curl -sSL https://raw.githubusercontent.com/texbld/texbld-manager/master/texbld-manager | python - setup
```

Follow the install script and add the installed directory to your $PATH.

## Upgrading

```
texbld-manager setup
```

This will install the master branch of texbld-manager from GitHub.

## Code Requirements

- Zero dependencies outside of the built-in python modules
- All code in one file (because imports are basically impossible)
