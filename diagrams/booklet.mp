u=2cm;
%defaultfont:="ptmr8r";
outputtemplate:="%j-%c.eps";
prologue:=2;

def book(text l)(text r) =
draw (0, 0)--(0, 1.4u)--(0.6u, 1u)--(0.6u,-0.4u)--(0, 0);
draw (0, 1.4u)--(1u, 1.4u)--(1u, 0u)--(0.65u, 0u);
draw (0, 0) -- (0.6u, 0) dashed evenly;
label.top(l, (0.5u, -0.3u));
label.top(r, (0.9u, 0u));
enddef;

beginfig(1);
book("1")("7");
endfig;

beginfig(2);
book("3")("5");
endfig;

def paper(text l)(text r) =
draw (0, 1.4u)--(1u, 1.4u)--(1u, 0u)--(0u, 0u)--cycle;
draw (1u, 1.4u)--(2u, 1.4u)--(2u, 0u)--(1u, 0u);
label.top(l, (0.1u, 0u));
label.top(r, (1.9u, 0u));
enddef;

beginfig(3);
paper("8")("1");
endfig;

beginfig(4);
paper("2")("7");
endfig;

beginfig(5);
paper("6")("3");
endfig;

beginfig(6);
paper("4")("5");
endfig;

end
