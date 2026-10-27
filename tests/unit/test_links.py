from __future__ import annotations

from memento.links import LinkFormat, render


SAMPLE = (
    "Related services:\n"
    "- [[id:11111111-2222-3333-4444-555555555555][alpha-service]]\n"
    "- [[id:66666666-7777-8888-9999-AAAAAAAAAAAA][beta-worker]]\n"
    "- plain text after the list"
)


def test_inline_default():
    out = render(SAMPLE, LinkFormat.INLINE)
    assert "alpha-service (ref:11111111)" in out
    assert "beta-worker (ref:66666666)" in out
    assert "[[id:" not in out
    assert "plain text after the list" in out


def test_raw_passes_through():
    assert render(SAMPLE, LinkFormat.RAW) == SAMPLE


def test_title_lossy():
    out = render(SAMPLE, LinkFormat.TITLE)
    assert "- alpha-service\n" in out
    assert "- beta-worker\n" in out
    assert "[[id:" not in out
    assert "(ref:" not in out


def test_no_links_unchanged():
    text = "Just prose. No links."
    assert render(text, LinkFormat.INLINE) == text
    assert render(text, LinkFormat.RAW) == text
    assert render(text, LinkFormat.TITLE) == text


def test_lowercased_prefix_regardless_of_source_case():
    text = "Pointer: [[id:ABCDEF12-3456-7890-ABCD-EF1234567890][Target]]"
    out = render(text, LinkFormat.INLINE)
    assert "Target (ref:abcdef12)" in out


def test_8_char_prefix_strips_dashes():
    text = "[[id:1A-2B3C4D-1234-5678-9ABC-DEF012345678][Test]]"  # malformed-ish; the regex still anchors on 36-char [0-9a-fA-F-] run
    # Build a normalised-looking input that the regex DOES match (with proper UUID):
    proper = "[[id:1A2B3C4D-1234-5678-9ABC-DEF012345678][T]]"
    out = render(proper, LinkFormat.INLINE)
    # 8 hex chars taken from the de-dashed UUID
    assert "T (ref:1a2b3c4d)" in out
