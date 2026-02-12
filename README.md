# texpdfedits
This python project modifies LaTeX source files to aid and automate any correction workflow where copyedits are provided by an annotated PDF.

Normal processing of the changes involves reviewing the PDF and finding and fixing the corresponding LaTeX one annotation at a time. There are tools like SyncTeX to speed up the navigation between output and source, but even then the process is time-consuming and tedious.

The script this project provides places the corrections directly into the source LaTeX as comments and carries out whatever corrections it can automatically. See [annotation_guidelines.md](notes/annotation_guidelines.md) for more on the autocorrections.

## Tools/Tech
The major dependencies of this project are 
- [pixi](https://pixi.prefix.dev/latest/installation/) for the python package management
- [diff-pdf](https://github.com/vslavik/diff-pdf) for comparing PDF files
- [TeXLive](https://www.tug.org/texlive/) for compiling the LaTeX

## Install
Install `pixi` (the python package manager) following instructions at https://pixi.prefix.dev/latest/installation/

Install [`diff-pdf`](https://github.com/vslavik/diff-pdf)

Install TeX Live if you don't already have a LaTeX distribution.

---

Clone this repository on your machine.

Navigate to the repository and run
```shell
pixi init
```

Now you should be able to run
```shell
pixi shell
python -m texpdfedits.comment_corr
```

and follow its usage directions.

To run a single script anywhere on your machine, you could create a simple bash script that looks like
```bash
#!/bin/bash

pixi run --manifest-path <PATH TO PROJECT DIR OR pyproject.toml> python -m texpdfedits.comment_corr "$@"
```

But clearly there is room for improvement for configuring the script which still needs to be done.





