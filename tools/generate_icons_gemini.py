#!/usr/bin/env python3
"""Generate small methodology-diagram icons with Gemini image models.

This helper is optional. FIGTREE itself does not require generated icons, but
paper figures sometimes benefit from a small, consistent icon vocabulary.

Example:
    python tools/generate_icons_gemini.py \
      --prompt "minimal flat vector icon of a neural network block" \
      --output icons/neural_network.png
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
from pathlib import Path


DEFAULT_STYLE = (
    "Create a clean academic methodology-diagram icon. Use a flat vector-like "
    "style, white or transparent background, no text, no watermark, compact "
    "geometry, simple shapes, and high contrast at 64x64 pixels."
)


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def extract_image_bytes(response) -> tuple[bytes, str]:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data is None:
                continue
            data = getattr(inline_data, "data", None)
            mime_type = getattr(inline_data, "mime_type", None) or "image/png"
            if isinstance(data, str):
                return base64.b64decode(data), mime_type
            return bytes(data), mime_type
    raise RuntimeError("Gemini response did not contain image data.")


def generate_icon(prompt: str, output: Path, model: str) -> Path:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional Gemini SDK first: pip install google-genai"
        ) from exc

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    full_prompt = f"{DEFAULT_STYLE}\n\nIcon concept: {prompt}"
    response = client.models.generate_content(model=model, contents=full_prompt)
    image_bytes, mime_type = extract_image_bytes(response)

    if output.suffix == "":
        extension = mimetypes.guess_extension(mime_type) or ".png"
        output = output.with_suffix(extension)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image_bytes)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate FIGTREE helper icons with Gemini.")
    parser.add_argument("--prompt", required=True, help="Icon concept to generate.")
    parser.add_argument("--output", required=True, type=Path, help="Output image path.")
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        help="Gemini image model name.",
    )
    parser.add_argument(
        "--env",
        default=".env",
        type=Path,
        help="Optional .env file containing GEMINI_API_KEY.",
    )
    args = parser.parse_args()

    load_dotenv(args.env)
    output = generate_icon(args.prompt, args.output, args.model)
    print(output)


if __name__ == "__main__":
    main()
