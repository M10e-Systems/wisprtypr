import numpy as np

from wisprtypr.audio import DetectedChunk, UtteranceDetector, merge_detected_chunks


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


def test_merge_detected_chunks_preserves_audio_and_final_flag():
    merged = merge_detected_chunks(
        DetectedChunk(audio=np.array([1.0, 2.0]), is_final=False),
        DetectedChunk(audio=np.array([3.0]), is_final=True),
    )

    assert merged.audio.tolist() == [1.0, 2.0, 3.0]
    assert merged.is_final is True
