You are to carry out edits to source latex. You'll receive a comment with the description of the edit to carry out and the corresponding latex source code to change. Please use only ASCII characters, and just output the edited latex code inside a verbatim codeblock and nothing else. 

comment:
```text
insert MSCs Primary 2591, 39E01 Secondary E8510
```

latex:
```latex
\title[Bicombing MCG and Teich via stable cubical intervals]{Bicombing the mapping class group and Teichm\"uller space via stable cubical intervals}

\author{Matthew Gentry Durham}
\address{Department of Mathematics and Statistics, CUNY Hunter College, New York, NY }
\email{matthew.durham@hunter.edu}
```


RESPONSE

```latex
\title[Bicombing MCG and Teich via stable cubical intervals]{Bicombing the mapping class group and Teichm\"uller space via stable cubical intervals}

\author{Matthew Gentry Durham}
\address{Department of Mathematics and Statistics, CUNY Hunter College, New York, NY }
\email{matthew.durham@hunter.edu}

\subjclass[2020]{Primary 2591, 39E01; Secondary E8510}

```






comment:
```text
COMP: question and assumption environments should have upright text, not italic, and bold headings per journal style
```

latex:
```latex
 \newtheorem{theorem}{Theorem}[section]
  \newtheorem{proposition}[theorem]{Proposition}
    \newtheorem{convention}[theorem]{Convention}
      \newtheorem{construction}[theorem]{Construction}
         \newtheorem{assumption}[theorem]{Assumption}


  \newtheorem{corollary}[theorem]{Corollary}
  \newtheorem{lemma}[theorem]{Lemma}
  \newtheorem{conjecture}[theorem]{Conjecture}
  \newtheorem{problem}[theorem]{Problem}
  \newtheorem{question}[theorem]{Question}
  \newtheorem{axiom}[theorem]{Axiom}


  \newtheorem{introthm}{Theorem}
  \newtheorem{introcor}[introthm]{Corollary}
  \renewcommand{\theintrothm}{\Alph{introthm}}
  \renewcommand{\theintrocor}{\Alph{introcor}}

  \theoremstyle{definition}
  \newtheorem{definition}[theorem]{Definition}
  \newtheorem{claim}[theorem]{Claim}
  \newtheorem{subclaim}[theorem]{Subclaim}
  \newtheorem*{claim*}{Claim}
  \newtheorem{exercise}[theorem]{Exercise}
  \newtheorem{example}[theorem]{Example}
    \newtheorem{notation}[theorem]{Notation}

  \newtheorem{fact}[theorem]{Fact}
  \newtheorem*{question*}{Question}
  \newtheorem*{answer*}{Answer}
  \newtheorem*{application*}{Application}

  \theoremstyle{remark}
  \newtheorem{remark}[theorem]{Remark}
  \newtheorem*{remark*}{Remark}
    \newtheorem{fiddly}[theorem]{Fiddly Bit}
```





