"""
File parsing: turns raw uploaded bytes into a list of {column_name: string_value}
rows, in whatever column order the source file used. This is the one place that
knows about file formats (CSV vs Excel) - everything after this deals only in
plain dicts, so adding a new file format later never touches the normalizer.

Every value is kept as a string exactly as the file presented it (dtype=str,
na_filter=False), because this is the layer responsible for the PDF's "preserve
the raw source record" requirement - type coercion (dates, numbers) is the
normalizer's job, not the parser's.
"""
import io

import pandas as pd

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls")


class UnsupportedFileType(ValueError):
    pass


def parse_file(filename: str, content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str, na_filter=False, keep_default_na=False)
    elif lower.endswith(".xlsx") or lower.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(content), dtype=str, na_filter=False)
    else:
        raise UnsupportedFileType(
            f"Unsupported file type for '{filename}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    headers = [str(c) for c in df.columns]
    rows = df.to_dict(orient="records")
    # to_dict keeps the exact per-cell strings produced above; nothing here mutates values.
    return headers, rows
