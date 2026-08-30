"""
FIGTREE Orchestrator

Manages the recursive layout tree. Generator, critic, and SVG-repair calls are
executed via `claude -p`.

ALL calls are logged to {run_dir}/tree_trace.jsonl with full prompt/response saved.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tree_pipeline.schemas import (
    DEFAULT_GLOBAL_STYLE,
    TaskPackage,
    NodeReport,
    IssueReport,
    DecompositionPlan,
    LLMCallLog,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class TreeOrchestrator:
    """Drives the FIGTREE recursive layout pipeline, logging every LLM call."""

    def __init__(
        self,
        paper_text: str,
        output_dir: str,
        max_depth: int = 3,
        max_retries: int = 3,
        model: str = "sonnet",
        reference_image: Optional[str] = None,
    ):
        self.paper_text = paper_text
        self.max_depth = max_depth
        self.max_retries = max_retries
        self.model = model
        self.reference_image = reference_image

        # Run directory
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = Path(output_dir) / f"run_{ts}_{uuid.uuid4().hex[:6]}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "nodes").mkdir(exist_ok=True)

        # Trace log
        self.trace_path = self.run_dir / "tree_trace.jsonl"
        self.trace_path.touch()

        # Run manifest
        self.manifest = {
            "start_time": ts,
            "model": model,
            "max_depth": max_depth,
            "max_retries": max_retries,
            "status": "running",
            "nodes": {},
        }
        self._save_manifest()

        print(f"[orchestrator] Run directory: {self.run_dir}")

    # ------------------------------------------------------------------
    # Claude CLI call with full logging
    # ------------------------------------------------------------------

    def call_claude(
        self,
        node_id: str,
        character: str,
        user_prompt: str,
        system_prompt: str,
        allowed_tools: str = "Read,Bash",
        image_paths: Optional[List[str]] = None,
    ) -> str:
        """
        Call claude CLI with -p, log everything.
        Returns the raw text response.
        """
        # Save full prompt to disk
        node_dir = self.run_dir / "nodes" / node_id
        node_dir.mkdir(parents=True, exist_ok=True)

        call_id = f"{character}_{uuid.uuid4().hex[:6]}"
        prompt_path = node_dir / f"{call_id}_prompt.txt"
        response_path = node_dir / f"{call_id}_response.txt"

        prompt_path.write_text(user_prompt, encoding="utf-8")

        # Build command
        cmd = [
            "claude",
            "-p", user_prompt,
            "--output-format", "text",
            "--model", self.model,
            "--system-prompt", system_prompt,
            "--allowed-tools", allowed_tools,
            "--no-session-persistence",
            "--bare",
        ]

        if os.environ.get("CLAUDE_SKIP_PERMISSIONS"):
            cmd.append("--dangerously-skip-permissions")

        start = time.time()
        success = True
        error_msg = ""
        response_text = ""

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(PROJECT_ROOT),
            )
            response_text = result.stdout
            if result.returncode != 0:
                success = False
                error_msg = result.stderr[:1000]
                response_text = result.stderr
        except subprocess.TimeoutExpired:
            success = False
            error_msg = "Timeout after 300s"
        except Exception as e:
            success = False
            error_msg = str(e)

        duration = time.time() - start

        # Save full response
        response_path.write_text(response_text, encoding="utf-8")

        # Append to trace log
        log_entry = LLMCallLog(
            timestamp=datetime.now().isoformat(),
            node_id=node_id,
            character=character,
            prompt_summary=user_prompt[:500],
            prompt_full_path=str(prompt_path),
            response_summary=response_text[:500],
            response_full_path=str(response_path),
            duration_seconds=round(duration, 2),
            success=success,
            error=error_msg,
        )
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(log_entry.to_json_line() + "\n")

        print(f"  [{node_id}:{character}] {'OK' if success else 'FAIL'} ({duration:.1f}s)")

        if not success:
            raise RuntimeError(
                f"Claude call failed for {node_id}:{character}: {error_msg}"
            )

        return response_text

    # ------------------------------------------------------------------
    # Extract JSON from LLM response
    # ------------------------------------------------------------------

    @staticmethod
    def extract_json(text: str) -> Dict:
        """Extract the first JSON object or array from text."""
        # Try to find JSON in markdown code blocks first
        import re
        patterns = [
            r"```json\s*\n(.*?)\n\s*```",
            r"```\s*\n(.*?)\n\s*```",
            r"(\{.*\})",
            r"(\[.*\])",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
        # Last resort: try parsing the whole text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "Could not parse JSON", "raw": text[:1000]}

    # ------------------------------------------------------------------
    # Render SVG to PNG (for Critic)
    # ------------------------------------------------------------------

    def render_png(self, svg_path: str, png_path: str):
        """Render SVG to PNG with WHITE background for Critic review."""
        try:
            import cairosvg
            from PIL import Image
            import io

            # Render SVG to PNG bytes
            png_bytes = cairosvg.svg2png(
                url=svg_path,
                output_width=1400,
            )

            # Composite onto white background (SVG may have transparent bg)
            img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
            white_bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            composited = Image.alpha_composite(white_bg, img)
            composited = composited.convert("RGB")
            composited.save(png_path, "PNG")

        except Exception as e:
            print(f"  [render] ERROR: cairosvg+PIL failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Core recursive execution
    # ------------------------------------------------------------------

    def run(self) -> str:
        """Entry point: execute the root node and return path to final SVG."""
        root_task = TaskPackage(
            task_id="root",
            description=(
                "Generate a complete methodology architecture diagram for this paper. "
                "This is an academic SVG figure showing the high-level architecture. "
                "Layout: left-to-right pipeline. Only draw the core methodology — "
                "do NOT include experiment results or training details."
            ),
            paper_excerpt=self.paper_text,
            canvas={"w": 1200, "h": 600},
            global_style=DEFAULT_GLOBAL_STYLE,
            depth=0,
            max_depth=self.max_depth,
            reference_image_path=self.reference_image,
        )

        report = self.execute_node(root_task)

        # Save final output
        final_svg_path = self.run_dir / "output.svg"
        final_png_path = self.run_dir / "output.png"
        final_svg_path.write_text(report.svg, encoding="utf-8")
        self.render_png(str(final_svg_path), str(final_png_path))

        self.manifest["status"] = "completed"
        self.manifest["final_svg"] = str(final_svg_path)
        self._save_manifest()

        print(f"\n[orchestrator] Done! Output: {final_svg_path}")
        return str(final_svg_path)

    def execute_node(self, task: TaskPackage) -> NodeReport:
        """Recursively execute a single node."""
        node_id = task.task_id
        node_dir = self.run_dir / "nodes" / node_id
        node_dir.mkdir(parents=True, exist_ok=True)

        # Save task
        task.save(str(node_dir / "task.json"))
        self.manifest["nodes"][node_id] = {"status": "running", "depth": task.depth}
        self._save_manifest()

        print(f"\n[node:{node_id}] Starting (depth={task.depth})")

        # ----- Step 1: Generator -----
        plan = self._call_generator(task)

        if plan.should_decompose and task.depth < task.max_depth:
            # ----- Intermediate node: decompose → children → merge -----
            report = self._execute_intermediate(task, plan)
        else:
            # ----- Leaf node: direct SVG generation -----
            report = self._execute_leaf(task, plan)

        # Save report
        report.save(str(node_dir / "report.json"))
        self.manifest["nodes"][node_id]["status"] = report.status
        self._save_manifest()

        return report

    # ------------------------------------------------------------------
    # Generator call
    # ------------------------------------------------------------------

    def _call_generator(self, task: TaskPackage) -> DecompositionPlan:
        sys_prompt = _read_prompt("generator")
        user_prompt = f"""## Task
{task.description}

