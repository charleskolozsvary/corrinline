# Package management: pixi
Install pixi following the steps here: https://pixi.prefix.dev/latest/installation/

Here's what I did to set up the project environment. It's extremely simple.
```shell
pixi init [project name] --format pyproject
pixi add python=3.14
pixi add [conda-forge available package]
pixi add --pypi [only-PyPi available package]
```

Pixi is a conda first manager, so it will import a package from conda-forge before anywhere else. If a package is not available in conda-forge, you can install it from PyPI, the python package index, which has a much lower barrier to entry and therefore many many more packages.
