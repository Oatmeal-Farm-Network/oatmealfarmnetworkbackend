"""
Move top-level `with engine.begin()` blocks into lazy `_ensure_schema()`,
and attach `dependencies=[Depends(_schema_dep)]` on the module router.

Usage:
  python scripts/lazy_schema_ast.py
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"

TARGETS = [
    "sfproducts.py",
    "supplier_directory.py",
    "provenance.py",
    "mill.py",
    "notifications.py",
    "market_alerts.py",
    "job_board.py",
    "land_leasing.py",
    "grants.py",
    "food_wanted.py",
    "field_health_alerts.py",
    "equipment_marketplace.py",
    "education.py",
    "csa.py",
    "commodity_history.py",
    "certifications.py",
    "marketplace.py",
]


class EngineBeginFinder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.spans: list[tuple[int, int]] = []  # 1-based inclusive line numbers

    def visit_With(self, node: ast.With) -> None:
        # Only top-level with (parent is Module) — visitor doesn't track parent,
        # so caller only walks module.body
        pass


def top_level_engine_begins(tree: ast.Module) -> list[tuple[int, int]]:
    spans = []
    for node in tree.body:
        if isinstance(node, ast.With) and node.end_lineno:
            for item in node.items:
                ctx = item.context_expr
                if (
                    isinstance(ctx, ast.Call)
                    and isinstance(ctx.func, ast.Attribute)
                    and ctx.func.attr == "begin"
                    and isinstance(ctx.func.value, ast.Name)
                    and ctx.func.value.id == "engine"
                ):
                    spans.append((node.lineno, node.end_lineno))
                    break
        # Also pull preceding Assign of seed constants immediately before a begin block
    return spans


def expand_with_seed_assigns(lines: list[str], spans: list[tuple[int, int]]) -> tuple[int, int]:
    """Return one region (0-based start, end exclusive) covering all begins + seed assigns between."""
    if not spans:
        raise ValueError("no spans")
    start = spans[0][0] - 1
    end = spans[-1][1]  # already 1-based end_lineno inclusive -> exclusive index = end_lineno

    # Include assignment / comment / blank lines between first and last
    # Expand backward for seed assigns / section comments before first with
    i = start - 1
    while i >= 0:
        s = lines[i].strip()
        if s == "" or s.startswith("#") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", lines[i]):
            # stop if we hit router assignment
            if lines[i].lstrip().startswith("router") or "APIRouter" in lines[i]:
                break
            if lines[i].startswith("def ") or lines[i].startswith("class ") or lines[i].startswith("from ") or lines[i].startswith("import "):
                break
            start = i
            i -= 1
            continue
        break
    return start, end


def transform(path: Path) -> None:
    src = path.read_text(encoding="utf-8", errors="replace")
    if "def _ensure_schema()" in src:
        print(f"skip (done) {path.name}")
        return
    tree = ast.parse(src)
    spans = top_level_engine_begins(tree)
    if not spans:
        print(f"skip (none) {path.name}")
        return

    lines = src.splitlines()
    region_start, region_end = expand_with_seed_assigns(lines, spans)
    body = lines[region_start:region_end]
    label = path.stem.replace("_", "-")

    ensure_lines = [
        "_schema_ready = False",
        "",
        "",
        "def _ensure_schema() -> None:",
        '    """Lazy schema/seed — never runs at import time."""',
        "    global _schema_ready",
        "    if _schema_ready:",
        "        return",
        "    from app.schema_ensure import run_schema_ensure, skip_schema_ensure",
        "    if skip_schema_ensure():",
        "        return",
        "",
        "    def _run() -> None:",
        "        global _schema_ready",
    ]
    for bl in body:
        ensure_lines.append(("        " + bl) if bl.strip() else "        ")
    ensure_lines += [
        "        _schema_ready = True",
        "",
        f'    run_schema_ensure("{label}", _run)',
        "",
        "",
        "def _schema_dep() -> None:",
        "    _ensure_schema()",
        "",
    ]

    # Remove region from lines
    new_lines = lines[:region_start] + lines[region_end:]
    text = "\n".join(new_lines) + "\n"

    # Ensure Depends imported
    def fix_fastapi_import(m: re.Match) -> str:
        names = m.group(1)
        if "Depends" in names:
            return m.group(0)
        return f"from fastapi import APIRouter, Depends, {names}" if names.strip() else "from fastapi import APIRouter, Depends"

    if re.search(r"from fastapi import ([^\n]+)", text):
        text = re.sub(
            r"from fastapi import ([^\n]+)",
            lambda m: (
                m.group(0)
                if "Depends" in m.group(1)
                else (
                    f"from fastapi import Depends, {m.group(1)}"
                    if "APIRouter" in m.group(1)
                    else f"from fastapi import {m.group(1)}, Depends"
                )
            ),
            text,
            count=1,
        )
        text = text.replace("Depends, Depends", "Depends")

    # Insert ensure block before first *router* = APIRouter(
    m = re.search(r"^(\w*router\w*\s*=\s*APIRouter\()", text, flags=re.M | re.I)
    if not m:
        raise RuntimeError(f"{path.name}: no APIRouter assignment")

    insert_pos = m.start()
    text = text[:insert_pos] + "\n".join(ensure_lines) + "\n" + text[insert_pos:]

    # Add dependencies to APIRouter( ... )
    def add_dep(match: re.Match) -> str:
        full = match.group(0)
        if "_schema_dep" in full:
            return full
        # single-line preferred
        if "\n" not in full:
            inner = full[len("APIRouter(") : -1]
            if inner.strip():
                return f"APIRouter({inner}, dependencies=[Depends(_schema_dep)])"
            return "APIRouter(dependencies=[Depends(_schema_dep)])"
        # multiline: insert before closing paren
        return full[:-1] + ", dependencies=[Depends(_schema_dep)])"

    text, n = re.subn(r"APIRouter\([\s\S]*?\)", add_dep, text, count=1)
    if n != 1:
        raise RuntimeError(f"{path.name}: failed to patch APIRouter ({n})")

    # Validate
    ast.parse(text)
    # Order check
    if text.find("def _schema_dep") > text.find("dependencies=[Depends(_schema_dep)]"):
        raise RuntimeError(f"{path.name}: bad order")

    path.write_text(text, encoding="utf-8")
    print(f"ok {path.name}")


def main() -> None:
    for name in TARGETS:
        transform(ROOT / name)


if __name__ == "__main__":
    main()
