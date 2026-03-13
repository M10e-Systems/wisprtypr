from wisprtypr.normalization import normalize_transcript


def test_normalize_transcript_trims_and_caps_sentences():
    text = "  hello   world. this is   wisprtypr.  "
    assert normalize_transcript(text) == "Hello world. This is wisprtypr."


def test_normalize_transcript_handles_empty_values():
    assert normalize_transcript("   ") == ""


def test_normalize_transcript_splits_glued_punctuation_and_camel_case():
    text = "reports.States weFix this"
    assert normalize_transcript(text) == "Reports. States we Fix this"
