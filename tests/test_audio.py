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


def test_utterance_detector_splits_on_multi_second_pause_between_words():
    utterances = []
    detector = UtteranceDetector(
        on_utterance=utterances.append,
        min_speech_seconds=0.2,
        silence_seconds=0.75,
        energy_threshold=0.01,
        sample_rate=10,
        max_chunk_seconds=10,
    )

    # "word 1"
    detector.push(np.ones(3, dtype=float))
    detector.push(np.ones(3, dtype=float))
    # multi-second pause
    detector.push(np.zeros(10, dtype=float))
    # "word 2"
    detector.push(np.ones(3, dtype=float))
    detector.push(np.ones(3, dtype=float))
    detector.push(np.zeros(10, dtype=float))

    assert len(utterances) == 2
    assert all(chunk.is_final for chunk in utterances)
    assert utterances[0].audio.shape[0] == 16  # 6 speech + 10 pause
    assert utterances[1].audio.shape[0] == 16  # 6 speech + 10 pause


def test_utterance_detector_handles_long_sentence_pause_then_new_sentence():
    utterances = []
    detector = UtteranceDetector(
        on_utterance=utterances.append,
        min_speech_seconds=0.2,
        silence_seconds=0.75,
        energy_threshold=0.01,
        sample_rate=20,
        max_chunk_seconds=10,
    )

    # sentence 1
    detector.push(np.ones(8, dtype=float))
    detector.push(np.ones(8, dtype=float))
    # long pause (~2 seconds at sample_rate=20)
    detector.push(np.zeros(40, dtype=float))
    # sentence 2
    detector.push(np.ones(8, dtype=float))
    detector.push(np.ones(8, dtype=float))
    detector.push(np.zeros(40, dtype=float))

    assert len(utterances) == 2
    assert all(chunk.is_final for chunk in utterances)
    assert utterances[0].audio.shape[0] == 56  # 16 speech + 40 pause
    assert utterances[1].audio.shape[0] == 56  # 16 speech + 40 pause
