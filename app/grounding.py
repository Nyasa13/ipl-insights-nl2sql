"""Grounding check: every number the LLM states in its summary must be traceable to the query result
(or to the question itself). Anything else is an 'unsupported numeric claim'."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUM_RE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")


def extract_numbers(text: str) -> list[tuple[str, float, int]]:
    """Return (raw, value, decimals) for every number in text."""
    out = []
    for m in NUM_RE.finditer(text or ""):
        raw = m.group(0)
        clean = raw.replace(",", "").rstrip("%")
        try:
            val = float(clean)
        except ValueError:
            continue
        decimals = len(clean.split(".")[1]) if "." in clean else 0
        out.append((raw, val, decimals))
    return out


@dataclass
class GroundingResult:
    claims: int = 0
    unsupported: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return not self.unsupported


def _source_numbers(question: str, columns: list[str], rows: list[tuple]) -> list[float]:
    nums: list[float] = []
    for _, v, _ in extract_numbers(question):
        nums.append(v)
    for r in rows:
        for cell in r:
            if isinstance(cell, bool) or cell is None:
                continue
            if isinstance(cell, (int, float)):
                nums.append(float(cell))
            else:  # dates and text can contain numbers: "2023-05-21", "Over 19"
                for m in re.finditer(r"\d+(?:\.\d+)?", str(cell)):
                    nums.append(float(m.group(0)))
    for c in columns:  # column names like "runs_2023"
        for m in re.finditer(r"\d+", str(c)):
            nums.append(float(m.group(0)))
    nums.append(float(len(rows)))
    nums.extend(float(i) for i in range(1, len(rows) + 1))  # rank positions (#1, #2 ...)
    return nums


def check_grounding(summary: str, question: str, columns: list[str], rows: list[tuple]) -> GroundingResult:
    sources = _source_numbers(question, columns, rows)
    res = GroundingResult()
    for raw, val, decimals in extract_numbers(summary):
        res.claims += 1
        tol = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(val - s) <= tol for s in sources):
            res.unsupported.append(raw)
    return res


def template_summary(question: str, columns: list[str], rows: list[tuple]) -> str:
    """Deterministic fallback; grounded by construction because it only prints table values."""
    if not rows:
        return "No matching data was found for that question."
    if len(rows) == 1 and len(columns) == 1:
        return f"{columns[0].replace('_', ' ')}: {rows[0][0]}."
    first = ", ".join(f"{c.replace('_', ' ')}: {v}" for c, v in zip(columns, rows[0]))
    more = f" ({len(rows)} rows returned.)" if len(rows) > 1 else ""
    return f"Top result - {first}.{more}"
