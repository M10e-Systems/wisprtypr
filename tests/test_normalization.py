from wisprtypr.normalization import normalize_transcript


def test_normalize_transcript_trims_and_caps_sentences():
    text = "  hello   world. this is   wisprtypr.  "
    assert normalize_transcript(text) == "Hello world. This is wisprtypr."


def test_normalize_transcript_handles_empty_values():
    assert normalize_transcript("   ") == ""


def test_normalize_transcript_splits_glued_punctuation_and_camel_case():
    text = "reports.States weFix this"
    assert normalize_transcript(text) == "Reports. States we Fix this"


def test_normalize_transcript_adds_space_after_non_period_punctuation():
    text = "hello,world!how are you?fine:thanks;ok"
    assert normalize_transcript(text) == "Hello, world! How are you? Fine: thanks; ok"


def test_normalize_transcript_keeps_decimal_numbers_intact():
    text = "version 3.14 is fine"
    assert normalize_transcript(text) == "Version 3.14 is fine"
