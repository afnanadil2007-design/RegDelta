"""The rules extractor and the synthetic generator that feeds it."""

from __future__ import annotations

import pytest

from app.ai.extraction.rules import extract_obligations_by_rule
from ingestion.generate_corpus import TOPICS, GeneratedCircular, generate, write_pdf


def test_the_actor_is_the_whole_subject_phrase() -> None:
    """v1 kept only capitalised words, so this obligation began at "document"."""
    text = "2. The risk disclosure document shall be acknowledged by the client in writing."
    (item,) = extract_obligations_by_rule(text)
    assert item.actor == "The risk disclosure document"
    assert item.text == text[3:]
    assert text[item.char_start : item.char_end] == item.text


@pytest.mark.parametrize(
    "sentence",
    [
        "5. Intermediaries shall read this circular together with the KYC framework vide X.",
        "6. The provisions in X shall stand superseded from the date of this circular.",
        "7. This circular is issued in exercise of powers conferred under Section 11(1).",
        "8. The requirements in X are specified there and shall continue to apply.",
    ],
)
def test_sentences_without_a_requirement_are_excluded(sentence: str) -> None:
    assert extract_obligations_by_rule(sentence) == []


def test_every_planted_template_is_extracted_exactly() -> None:
    for topic in TOPICS:
        for template in topic.obligations:
            sentence = "3. " + template.format(n=7)
            (item,) = extract_obligations_by_rule(sentence)
            assert item.text == sentence[3:]


def test_offsets_slice_the_source_in_a_multi_paragraph_circular() -> None:
    circular = generate(12)[11]
    text = "\n\n".join(circular.pages)
    items = extract_obligations_by_rule(text)
    assert items
    for item in items:
        assert text[item.char_start : item.char_end] == item.text


def test_the_generator_refuses_text_its_pdf_font_cannot_encode(tmp_path) -> None:
    """PyMuPDF's base-14 Helvetica writes unencodable characters as "?"."""
    circular = generate(1)[0]
    broken = GeneratedCircular(
        circular.number,
        circular.title,
        circular.issue_date,
        circular.department,
        circular.topic,
        ["Fees of ₹10 — payable in advance."],
    )
    with pytest.raises(ValueError, match="not encodable"):
        write_pdf(broken, tmp_path)
