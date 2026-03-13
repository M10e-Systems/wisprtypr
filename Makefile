POETRY ?= poetry

.PHONY: test
test:
	$(POETRY) install --with dev
	$(POETRY) run pytest
