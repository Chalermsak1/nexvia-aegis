#!/usr/bin/env python3
"""
Audit Report Compilation and Verification Utility for NEXVIA AEGIS V9-M4.
Generates publication-quality PDFs via XeLaTeX from corresponding TeX source,
validates layout, page count, text extraction, and computes SHA-256 hashes.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/chalermsak/Desktop/nexvia-aegis-main")
REPORT_DIR = REPO_ROOT / "docs" / "reports" / "v9_m4_statistical_audit"
XELATEX_BIN = "/usr/local/texlive/2026/bin/universal-darwin/xelatex"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compile_and_verify(tex_source_path: Path, output_pdf_path: Path) -> dict:
    """Compiles LaTeX to PDF using xelatex, validates with pdfinfo and pdftotext, and calculates SHA-256."""
    cwd = tex_source_path.resolve().parent
    tex_file = tex_source_path.resolve()
    cmd = [
        XELATEX_BIN,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={cwd}",
        str(tex_file),
    ]

    # Run twice for cross-references / page numbers
    for run in range(2):
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Compilation error on run {run+1} for {tex_source_path.name}:", file=sys.stderr)
            print(res.stdout[-2000:], file=sys.stderr)
            raise RuntimeError(f"XeLaTeX compilation failed for {tex_source_path.name}")

    if not output_pdf_path.exists() or output_pdf_path.stat().st_size == 0:
        raise RuntimeError(f"Output PDF {output_pdf_path} was not created or is empty.")

    # Validate with pdfinfo
    pinfo = subprocess.run(["pdfinfo", str(output_pdf_path)], capture_output=True, text=True)
    if pinfo.returncode != 0:
        raise RuntimeError(f"pdfinfo failed on {output_pdf_path}: {pinfo.stderr}")

    page_count = 0
    for line in pinfo.stdout.splitlines():
        if line.startswith("Pages:"):
            page_count = int(line.split()[1])

    # Validate with pdftotext
    ptotext = subprocess.run(["pdftotext", str(output_pdf_path), "-"], capture_output=True, text=True)
    if ptotext.returncode != 0 or len(ptotext.stdout.strip()) == 0:
        raise RuntimeError(f"pdftotext extracted empty content from {output_pdf_path}")

    # Clean intermediate auxiliary files
    for ext in [".aux", ".log", ".out", ".toc"]:
        aux = tex_source_path.with_suffix(ext)
        if aux.exists():
            aux.unlink()

    pdf_sha = sha256_file(output_pdf_path)
    return {
        "status": "PASS",
        "pages": page_count,
        "size_bytes": output_pdf_path.stat().st_size,
        "sha256": pdf_sha,
        "extracted_chars": len(ptotext.stdout),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: compile_audit_report.py <tex_path> <pdf_path>")
        sys.exit(1)
    res = compile_and_verify(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(res, indent=2))
