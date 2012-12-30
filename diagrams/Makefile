PICS = $(wildcard *.pic)
PIC_EPSES = $(subst pic,eps,$(PICS))
PS2EPS_CMD ?= ps2eps --loose --gsbbox

all: eps

eps: $(PIC_EPSES)

%.eps : %.pic
	gpic $< | geqn | groff | $(PS2EPS_CMD) > $@

.PHONY : eps