## Paper Excerpt
{task.paper_excerpt[:3000]}

## Canvas
Width: {task.canvas['w']}px, Height: {task.canvas['h']}px

## Required Ports
{json.dumps(task.required_ports, indent=2)}

## Global Style
{json.dumps(task.global_style, indent=2)}

## Current Depth: {task.depth} / Max Depth: {task.max_depth}

{"## Fix Instructions (REDO)" + chr(10) + json.dumps(task.fix_instructions, indent=2) if task.fix_instructions else ""}

Please analyze and output your decision as JSON.
"""
        response = self.call_claude(
            task.task_id, "generator", user_prompt, sys_prompt,
            allowed_tools="Read,Bash",
        )
        data = self.extract_json(response)

        # Save decomp plan
        plan_path = self.run_dir / "nodes" / task.task_id / "decomp_plan.json"
        plan_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        return DecompositionPlan(
            should_decompose=data.get("should_decompose", False),
            child_tasks=data.get("child_tasks", []),
            svg=data.get("svg", ""),
            reasoning=data.get("reasoning", ""),
        )

    # ------------------------------------------------------------------
    # Intermediate node: children -> merge -> critic -> repair
    # ------------------------------------------------------------------

    def _execute_intermediate(
        self, task: TaskPackage, plan: DecompositionPlan
    ) -> NodeReport:
        node_id = task.task_id
        node_dir = self.run_dir / "nodes" / node_id

        # Execute children
        child_reports: Dict[str, NodeReport] = {}
        for child_spec in plan.child_tasks:
            child_task = TaskPackage(
                task_id=child_spec["task_id"],
                description=child_spec.get("description", ""),
                paper_excerpt=child_spec.get("paper_excerpt", task.paper_excerpt[:1500]),
                canvas=child_spec.get("canvas", {"w": 300, "h": 200}),
                global_style=task.global_style,
                required_ports=child_spec.get("required_ports", {}),
                depth=task.depth + 1,
                max_depth=task.max_depth,
                parent_id=node_id,
            )
            child_reports[child_task.task_id] = self.execute_node(child_task)

        # Merge via SVG Worker
        merged_svg = self._call_svg_worker_merge(
            task, child_reports, plan.child_tasks
        )

        # Save merged SVG + render PNG
        merged_svg_path = str(node_dir / "merged.svg")
        merged_png_path = str(node_dir / "merged.png")
        Path(merged_svg_path).write_text(merged_svg, encoding="utf-8")
        self.render_png(merged_svg_path, merged_png_path)

        # Critic loop
        for retry in range(self.max_retries + 1):
            issues = self._call_critic(node_id, merged_svg_path, merged_png_path)

            critical = [i for i in issues if i.get("severity") == "critical"]
            warnings = [i for i in issues if i.get("severity") == "warning"]

            # Save issues
            (node_dir / f"issues_round{retry}.json").write_text(
                json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            if not critical:
                print(f"  [{node_id}] Passed critic (round {retry}, {len(warnings)} warnings)")
                break

            if retry >= self.max_retries:
                print(f"  [{node_id}] Max retries reached, proceeding with {len(critical)} critical issues")
                break

            print(f"  [{node_id}] {len(critical)} critical issues, fixing (round {retry+1})")

            # SVG Worker fixes
            merged_svg = self._call_svg_worker_fix(
                node_id, merged_svg, issues
            )
            Path(merged_svg_path).write_text(merged_svg, encoding="utf-8")
            self.render_png(merged_svg_path, merged_png_path)

        return NodeReport(
            task_id=node_id,
            status="ok",
            svg=merged_svg,
            bbox={"w": task.canvas["w"], "h": task.canvas["h"]},
            ports=task.required_ports,
            issues_remaining=warnings if 'warnings' in dir() else [],
        )

    # ------------------------------------------------------------------
    # Leaf node: generate → critic → fix
    # ------------------------------------------------------------------

    def _execute_leaf(
        self, task: TaskPackage, plan: DecompositionPlan
    ) -> NodeReport:
        node_id = task.task_id
        node_dir = self.run_dir / "nodes" / node_id

        svg = plan.svg
        if not svg:
            # Generator didn't provide SVG in decomp response, call again
            svg = self._call_generator_leaf(task)

        # Save and render
        svg_path = str(node_dir / "output.svg")
        png_path = str(node_dir / "output.png")
        Path(svg_path).write_text(svg, encoding="utf-8")
        self.render_png(svg_path, png_path)

        # Critic loop
        warnings = []
        for retry in range(self.max_retries + 1):
            issues = self._call_critic(node_id, svg_path, png_path)

            critical = [i for i in issues if i.get("severity") == "critical"]
            warnings = [i for i in issues if i.get("severity") == "warning"]

            (node_dir / f"issues_round{retry}.json").write_text(
                json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            if not critical:
                print(f"  [{node_id}] Leaf passed critic (round {retry})")
                break

            if retry >= self.max_retries:
                break

            print(f"  [{node_id}] Leaf fixing {len(critical)} issues (round {retry+1})")
            svg = self._call_svg_worker_fix(node_id, svg, issues)
            Path(svg_path).write_text(svg, encoding="utf-8")
            self.render_png(svg_path, png_path)

        return NodeReport(
            task_id=node_id,
            status="ok",
            svg=svg,
            bbox={"w": task.canvas["w"], "h": task.canvas["h"]},
            ports=task.required_ports,
            issues_remaining=warnings,
        )

    def _call_generator_leaf(self, task: TaskPackage) -> str:
        """Dedicated leaf generation call — forces SVG output."""
        sys_prompt = _read_prompt("generator")
        user_prompt = f"""## Task (LEAF NODE — generate SVG directly)
{task.description}

