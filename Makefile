PYTHON ?= python

.PHONY: check
check:
	$(PYTHON) -m scripts.check
