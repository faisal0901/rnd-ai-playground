import io

import pytest
from pdfs import blank_pdf, make_pdf

from app import config
from app.documents import DocumentError, clip, extract_text, safe_name


def test_text_files_are_read_as_utf8_with_or_without_a_bom():
    assert extract_text("a.md", "Kopi pahit — enak".encode()) == "Kopi pahit — enak"
    assert extract_text("a.txt", b"\xef\xbb\xbfhalo") == "halo"  # the BOM that Windows Notepad adds is dropped


def test_an_old_windows_file_is_decoded_instead_of_failing():
    assert extract_text("lama.txt", "café".encode("cp1252")) == "café"


@pytest.mark.parametrize("name", ["a.md", "a.txt", "a.csv", "a.json", "a.log", "A.TXT"])
def test_all_text_types_and_any_letter_case_are_accepted(name):
    assert extract_text(name, b"isi") == "isi"


@pytest.mark.parametrize(("name", "status"), [("a.exe", 415), ("a.docx", 415), ("tanpaekstensi", 415), ("a.png", 415)])
def test_other_types_are_refused_with_415_and_the_allowed_list(name, status):
    with pytest.raises(DocumentError, match=r"not supported.*\.pdf") as error:
        extract_text(name, b"isi")
    assert error.value.status == status


def test_a_binary_file_with_a_text_name_is_refused():
    with pytest.raises(DocumentError, match="binary") as error:
        extract_text("a.txt", b"abc\x00\x01\x02def")
    assert error.value.status == 415


@pytest.mark.parametrize("data", [b"", b"   \n\t  "])
def test_an_empty_file_is_refused(data):
    with pytest.raises(DocumentError, match="No text found") as error:
        extract_text("a.txt", data)
    assert error.value.status == 422


def test_text_is_pulled_out_of_a_pdf():
    assert "kopi enak" in extract_text("a.pdf", make_pdf("kopi enak"))


def test_a_pdf_without_a_text_layer_says_it_needs_ocr():
    with pytest.raises(DocumentError, match="OCR"):
        extract_text("scan.pdf", blank_pdf())


def test_a_broken_pdf_is_a_clean_error_not_a_crash():
    with pytest.raises(DocumentError, match="could not be read") as error:
        extract_text("rusak.pdf", b"%PDF-1.4 this is not really a pdf")
    assert error.value.status == 422


def test_a_password_protected_pdf_is_refused():
    from pypdf import PdfWriter

    writer, buffer = PdfWriter(), io.BytesIO()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("rahasia")
    writer.write(buffer)
    with pytest.raises(DocumentError, match="password"):
        extract_text("terkunci.pdf", buffer.getvalue())


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("kopi.md", "kopi.md"),
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\aku\\catatan.txt", "catatan.txt"),
        ("/abs/path/x.md", "x.md"),
        ("a<b>:c|d?.txt", "a_b_c_d_.txt"),
        ("laporan akhir (v2).pdf", "laporan akhir (v2).pdf"),
    ],
)
def test_file_names_cannot_escape_the_folder_or_carry_odd_characters(given, stored):
    assert safe_name(given) == stored


@pytest.mark.parametrize("bad", [None, "", "..", "   ", "/", ".."])
def test_a_name_with_nothing_usable_is_refused(bad):
    with pytest.raises(DocumentError) as error:
        safe_name(bad)
    assert error.value.status == 400


def test_a_very_long_name_is_cut_but_keeps_its_extension():
    name = safe_name("a" * 300 + ".pdf")
    assert name.endswith(".pdf") and len(name) <= 105


def test_clip_cuts_long_text_and_says_so():
    assert clip("abc", 10) == ("abc", False)
    assert clip("abcdef", 4) == ("abcd", True)
    assert clip("x" * (config.MAX_ATTACH_CHARS + 5))[1] is True