## Paper Excerpt
{task.paper_excerpt[:2000]}

## Canvas
Width: {task.canvas['w']}px, Height: {task.canvas['h']}px

## Required Ports
{json.dumps(task.required_ports, indent=2)}

## Global Style
{json.dumps(task.global_style, indent=2)}

You MUST generate SVG directly. Output JSON with "should_decompose": false and "svg": "<svg>...</svg>".
"""
        response = self.call_claude(
            task.task_id, "generator_leaf", user_prompt, sys_prompt,
            allowed_tools="Read,Bash",
        )
        data = self.extract_json(response)
        return data.get("svg", "")

    # ------------------------------------------------------------------
    # Critic call
    # ------------------------------------------------------------------

    def _call_critic(
        self, node_id: str, svg_path: str, png_path: str
    ) -> List[Dict]:
        sys_prompt = _read_prompt("critic")

        svg_code = Path(svg_path).read_text(encoding="utf-8")
        # Truncate SVG if too long for prompt
        svg_for_prompt = svg_code[:5000] if len(svg_code) > 5000 else svg_code

        user_prompt = f"""## SVG Code
```xml
{svg_for_prompt}
```

## Rendered PNG
I've rendered this SVG to PNG. Please read the image file at:
{png_path}

Use the Read tool to view the PNG image, then also examine the SVG code above.
Identify all visual and structural issues. Output a JSON array of issues.
"""
        response = self.call_claude(
            node_id, "critic", user_prompt, sys_prompt,
            allowed_tools="Read,Bash",
        )
        data = self.extract_json(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "error" not in data:
            return [data]
        return []

    # ------------------------------------------------------------------
    # SVG Worker: merge children
    # ------------------------------------------------------------------

    def _call_svg_worker_merge(
        self,
        task: TaskPackage,
        child_reports: Dict[str, NodeReport],
        child_specs: List[Dict],
    ) -> str:
        sys_prompt = _read_prompt("svg_worker")

        children_info = []
        for spec in child_specs:
            cid = spec["task_id"]
            report = child_reports.get(cid)
            if report and report.svg:
                children_info.append({
                    "task_id": cid,
                    "canvas": spec.get("canvas", {}),
                    "required_ports": spec.get("required_ports", {}),
                    "svg_length": len(report.svg),
                })

        # Save all child SVGs to files for the worker to read
        node_dir = self.run_dir / "nodes" / task.task_id
        child_svg_paths = {}
        for spec in child_specs:
            cid = spec["task_id"]
            report = child_reports.get(cid)
            if report and report.svg:
                p = node_dir / f"child_{cid}.svg"
                p.write_text(report.svg, encoding="utf-8")
                child_svg_paths[cid] = str(p)

        user_prompt = f"""## Merge Task
