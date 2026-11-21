"""Every document type an RFQ attachment may come in reaches the agent's DG / packing-list / constraint checks."""
import io
import zipfile
from email.message import EmailMessage

import pytest

from ingest import extract_lines

DG = "UN3480 Lithium ion batteries, Class 9, 120 kg"


def _zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buffer.getvalue()


ODT = _zip({"mimetype": "application/vnd.oasis.opendocument.text",
            "content.xml": f"<office:document-content><text:p>Packing list</text:p><text:p>{DG}</text:p>"
                           "</office:document-content>"})
ODS = _zip({"content.xml": "<table:table-row><table:table-cell><text:p>Item</text:p></table:table-cell>"
                           f"<table:table-cell><text:p>{DG}</text:p></table:table-cell></table:table-row>"})
PPTX = _zip({"ppt/slides/slide1.xml": f"<p:sld><a:p><a:r><a:t>{DG}</a:t></a:r></a:p></p:sld>"})
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64 + DG.encode("utf-16-le") + b"\x00" * 32
XLS = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64 + DG.encode("latin-1") + b"\x00" * 32
RTF = ("{\\rtf1\\ansi{\\fonttbl{\\f0 Arial;}}\\f0 Packing list\\par " + DG + "\\par Gewicht 120 kg, Gr\\'f6\\'dfe}").encode()
HTML = f"<html><body><table><tr><td>Item</td><td>{DG}</td></tr></table><script>x=1</script></body></html>".encode()


def _eml(attachment_name="packing.odt", attachment=ODT) -> bytes:
    message = EmailMessage()
    message["From"], message["Subject"] = "shipper@example.com", "Fwd: packing list"
    message.set_content("Please see the packing list attached.")
    message.add_attachment(attachment, maintype="application", subtype="octet-stream", filename=attachment_name)
    return bytes(message)


@pytest.mark.parametrize("name,data", [
    ("packing.odt", ODT), ("packing.ods", ODS), ("slides.pptx", PPTX), ("packing.doc", DOC), ("list.xls", XLS),
    ("packing.rtf", RTF), ("packing.html", HTML), ("packing.htm", HTML), ("packing.xml", f"<r><i>{DG}</i></r>".encode()),
    ("packing.json", ('{"items": ["' + DG + '"]}').encode()), ("packing.tsv", f"Item\t{DG}".encode()),
    ("fwd.eml", _eml()), ("docs.zip", _zip({"inner/packing.odt": ODT, "notes.txt": "pickup Monday"})),
    ("NOEXTENSION", DOC),
])
def test_the_dg_line_is_read_from_every_document_type(name, data):
    text = "\n".join(extract_lines(name, data))
    assert "UN3480" in text and "Class 9" in text and "120 kg" in text


def test_rtf_umlauts_html_cells_and_scripts():
    assert "Größe" in "\n".join(extract_lines("x.rtf", RTF))
    html = extract_lines("x.html", HTML)
    assert any("Item | " + DG in line or ("Item" in line and DG in line) for line in html) and "x=1" not in "".join(html)


def test_a_zip_bomb_and_deep_nesting_are_not_unpacked():
    big = _zip({"a.txt": "0" * 21_000_000})
    assert extract_lines("big.zip", big) == []
    nested = _zip({"l1.zip": _zip({"l2.zip": _zip({"deep.txt": DG})})})
    assert "UN3480" not in "\n".join(extract_lines("nested.zip", nested))


def test_a_broken_file_inside_a_zip_never_loses_the_others():
    text = "\n".join(extract_lines("docs.zip", _zip({"broken.pdf": b"%PDF-garbage", "packing.rtf": RTF})))
    assert "UN3480" in text


def test_unknown_types_still_raise_for_tariffs():
    from ingest import TariffError
    with pytest.raises(TariffError):
        extract_lines("photo.heic", b"\x00\x01binary")


def test_an_excel_file_without_extension_is_read_as_excel():
    import openpyxl
    book = openpyxl.Workbook()
    book.active.append(["Item", DG])
    buffer = io.BytesIO()
    book.save(buffer)
    assert "UN3480" in "\n".join(extract_lines("attachment", buffer.getvalue()))


# ---- the long list (Sat 22:40): text, data, databases, archives, packages, engineering files ----------------------

import bz2 as _bz2
import gzip as _gzip
import lzma as _lzma
import sqlite3 as _sqlite3
import tarfile as _tarfile


def _tar(files: dict, mode="w:gz") -> bytes:
    buffer = io.BytesIO()
    with _tarfile.open(fileobj=buffer, mode=mode) as t:
        for name, data in files.items():
            info = _tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _sqlite_file(tmp_path) -> bytes:
    path = tmp_path / f"list{len(list(tmp_path.iterdir()))}.db"
    db = _sqlite3.connect(path)
    db.execute("CREATE TABLE items (pos INTEGER, description TEXT)")
    db.execute("INSERT INTO items VALUES (1, ?)", (DG,))
    db.commit()
    db.close()
    return path.read_bytes()


def _dbf_file() -> bytes:
    fields = [(b"POS", 3), (b"TEXT", 60)]
    header_len, record_len = 32 + 32 * len(fields) + 1, 1 + sum(s for _, s in fields)
    head = bytes([3, 126, 11, 21]) + (1).to_bytes(4, "little") + header_len.to_bytes(2, "little") \
        + record_len.to_bytes(2, "little") + b"\x00" * 20
    descriptors = b"".join(n.ljust(11, b"\x00") + b"C" + b"\x00" * 4 + bytes([s]) + b"\x00" * 15 for n, s in fields)
    record = b" " + b"1".ljust(3) + DG.encode("latin-1").ljust(60)
    return head + descriptors + b"\x0d" + record + b"\x1a"


