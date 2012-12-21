\usepackage[centering,paperwidth=180mm,paperheight=230mm,%
body={390pt,18.5cm},marginparsep=10pt,marginpar=50pt]{geometry}
\usepackage{color}
\usepackage{enumitem}
\usepackage{fancyvrb}
\usepackage{graphicx}
\usepackage[toc]{multitoc}
\usepackage{underscore}

\CTEXsetup[number={\thechapter}]{chapter}
\CTEXsetup[format+={\raggedleft}]{chapter}
\CTEXsetup[beforeskip={10pt}]{chapter}
\def\CTEX@chapter@aftername{\par} % \CTEXsetup[aftername={\par}]{chapter}
\CTEXsetup[format+={\raggedright}]{section}

\newfontfamily\urlfont{PT Sans Narrow}

\newcommand{\fn}[1]{\texttt{#1}}
\newcommand{\sfn}[1]{\texttt{\small #1}}
\newcommand{\kw}[1]{\textsf{#1}}
\newcommand{\myurl}[1]{{\urlfont #1}}
\newcommand{\mpar}[1]{\marginpar[\hfill\kaishu #1]{\kaishu #1}}
\renewcommand{\today}{\the\year-\the\month-\the\day}

\newcommand\begindot{\begin{itemize}
[itemsep=2pt plus 2pt minus 2pt,%
topsep=3pt plus 2pt minus 2pt,%
parsep=0pt plus 2pt minus 2pt]}
\newcommand\myenddot{\end{itemize}}

\newcommand\beginnum{\begin{enumerate}
[itemsep=2pt plus 2pt minus 2pt,%
topsep=3pt plus 2pt minus 2pt,%
parsep=0pt plus 2pt minus 2pt]}
\newcommand\myendnum{\end{enumerate}}

\DefineVerbatimEnvironment%
  {Code}{Verbatim}
  {fontsize=\small,baselinestretch=0.9,xleftmargin=3mm}

\raggedbottom
%\setlength{\parskip}{1ex plus .5ex minus .5ex}

\@addtoreset{footnote}{page}
%\def\@fncnsymbol#1{\ifcase#1\or ①\or ②\or ③\or
%   ④\or ⑤\or ⑥\or ⑦\or ⑧
%   \or ⑨ \else\@ctrerr\fi}
%\def\fncnsymbol#1{\expandafter\@fncnsymbol\csname c@#1\endcsname}
%\renewcommand{\thefootnote}{\fncnsymbol{footnote}}
%\renewcommand{\thefootnote}{\textbf{\color{blue}{\arabic{footnote}}}}
