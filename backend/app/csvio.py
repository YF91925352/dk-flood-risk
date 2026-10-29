"""Parse an uploaded portfolio CSV. Accepts ',' or ';' (Danish Excel uses ';'), UTF-8 with or
without BOM, and an 'address' (or Danish 'adresse') column plus an optional reference column."""
import csv
import io
from dataclasses import dataclass

ADDRESS_COLS = {"address", "adresse"}
REFERENCE_COLS = {"reference", "ref", "id", "reference_id"}


class CsvError(ValueError):
    pass


@dataclass(frozen=True)
class InputRow:
    row_no: int          # spreadsheet row number, so problems can be found in the original file
    reference: str | None
    address: str


def parse(data: bytes, max_rows: int) -> list[InputRow]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvError("File must be UTF-8 encoded") from None
    if not text.strip():
        raise CsvError("File is empty")
    first_line = text.splitlines()[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    cols = {(c or "").strip().lower(): c for c in reader.fieldnames or []}
    addr_col = next((cols[c] for c in cols if c in ADDRESS_COLS), None)
    if addr_col is None:
        raise CsvError("CSV needs an 'address' column")
    ref_col = next((cols[c] for c in cols if c in REFERENCE_COLS), None)

    rows = []
    for r in reader:
        i = reader.line_num  # the row number the user sees in Excel (header = row 1)
        address = (r.get(addr_col) or "").strip()
        if not address:
            continue  # blank lines are common at the end of exported files
        if len(rows) == max_rows:
            raise CsvError(f"Too many rows: the limit is {max_rows} per upload")
        ref = (r.get(ref_col) or "").strip() if ref_col else ""
        rows.append(InputRow(i, ref or None, address))
    if not rows:
        raise CsvError("No addresses found")
    return rows
