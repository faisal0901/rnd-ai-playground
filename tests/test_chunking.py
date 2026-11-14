import pytest

from app.chunking import chunk_text

TEXT = " ".join(f"kata{i}" for i in range(400))  # 400 distinct words, about 2.7k characters


def test_short_text_stays_in_one_piece_and_empty_text_gives_nothing():
    assert chunk_text("halo dunia", size=100, overlap=10) == ["halo dunia"]
    assert chunk_text("  \n ", size=100, overlap=10) == []


def test_no_piece_is_longer_than_size():
    assert all(len(piece) <= 300 for piece in chunk_text(TEXT, size=300, overlap=50))


def test_no_word_is_lost_or_cut_in_half():
    pieces = chunk_text(TEXT, size=300, overlap=50)
    assert len(pieces) > 5
    seen = {word for piece in pieces for word in piece.split()}
    assert seen == set(TEXT.split())  # every word appears whole in at least one piece


def test_neighbouring_pieces_overlap_so_a_sentence_on_a_cut_survives():
    pieces = chunk_text(TEXT, size=300, overlap=100)
    for before, after in zip(pieces, pieces[1:], strict=False):
        assert set(before.split()) & set(after.split()), "no shared words between neighbours"


def test_without_overlap_pieces_do_not_repeat_words():
    pieces = chunk_text(TEXT, size=300, overlap=0)
    words = [word for piece in pieces for word in piece.split()]
    assert words == TEXT.split()


def test_prefers_to_cut_at_a_paragraph_break():
    text = ("a" * 40 + " " + "b" * 30) + "\n\n" + ("c" * 40 + " " + "d" * 30)  # 71 + 2 + 71 characters
    first = chunk_text(text, size=100, overlap=10)[0]
    assert first == "a" * 40 + " " + "b" * 30  # cut at the blank line, not in the middle of the second paragraph


def test_a_text_without_any_space_still_terminates():
    pieces = chunk_text("x" * 1000, size=100, overlap=20)
    assert 10 <= len(pieces) <= 20 and all(len(piece) <= 100 for piece in pieces)


@pytest.mark.parametrize("size, overlap", [(0, 0), (100, 100), (100, -1), (50, 80)])
def test_nonsense_settings_are_refused(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("abc", size=size, overlap=overlap)
