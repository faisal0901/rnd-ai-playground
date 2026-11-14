"""Chunking: cut a long text into pieces that are small enough to embed and focused enough to be found.

One vector per whole book would blur everything together; one vector per word would lose the context.
So: pieces of roughly ``size`` characters. Consecutive pieces ``overlap`` by a little, so a sentence that falls on a
cut still appears whole in one of them. Cuts prefer a paragraph break, then a sentence end, then a space.
"""

from app.config import CHUNK_OVERLAP, CHUNK_SIZE

CUT_PREFERENCE = ("\n\n", ". ", "\n", " ")  # the best place to cut, in order


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("need size > 0 and 0 <= overlap < size")
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while True:
        end = _end_of_chunk(text, start, size)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            return chunks
        start = _start_of_next(text, start, end, overlap)


def _end_of_chunk(text: str, start: int, size: int) -> int:
    """Where this chunk stops: the end of the window, pulled back to a natural break when there is one."""
    end = min(start + size, len(text))
    if end == len(text):
        return end
    window = text[start:end]
    for separator in CUT_PREFERENCE:
        cut = window.rfind(separator)
        if cut >= size // 2:  # not too early, or the piece would be tiny
            return start + cut + len(separator)
    return end


def _start_of_next(text: str, start: int, end: int, overlap: int) -> int:
    """Where the next chunk begins: back by the overlap, but always forward, and never in the middle of a word."""
    nxt = max(end - overlap, start + 1)
    while nxt < end and not text[nxt - 1].isspace():
        nxt += 1
    return nxt
