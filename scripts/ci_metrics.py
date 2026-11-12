#!/usr/bin/env python3
"""Write optional Shields metric payloads from this run's JUnit/coverage XML.

The caller must supply the test process exit code and remove stale reports before
running tests. This helper reports metrics; it does not replace the CI test gate.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from html import escape
from pathlib import Path
import xml.etree.ElementTree as ET


def tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def read_counts(path: Path) -> tuple[int, int, int, int]:
    """Return total, failures, errors, skipped without counting parent suites twice."""
    root = ET.parse(path).getroot()
    suites = [node for node in root.iter() if tag(node) == "testsuite"]
    leaves = [
        node for node in suites
        if not any(child is not node and tag(child) == "testsuite" for child in node.iter())
    ]
    if not leaves and tag(root) == "testsuites" and "tests" in root.attrib:
        leaves = [root]
    declared = None
    if leaves and all("tests" in node.attrib for node in leaves):
        counts = [0, 0, 0, 0]
        for suite in leaves:
            values = [int(suite.attrib.get(key, "0")) for key in ("tests", "failures", "errors", "skipped")]
            if any(value < 0 for value in values) or sum(values[1:]) > values[0]:
                raise ValueError("Inconsistent suite counts")
            counts = [a + b for a, b in zip(counts, values)]
        declared = tuple(counts)

    cases = [node for node in root.iter() if tag(node) == "testcase"]
    if cases:
        failures = errors = skipped = 0
        for case in cases:
            statuses = {tag(child) for child in case}
            if "error" in statuses:
                errors += 1
            elif "failure" in statuses:
                failures += 1
            elif "skipped" in statuses:
                skipped += 1
        observed = (len(cases), failures, errors, skipped)
        if declared is not None and declared != observed:
            raise ValueError("Suite summary and testcase results disagree")
        return observed
    if declared is None:
        raise ValueError("No testcase elements or suite counts")
    return declared


def badge(label: str, message: str, color: str) -> dict[str, object]:
    return {"schemaVersion": 1, "label": label, "message": message, "color": color}


def prepare(junit: Path, coverage: Path, exit_code: int) -> dict[str, dict[str, object]]:
    completed = False
    try:
        total, failures, errors, skipped = read_counts(junit)
        passed = total - failures - errors - skipped
        parts = [f"{passed} passed"]
        if failures:
            parts.append(f"{failures} failed")
        if errors:
            parts.append(f"{errors} errors")
        if skipped:
            parts.append(f"{skipped} skipped")
        if exit_code != 0:
            parts.append("run failed")
        if failures or errors or exit_code != 0:
            color = "red"
        elif passed == 0:
            color = "yellow"
            if total == 0:
                parts = ["no test results"]
        else:
            color = "brightgreen"
            completed = True
        tests_badge = badge("tests", ", ".join(parts), color)
    except (OSError, ET.ParseError, ValueError, TypeError):
        message = "run failed; report unavailable" if exit_code != 0 else "report unavailable"
        tests_badge = badge("tests", message, "red" if exit_code != 0 else "lightgrey")

    coverage_badge = badge("coverage", "unavailable", "lightgrey")
    if completed:
        try:
            coverage_root = ET.parse(coverage).getroot()
            rate = float(coverage_root.attrib["line-rate"])
            if not math.isfinite(rate) or not 0 <= rate <= 1:
                raise ValueError("Invalid coverage rate")
            coverage_badge = badge("coverage", f"{rate * 100:.1f}%", "blue")
        except (OSError, ET.ParseError, KeyError, ValueError, TypeError):
            pass
    return {"tests.json": tests_badge, "coverage.json": coverage_badge}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--build-status", choices=['success','failure','cancelled','skipped'], required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    payloads = prepare(args.junit, args.coverage, args.exit_code)
    payloads['build.json'] = badge('build', args.build_status,
        'brightgreen' if args.build_status == 'success' else 'red')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in payloads.items():
        (args.output_dir / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / ('ci-'+filename.replace('.json','.svg'))).write_text(
            render(str(payload['label']), str(payload['message']), str(payload['color']),
                   f"{args.source_sha} · {args.run_url}"), encoding='utf-8')
    print(json.dumps({name: payload["message"] for name, payload in payloads.items()}))


def render(label: str, message: str, color: str, source: str) -> str:
    """Render private report badges in the compact Shields flat style."""
    colors = {'red':'#e05d44','brightgreen':'#4c1','yellow':'#dfb317',
              'lightgrey':'#9f9f9f','blue':'#007ec6'}
    title = escape(f'{label}: {message}. Source: {source}', quote=True)
    # Keep complete report counts in the tooltip/JSON, without widening a
    # successful test badge for skips. Never hide failures or unavailable data.
    if label == 'tests' and color == 'brightgreen':
        passed = re.fullmatch(r'(\d+ passed)(?:, \d+ skipped)?', message)
        if passed:
            message = passed.group(1)
    left, right = 10+6*len(label), 10+6*len(message)
    width = left+right
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" '
        f'role="img" aria-label="{title}"><title>{title}</title>'
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{width}" height="20" rx="3"/></clipPath>'
        '<g clip-path="url(#r)">'
        f'<rect width="{left}" height="20" fill="#555"/>'
        f'<rect x="{left}" width="{right}" height="20" fill="{colors[color]}"/>'
        f'<rect width="{width}" height="20" fill="url(#s)"/></g>'
        '<g fill="#fff" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        'font-size="11" text-anchor="middle" text-rendering="geometricPrecision">'
        '<g fill="#010101" fill-opacity=".3" aria-hidden="true">'
        f'<text x="{left/2}" y="15">{escape(label)}</text>'
        f'<text x="{left+right/2}" y="15">{escape(message)}</text></g>'
        f'<text x="{left/2}" y="14">{escape(label)}</text>'
        f'<text x="{left+right/2}" y="14">{escape(message)}</text></g></svg>\n')


if __name__ == "__main__":
    main()