Merge the following child SVG fragments into a single SVG.

## Parent Canvas
Width: {task.canvas['w']}px, Height: {task.canvas['h']}px

## Global Style
{json.dumps(task.global_style, indent=2)}

## Children to merge
{json.dumps(children_info, indent=2)}

## Child SVG files (use Read tool to access them):
{json.dumps(child_svg_paths, indent=2)}

## Instructions
1. Read each child SVG file
2. Place them in a left-to-right layout within the parent canvas
3. Add connection arrows between them based on the data flow
4. Define shared <defs> (gradients, markers, filters) at the top
5. Enforce MIN_ARROW_DISTANCE from global_style: every marker-ended arrow must have at least 20px straight length, or at least 20px in the terminal segment before the marker for L/bracket routes. If too short, move the target child and downstream dependent children, then recompute ports and arrow paths.
6. Keep unrelated children compact and non-overlapping; do not force 48px gaps unless the layout needs them.
7. Snap all coords to the active grid from global_style
8. Set canvas size to fit everything with 24px padding

Output JSON with "svg", "bbox", "ports", and "changes_made".
"""
        response = self.call_claude(
            task.task_id, "svg_worker_merge", user_prompt, sys_prompt,
            allowed_tools="Read,Write,Bash,Edit",
        )
        data = self.extract_json(response)
        return data.get("svg", "")

    # ------------------------------------------------------------------
    # SVG Worker: apply fixes
    # ------------------------------------------------------------------

    def _call_svg_worker_fix(
        self, node_id: str, current_svg: str, issues: List[Dict]
    ) -> str:
        sys_prompt = _read_prompt("svg_worker")

        # Save current SVG for worker to read
        node_dir = self.run_dir / "nodes" / node_id
        fix_svg_path = node_dir / "to_fix.svg"
        fix_svg_path.write_text(current_svg, encoding="utf-8")

        # Truncate SVG in prompt, tell worker to read file for full version
        svg_preview = current_svg[:3000]

        user_prompt = f"""## Fix Task
Apply the following fixes to the SVG.

## Issues to fix
{json.dumps(issues, indent=2)}

## Current SVG (preview — full file at {fix_svg_path})
```xml
{svg_preview}
```

Read the full SVG from {fix_svg_path}, apply all fixes, then output JSON with the complete fixed SVG.
"""
        response = self.call_claude(
            node_id, "svg_worker_fix", user_prompt, sys_prompt,
            allowed_tools="Read,Edit,Bash",
        )
        data = self.extract_json(response)
        return data.get("svg", current_svg)

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _save_manifest(self):
        manifest_path = self.run_dir / "run_manifest.json"
        manifest_path.write_text(
            json.dumps(self.manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
