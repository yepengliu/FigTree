# FIGTREE Pipeline Guide

This guide describes the implementation workflow for FIGTREE, a recursive
layout-tree pipeline for editable SVG methodology figures.

## Inputs

FIGTREE accepts one of:

- `--paper`: a UTF-8 text file containing paper content.
- `--pdf`: a PDF file; text is extracted before generation.
- `--text`: inline text supplied directly through the CLI.

By default, `tree_pipeline.run` extracts a likely methodology section. Pass
`--full-text` when the complete input should be used.

## Stage 1: Paper Grounding

The root agent reads the input paper and produces:

- A conservative global diagram description.
- A global style specification shared by all nodes.

The grounding stage should include only content supported by the paper. It
should not add auxiliary modules merely to make the figure look complete.

## Stage 2: Recursive Figure Construction

The root node starts a layout tree. Each node contains:

- `description`: what the sub-figure should show.
- `canvas`: local width and height.
- `required_ports`: named boundary ports for cross-node connections.
- `depth`: current tree depth.
- `global_style`: shared visual constraints.

For each node, the generator decides whether to draw directly or decompose:

```text
if the node is atomic or depth reaches max_depth:
    draw a leaf SVG fragment
else:
    decompose into immediate child nodes
    recursively generate each child
    merge checked child fragments
```

Children draw only internal structure. Cross-boundary arrows are owned by the
parent, because the parent is the first node that knows both endpoints in a
shared coordinate frame.

## Stage 3: Render-Critic Refinement

Each generated fragment is rendered to PNG and reviewed together with its SVG
source. The critic reports localized defects with:

- A visual description.
- The affected code anchor.
- A concrete repair instruction.

The worker edits only the offending element, re-renders, and repeats until the
fragment passes or the retry budget is exhausted. Residual defects are returned
in the node report so an ancestor can address layout-level issues.

## Output Layout

Each run creates a timestamped directory under `--output`:

```text
runs/figtree/
  run_<timestamp>_<id>/
    run_manifest.json
    tree_trace.jsonl
    output.svg
    output.png
    nodes/
      <node_id>/
        task.json
        node_report.json
        output.svg
        output.png
```

These run artifacts are generated outputs and should not be committed.

## CLI Examples

```bash
python -m tree_pipeline.run --paper input.txt --output runs/figtree
python -m tree_pipeline.run --pdf paper.pdf --output runs/figtree --max-depth 3
python -m tree_pipeline.run --text "Describe the method here" --model sonnet
```
