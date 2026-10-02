"""Phase 1a — Ingest: turn a job description file (rtf/docx/html/pdf/txt/md) into clean text.

Usage:
    python -m jd2agent.ingest roles/<slug>/jd.rtf            # writes roles/<slug>/jd.txt
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

PANDOC_FORMATS = {".rtf": "rtf", ".docx": "docx", ".html": "html", ".htm": "html", ".odt": "odt"}


def to_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        if not shutil.which("pdftotext"):
            sys.exit("pdftotext not installed (poppler-utils)")
        return subprocess.run(["pdftotext", "-layout", str(path), "-"],
                              capture_output=True, text=True, check=True).stdout
    if suffix in PANDOC_FORMATS:
        if not shutil.which("pandoc"):
            sys.exit("pandoc not installed")
        return subprocess.run(["pandoc", "-f", PANDOC_FORMATS[suffix], "-t", "plain", "--wrap=none", str(path)],
                              capture_output=True, text=True, check=True).stdout
    sys.exit(f"Unsupported file type: {suffix}")


def clean(text: str) -> str:
    text = text.replace(" ", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def main(src: str) -> Path:
    path = Path(src)
    out = path.with_suffix(".txt")
    if out == path:
        out = path.with_name(path.stem + ".clean.txt")
    out.write_text(clean(to_text(path)), encoding="utf-8")
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
