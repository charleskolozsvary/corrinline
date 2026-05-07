# `corrinline`
## Description
`corrinline` is a command line tool which modifies LaTeX source files to aid and partially automate a document correction workflow where copyedits are specified by an annotated PDF and changes are made directly to the LaTeX source.

### Motivation
A typical workflow involves viewing the corrections from the annotated PDF in one window and the LaTeX source in another, selecting an annotation, interpreting the copyedit, tracking down where the change needs to be made in the LaTeX source, composing the change, compiling the source, and verifying that the change was made correctly. This is done for every individual annotation one at a time. There are simple ways to save some time in this process: saving the compilation of the source and verification of the changes to the very end, or using [SyncTeX](https://www.tug.org/TUGboat/tb29-3/tb93laurens.pdf) to speed up navigatoin between the source and output, but, even then, the processs is time-consuming and tedious. 

`corrinline` places the corrections directly into the source LaTeX as comments and carries out whatever corrections it can automatically.

## Installation
If you don't already have a LaTeX distribution, download the latest version of TeX Live at https://www.tug.org/texlive/.
### Linux/Mac
1. Install pixi (the python package and dependency manager): https://pixi.prefix.dev/latest/installation/

2. Install `diff-pdf` (CL tool for comparing PDFs): https://github.com/vslavik/diff-pdf

3. Clone this repo to your machine

4. Run `./install.sh [binary install directory]`, e.g., `./install.sh /usr/local/bin/`

Verify it is installed properly with `corrinline -h`. You should see the usage message.

## Usage
From the shell, run
```shell
corrinline ANNOTATED_PDF_FILE LATEX_FILE
```
from anywhere on your machine.

When the program is finished, it will have written a new file, `[latex_source]_inlined.tex`. This file has the annotations in `[annotated_PDF]` written directly into the source LaTeX as comments (so the source output is unchanged). There are also many options, including `--auto` to carry out compatible corrections automatically. See [option_usage.md](./notes/option_usage.md) for complete details on how to use them, but hopefully their help descriptions are sufficient.

## Examples
Example annotated PDFs can be found at `./AnnotatedPDFs` with corresponding LaTeX sources at `./TeX`.

### Results
Here's part of `arxiv5_inlined.tex`, the output of `corrinline arxiv5_ann.pdf arxiv5.tex`:
```latex
%% Correction 28 [ ]
%% Annotated text: "fr−2 given by<Remove>:</Remove>"
%% Comment: "" 
%% 
%% START of correction 28
given by:
\begin{equation}
    \label{eq:GD_hier}
\frac{\partial L}{\partial T_n}=\lambda^{n-1}[(L^{n/r})_+,L],\quad n\geq 1.
\end{equation}

Denote %%
%% END of correction 28
by $L$ the solution of the system specified by the initial %%
%% Correction 29 [ ]
%% Annotated text: "x + λ rrx<Replace>,</Replace>"
%% Comment: "." 
%% 
%% START of correction 29
condition
\begin{equation}\label{eq:init_cond_L}
L|_{T_{\geq 2}=0}=\partial_x^r+\lambda^{-r}rx,
\end{equation}
Witten's %%
%% END of correction 29
```

And here's the same snippet in `arxiv5_autocorrected.tex`, which is outputted when the `--autocorrect` option is present.
```latex
%% Correction 28 (auto) [✓]
%% Annotated text: "fr−2 given by<Remove>:</Remove>"
%% Comment: "" 
%% 
%% START of correction 28
given by
\begin{equation}
    \label{eq:GD_hier}
\frac{\partial L}{\partial T_n}=\lambda^{n-1}[(L^{n/r})_+,L],\quad n\geq 1.
\end{equation}

Denote %%
%% END of correction 28
by $L$ the solution of the system specified by the initial %%
%% Correction 29 (auto) [✓]
%% Annotated text: "x + λ rrx<Replace>,</Replace>"
%% Comment: "." 
%% 
%% START of correction 29
condition
\begin{equation}\label{eq:init_cond_L}
L|_{T_{\geq 2}=0}=\partial_x^r+\lambda^{-r}rx.
\end{equation}
Witten's %%
%% END of correction 29
```

For this particular paper, **293/422 corrections were completed automatically!** 

Finally, here are two pages side by side, one from `arxiv5_ann.pdf`, the other from `arxiv5_autocorrected.pdf`, demonstrating the result of several automatic corrections.

<img width="408" alt="annotated" src="https://github.com/user-attachments/assets/912e4c1d-efb9-4fa4-a404-0ced2869e2c1" />
<img width="408" alt="autocorrected" src="https://github.com/user-attachments/assets/4dcc4ff8-d3e1-4300-9262-3c401e3fd1e5" />

You might notice that one of the automatic corrections resulted in "satisfyit." That happened because the contents of the comment for that correction was just "it" (no space before).

## Assumptions and limitations
### Unchanged LaTeX
For best results, the LaTeX souce should be unchanged since the PDF it generated was annotated. Even relatively small changes could change the pagination of the document and cause an entire cascade of differences between what the source then renders and the annotated PDF. If the source and and the annotatated PDF are mostly in sync, the `--source-start-page` option might be of use. It, along with the other options, are discussed in [option_usage.md](./notes/option_usage.md).

### Annotations are precise
As shown in the above screenshots, the contents of insertion and replacement text are interpreted literally. Additionally, since 'highlight' is too general an annotation, they will never be done automatically, even if they are used in place of a replacement or strikeout annotation. So dedicated annotations must be used for best results.
