# Figures as Programs: Recursive Generation of Editable Scientific Figures

Official implementation of an editable scientific figure generation method presented in the paper:

["Figures as Programs: Recursive Generation of Editable Scientific Figures"](https://arxiv.org/pdf/2609.01006) 


## Introduction

FIGTREE generates editable scientific methodology figures as SVG programs.

The core idea is to treat figure generation as a long-horizon SVG program construction and make it tractable through a recursive layout tree. Instead of asking one model call to write an entire complex diagram, FIGTREE decomposes the figure into localized sub-figures, generates short SVG fragments, verifies them through rendering, and assembles them level by level.

## Method Overview

Given the text of a paper, FIGTREE synthesizes a methodology figure that
summarizes the paper's method. The output is not a raster image; it is an SVG
program whose deterministic rendering is the visible figure. Because every
visual element remains an addressable SVG statement, visual problems can be
repaired through local program edits.

FIGTREE represents the diagram as a layout tree. Each node corresponds to a
sub-figure and contains:

- A natural-language description of the content to draw.
- A local canvas size.
- Boundary ports for connections to other sub-figures.
- The node depth in the recursive tree.
- A global style specification shared across the full figure.

## Pipeline

FIGTREE has three main stages.

### 1. Paper Grounding

The grounder extracts methodology content from the input paper and builds a
global diagram description. This description specifies the components, data
flow, and notation that should appear in the figure.

The grounding stage is conservative: it should include only paper-supported
content and avoid inventing auxiliary modules merely to make the diagram look
complete.

### 2. Recursive Figure Construction

Starting from the root node, FIGTREE expands the layout tree top-down.

For each node, a generator decides whether the node is atomic enough to draw
directly. If so, it writes a short SVG fragment. Otherwise, it decomposes the
node into a small set of immediate child nodes and delegates each child
recursively.

Children only draw content inside their own local canvas. Cross-boundary
connections are owned by the parent, because the parent is the first node that
knows both endpoints in a shared coordinate frame. This avoids duplicated or
inconsistent arrows between sibling sub-figures.

### 3. Render-Critic Refinement

Each SVG fragment is rendered and reviewed before it is returned to its parent.
The critic inspects both:

- The rendered image, which exposes visual defects such as overflow,
  misalignment, cramped spacing, and broken arrows.
- The SVG source code, which provides precise anchors for localized repair.

When the critic finds a defect, FIGTREE edits only the offending SVG element and
re-renders the fragment. The loop continues until the fragment passes or the
retry budget is exhausted. Residual defects are preserved in the node report so
an ancestor can address layout-level issues with more context.

## Installation

```bash
pip install -r requirements.txt
```

FIGTREE currently invokes the Claude CLI from Python, so install and
authenticate `claude` before running the main pipeline.

Optional icon generation uses Gemini image models:

```bash
pip install google-genai
```

Set API keys in `.env` or your shell environment when needed:

```bash
GEMINI_API_KEY=your_key_here
```

## Usage

Generate from paper text:

```bash
python -m tree_pipeline.run --paper input.txt --output runs/figtree
```

Generate from a PDF:

```bash
python -m tree_pipeline.run --pdf paper.pdf --output runs/figtree
```

Use the full input text instead of extracting a likely methodology section:

```bash
python -m tree_pipeline.run --paper input.txt --full-text
```

Common options:

```bash
python -m tree_pipeline.run \
  --paper input.txt \
  --output runs/figtree \
  --max-depth 3 \
  --max-retries 3 \
  --model sonnet
```

Generate an optional helper icon:

```bash
python tools/generate_icons_gemini.py \
  --prompt "minimal flat icon of a neural network module" \
  --output icons/neural_network.png
```

## Repository Structure

```text
tree_pipeline/
  run.py              CLI entry point
  orchestrator.py     Recursive layout-tree orchestration
  schemas.py          Node, issue, and logging data structures
  prompts/
    generator.md      Decomposition and SVG drawing prompt
    critic.md         Render/code review prompt
    svg_worker.md     SVG merge and localized repair prompt

tools/
  latex_to_svg.py             Convert LaTeX snippets to SVG
  generate_icons_gemini.py    Optional Gemini icon-generation helper
```

## Generated Artifacts

Each run writes artifacts under the directory passed to `--output`, typically
`runs/figtree/`. These artifacts include node tasks, generated SVG fragments,
rendered PNG previews, critic reports, and the final assembled SVG.

Generated outputs are intentionally ignored by Git and should not be committed
to the public repository.



## Citation

```bibtex
@article{liu2026figures,
  title={Figures as Programs: Recursive Generation of Editable Scientific Figures},
  author={Liu, Yepeng and Dai, Dasen and Liu, Chengzhi and Song, Yiren and Ci, Hai and Zhang, Yu and Zhang, Qi and Shou, Mike Zheng and Wang, Xin Eric and Bu, Yuheng},
  journal={arXiv preprint arXiv:2609.01006},
  year={2026}
}
```
