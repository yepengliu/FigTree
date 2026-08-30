#!/usr/bin/env python3
"""
Render LaTeX math expressions to SVG path elements using matplotlib's mathtext.
Output is pure SVG <path> data — no font dependencies, renders identically everywhere.

Usage:
    python tools/latex_to_svg.py '$\\tau_T$' --fontsize 14 --output /tmp/tau_T.svg
    python tools/latex_to_svg.py '$E_{kin}$' --fontsize 12

Python API:
    from tools.latex_to_svg import latex_to_svg, latex_to_svg_element

    # Get standalone SVG file content
    svg_str = latex_to_svg(r'$\tau_T$', fontsize=14)

    # Get embeddable SVG <g> element (for inserting into larger SVG)
    g_element, width, height = latex_to_svg_element(r'$\\phi_1$', fontsize=12)
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_svg import FigureCanvasSVG
import io
import re
import argparse
import sys


def latex_to_svg(expr: str, fontsize: int = 14, color: str = '#333333') -> str:
    """Render a LaTeX math expression to a standalone SVG string.

    Args:
        expr: LaTeX expression (e.g., r'$\\tau_T$' or r'$E_{kin}$')
        fontsize: Font size in points
        color: Text color as hex string

    Returns:
        Complete SVG file content as string
    """
    fig = plt.figure(figsize=(0.01, 0.01))
    fig.text(0, 0, expr, fontsize=fontsize, color=color,
             fontfamily='serif', math_fontfamily='cm',
             ha='left', va='baseline')

    buf = io.BytesIO()
    fig.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0.02,
                transparent=True, metadata={'Creator': 'latex_to_svg'})
    plt.close(fig)

    return buf.getvalue().decode('utf-8')


def latex_to_svg_element(expr: str, fontsize: int = 14, color: str = '#333333',
                          x: float = 0, y: float = 0,
                          anchor: str = 'middle') -> tuple:
    """Render LaTeX to an embeddable SVG <g> element with translate positioning.

    Args:
        expr: LaTeX expression
        fontsize: Font size in points
        color: Text color
        x, y: Position to place the element center
        anchor: 'middle', 'left', or 'right' horizontal alignment

    Returns:
        (svg_g_element: str, width: float, height: float)
    """
    svg_full = latex_to_svg(expr, fontsize, color)

    # Extract viewBox dimensions
    vb_match = re.search(r'viewBox="([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"', svg_full)
    if not vb_match:
        return f'<text x="{x}" y="{y}" font-size="{fontsize}">{expr}</text>', 50, 20

    vb_x, vb_y, vb_w, vb_h = [float(v) for v in vb_match.groups()]

    # Extract width/height in pt
    w_match = re.search(r'width="([\d.]+)pt"', svg_full)
    h_match = re.search(r'height="([\d.]+)pt"', svg_full)
    width_pt = float(w_match.group(1)) if w_match else vb_w
    height_pt = float(h_match.group(1)) if h_match else vb_h

    # Convert pt to px (1pt = 1.333px)
    width_px = width_pt * 1.333
    height_px = height_pt * 1.333

    # Extract the inner SVG content (everything inside <svg>...</svg>)
    inner_match = re.search(r'<svg[^>]*>(.*?)</svg>', svg_full, re.DOTALL)
    if not inner_match:
        return f'<text x="{x}" y="{y}" font-size="{fontsize}">{expr}</text>', 50, 20

    inner = inner_match.group(1)
    # Remove metadata and xlink references that cairosvg can't handle
    inner = re.sub(r'<metadata>.*?</metadata>', '', inner, flags=re.DOTALL)
    inner = re.sub(r'\s*xmlns:xlink="[^"]*"', '', inner)
    inner = re.sub(r'xlink:href', 'href', inner)

    # Calculate offset based on anchor
    if anchor == 'middle':
        tx = x - width_px / 2
    elif anchor == 'right':
        tx = x - width_px
    else:  # left
        tx = x
    ty = y - height_px / 2

    # Scale from viewBox to pixel dimensions
    sx = width_px / vb_w if vb_w else 1
    sy = height_px / vb_h if vb_h else 1

    g_element = f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sx:.4f},{sy:.4f})">{inner}</g>'

    return g_element, width_px, height_px


def latex_to_svg_file(expr: str, output_path: str, fontsize: int = 14,
                       color: str = '#333333'):
    """Render LaTeX and save to SVG file."""
    svg = latex_to_svg(expr, fontsize, color)
    with open(output_path, 'w') as f:
        f.write(svg)
    print(f"Saved: {output_path} ({len(svg)} bytes)")


def batch_render(expressions: dict, fontsize: int = 14) -> dict:
    """Render multiple expressions, return dict of {name: (g_element, w, h)}.

    Args:
        expressions: dict of {name: latex_expr}, e.g., {'tau_T': r'$\\tau_T$'}
        fontsize: Font size in points

    Returns:
        dict of {name: (svg_g_element, width_px, height_px)}
    """
    results = {}
    for name, expr in expressions.items():
        g, w, h = latex_to_svg_element(expr, fontsize)
        results[name] = (g, w, h)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Render LaTeX math to SVG')
    parser.add_argument('expression', help='LaTeX expression (e.g., "$\\\\tau_T$")')
    parser.add_argument('--fontsize', type=int, default=14, help='Font size (default: 14)')
    parser.add_argument('--color', default='#333333', help='Text color (default: #333333)')
    parser.add_argument('--output', '-o', help='Output SVG file path')
    parser.add_argument('--element', action='store_true',
                        help='Output embeddable <g> element instead of full SVG')

    args = parser.parse_args()

    if args.element:
        g, w, h = latex_to_svg_element(args.expression, args.fontsize, args.color)
        print(f"<!-- Size: {w:.1f}x{h:.1f}px -->")
        print(g)
    elif args.output:
        latex_to_svg_file(args.expression, args.output, args.fontsize, args.color)
    else:
        svg = latex_to_svg(args.expression, args.fontsize, args.color)
        print(svg)
