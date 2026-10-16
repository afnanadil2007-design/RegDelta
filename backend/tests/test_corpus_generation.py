"""A new generation of the synthetic corpus replaces the old one on disk.

Ingestion takes every PDF in the output directory, so PDFs left by an earlier,
larger generation would join the new corpus (and change its gold set) unless
the generator removes them.
"""

from __future__ import annotations

from pathlib import Path

from ingestion.generate_corpus import generate, remove_stale, write_pdf


def test_only_the_pdfs_of_this_generation_remain(tmp_path: Path) -> None:
    written = {write_pdf(circular, tmp_path).name for circular in generate(3, 7)}
    (tmp_path / "SEBI_HO_OLD_CIR_P_2019_999.pdf").write_bytes(b"%PDF- left by a larger run")
    (tmp_path / "notes.txt").write_text("not a PDF; not the generator's to remove")

    removed = remove_stale(tmp_path, written)

    assert removed == ["SEBI_HO_OLD_CIR_P_2019_999.pdf"]
    assert {p.name for p in tmp_path.glob("*.pdf")} == written
    assert (tmp_path / "notes.txt").exists()
