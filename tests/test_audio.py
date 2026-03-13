import numpy as np

from wisprtypr.audio import UtteranceDetector


def test_utterance_detector_flushes_when_max_chunk_reached():
    utterances = []
    detector = UtteranceDetector(
        on_utterance=utterances.append,
        min_speech_seconds=0.1,
        silence_seconds=10.0,
        energy_threshold=0.001,
        sample_rate=10,
        max_chunk_seconds=1,
    )

    detector.push(np.ones(6, dtype=float))
    detector.push(np.ones(6, dtype=float))

    assert len(utterances) == 1
    assert utterances[0].audio.shape[0] == 12
    assert utterances[0].is_final is False
