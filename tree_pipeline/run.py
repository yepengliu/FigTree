#!/usr/bin/env python3
"""
Entry point for FIGTREE.

Usage:
    python -m tree_pipeline.run --paper <path> [--output <dir>] [--max-depth 3] [--model sonnet]

    # With PDF:
    python -m tree_pipeline.run --pdf paper.pdf --output runs/figtree/

    # With text:
    python -m tree_pipeline.run --paper input.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tree_pipeline.orchestrator import TreeOrchestrator


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using available tools."""
    # Try pdfplumber first
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    # Try PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_path)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    # Fallback: use pdftotext CLI
    import subprocess
    try:
        result = subprocess.run(
            ["pdftotext", pdf_path, "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
    except FileNotFoundError:
        pass

    raise RuntimeError(
        f"Cannot extract text from {pdf_path}. "
        "Install pdfplumber, PyPDF2, or pdftotext."
    )


def extract_methodology_section(full_text: str) -> str:
    """
    Extract the Methodology / Method / Architecture section from paper text.
    We focus only on this section to avoid generating too much.
    """
    import re

    # Common section headers for methodology
    patterns = [
        r"(?i)(3\.?\s*(?:methodology|method|approach|architecture|model|framework|proposed).*?)(?=\n\s*(?:4|5)\.?\s*[A-Z])",
        r"(?i)((?:methodology|method|approach|architecture|model).*?)(?=\n\s*(?:experiment|result|evaluation|conclusion))",
    ]

    for pattern in patterns:
        m = re.search(pattern, full_text, re.DOTALL)
        if m:
            section = m.group(1).strip()
            if len(section) > 200:  # meaningful content
                return section

    # Fallback: return first 5000 chars (likely includes abstract + intro + method)
    return full_text[:5000]


def main():
    parser = argparse.ArgumentParser(description="FIGTREE SVG Generator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--paper", help="Path to paper text file")
    group.add_argument("--pdf", help="Path to PDF file")
    group.add_argument("--text", help="Inline text to use")

    parser.add_argument("--output", default="runs/figtree",
                        help="Output directory (default: runs/figtree)")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="Max tree recursion depth (default: 3)")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Max critic retry rounds per node (default: 3)")
    parser.add_argument("--model", default="sonnet",
                        help="Claude model alias (default: sonnet)")
    parser.add_argument("--reference", help="Path to reference image for comparison")
    parser.add_argument("--full-text", action="store_true",
                        help="Use full paper text instead of extracting methodology section")

    args = parser.parse_args()

    # Get paper text
    if args.pdf:
        print(f"[run] Extracting text from PDF: {args.pdf}")
        full_text = extract_text_from_pdf(args.pdf)
    elif args.paper:
        full_text = Path(args.paper).read_text(encoding="utf-8")
    else:
        full_text = args.text

    # Extract methodology section unless --full-text
    if not args.full_text:
        paper_text = extract_methodology_section(full_text)
        print(f"[run] Extracted methodology section ({len(paper_text)} chars)")
    else:
        paper_text = full_text
        print(f"[run] Using full text ({len(paper_text)} chars)")

    # Run pipeline
    orch = TreeOrchestrator(
        paper_text=paper_text,
        output_dir=args.output,
        max_depth=args.max_depth,
        max_retries=args.max_retries,
        model=args.model,
        reference_image=args.reference,
    )

    final_svg = orch.run()
    print(f"\n[run] Final SVG: {final_svg}")
    print(f"[run] Final PNG: {final_svg.replace('.svg', '.png')}")


if __name__ == "__main__":
    main()