def _deb_file() -> bytes:
    data = _tar({"./usr/share/doc/packing.txt": DG.encode()})
    member = b"data.tar.gz/".ljust(16) + b"0".ljust(12) + b"0".ljust(6) + b"0".ljust(6) + b"100644".ljust(8) \
        + str(len(data)).encode().ljust(10) + b"`\n"
    return b"!<arch>\n" + member + data + (b"\n" if len(data) % 2 else b"")


TEXTUAL = [
    ("packing.yaml", f"items:\n  - {DG}\n"), ("packing.yml", f"- {DG}\n"), ("packing.toml", f'item = "{DG}"\n'),
    ("notes.md", f"# Packing\n* {DG}\n"), ("graph.rdf", f"<rdf:RDF><rdf:Description>{DG}</rdf:Description></rdf:RDF>"),
    ("dump.sql", f"INSERT INTO items VALUES ('{DG}');"), ("order.hl7", f"MSH|^~\\&|X\rOBX|1|TX|||{DG}"),
    ("route.geojson", '{"type": "Feature", "properties": {"cargo": "' + DG + '"}}'),
    ("site.gml", f"<gml:featureMember><cargo>{DG}</cargo></gml:featureMember>"),
    ("label.svg", f"<svg><text>{DG}</text></svg>"), ("part.dxf", f"0\nTEXT\n1\n{DG}\n"),
    ("part.step", f"ISO-10303-21; /* {DG} */"), ("part.iges", f"{DG}"), ("part.stl", f"solid {DG}\nendsolid"),
    ("board.gbr", f"G04 {DG}*"), ("amp.sp", f"* {DG}\nR1 1 2 1k"), ("top.v", f"// {DG}\nmodule top; endmodule"),
    ("top.vhdl", f"-- {DG}"), ("events.jsonl", '{"cargo": "' + DG + '"}\n'),
]


@pytest.mark.parametrize("name,text", TEXTUAL)
def test_text_and_markup_formats(name, text):
    assert "UN3480" in "\n".join(extract_lines(name, text.encode()))


def test_databases_and_dbase(tmp_path):
    for name in ("list.db", "list.sqlite", "map.gpkg", "NOEXT_DB"):
        assert "UN3480" in "\n".join(extract_lines(name, _sqlite_file(tmp_path))), name
    assert "UN3480" in "\n".join(extract_lines("attributes.dbf", _dbf_file()))
    assert "UN3480" in "\n".join(extract_lines("parcels.zip", _zip({"parcels.shp": b"\x00" * 100,
                                                                     "parcels.dbf": _dbf_file()})))  # a Shapefile


def test_archives_and_packages():
    inner = {"docs/packing.rtf": RTF}
    cases = {"docs.tar.gz": _tar(inner), "docs.tgz": _tar(inner), "docs.tar": _tar(inner, "w"),
             "docs.tar.bz2": _tar(inner, "w:bz2"), "docs.tar.xz": _tar(inner, "w:xz"),
             "packing.rtf.gz": _gzip.compress(RTF), "packing.rtf.bz2": _bz2.compress(RTF),
             "packing.rtf.xz": _lzma.compress(RTF), "book.epub": _zip({"OEBPS/ch1.xhtml": HTML}),
             "tool.jar": _zip({"META-INF/notes.txt": DG.encode()}), "app.apk": _zip({"assets/packing.odt": ODT}),
             "app.aab": _zip({"base/packing.txt": DG.encode()}), "app.appx": _zip({"packing.txt": DG.encode()}),
             "pkg.deb": _deb_file()}
    for name, data in cases.items():
        assert "UN3480" in "\n".join(extract_lines(name, data)), name


@pytest.mark.parametrize("name", ["table.parquet", "table.orc", "data.h5", "data.hdf5", "rows.avro", "msg.pb",
                                  "msg.thrift", "rows.msgpack", "db.mdb", "db.accdb", "db.mdf", "part.dwg",
                                  "house.rvt", "part.f3d", "chip.gds", "art.psd", "art.xcf", "docs.7z", "docs.rar",
                                  "disk.iso", "disk.img", "disk.vhd", "disk.wim", "app.dmg", "app.msi", "app.rpm"])
def test_binary_formats_give_their_readable_strings(name):
    blob = b"\x00\x01\x02PAR1\x15\x04" + DG.encode() + b"\x00\xff\xfe" + "Gewicht 120 kg".encode("utf-16-le") + b"\x00\x00"
    text = "\n".join(extract_lines(name, blob))
    assert "UN3480" in text and "Gewicht 120 kg" in text


def test_illustrator_files_without_a_pdf_inside_give_their_strings():
    assert "UN3480" in "\n".join(extract_lines("logo.ai", b"%!PS-Adobe-3.0 " + DG.encode() + b"\x00\x00"))


@pytest.mark.parametrize("name", ["scan.tiff", "scan.bmp", "photo.heic", "memo.mp3", "memo.wav", "memo.bwf",
                                  "memo.aiff", "song.mid", "clip.mp4", "clip.mkv", "clip.mov", "clip.avi", "clip.webm",
                                  "frames.dpx"])
def test_images_and_recordings_are_left_to_the_scan_and_media_readers(name):
    from ingest import TariffError
    with pytest.raises(TariffError):  # /api/attachments/text answers "" and the agent's reader takes over
        extract_lines(name, b"\x00" * 32 + b"some text inside the binary" + b"\x00" * 32)
