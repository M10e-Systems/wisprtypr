POETRY ?= poetry
MAX_ITERATIONS ?= 5
FREE_DATASET ?= tests/fixtures/audio/free-samples/dataset.jsonl

.PHONY: test audio-dataset-bootstrap audio-eval audio-loop
test:
	$(POETRY) install --with dev
	$(POETRY) run pytest

audio-dataset-bootstrap:
	./scripts/bootstrap_free_audio_dataset.sh

audio-eval:
	@if [ -z "$(DATASET)" ]; then echo "DATASET is required, e.g. make audio-eval DATASET=tests/fixtures/audio/dataset.jsonl"; exit 2; fi
	$(POETRY) install --with dev
	$(POETRY) run wisprtypr-audio-eval --dataset "$(DATASET)"

audio-loop:
	@if [ -z "$(DATASET)" ]; then echo "DATASET is required, e.g. make audio-loop DATASET=tests/fixtures/audio/dataset.jsonl"; exit 2; fi
	$(POETRY) install --with dev
	$(POETRY) run wisprtypr-audio-fix-loop --dataset "$(DATASET)" --max-iterations "$(MAX_ITERATIONS)"
