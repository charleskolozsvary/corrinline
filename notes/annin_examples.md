TO DO 

# Examples
Example annotated PDFs can be found at `./AnnotatedPDFs` with corresponding LaTeX sources at `./TeX`.

## Results
Here's part of `arxiv5_inlined.tex`, the output of `annin arxiv5_ann.pdf arxiv5.tex`:
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

<img width="408" alt="annotated" src="https://github.com/user-attachments/assets/912e4c1d-efb9-4fa4-a404-0ced2869e2c1"/>
<img width="408" alt="autocorrected" src="https://github.com/user-attachments/assets/4dcc4ff8-d3e1-4300-9262-3c401e3fd1e5"/>

You might notice that one of the automatic corrections resulted in "satisfyit." That happened because the contents of the comment for that correction was just "it" (no space before).
