"""
Parse the pytest junit-xml report and write a markdown summary to
stdout. Called by .github/workflows/ci.yml — its output is appended
to $GITHUB_STEP_SUMMARY so failing-test details are visible on the
GitHub Actions job page without repo-admin auth.

Usage:
    python scripts/ci_summarize_pytest.py /tmp/pytest_report.xml

Embeds the failing test class::name pairs + the first 200 chars of
each failure message.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(path: str) -> int:
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError:
        print('(junit xml not found)')
        return 1
    except ET.ParseError as exc:
        print(f'(junit xml parse error: {exc})')
        return 1

    failed = []
    for tc in root.iter('testcase'):
        failures = list(tc.iter('failure')) + list(tc.iter('error'))
        if not failures:
            continue
        cls = tc.get('classname', '?')
        name = tc.get('name', '?')
        msgs = []
        for f in failures:
            msg = (f.get('message') or '').strip()
            if msg:
                msgs.append(msg[:200])
        failed.append((cls, name, msgs))

    if not failed:
        print('(no failures recorded — runner may have crashed before pytest started)')
        return 0

    print(f'**{len(failed)} test(s) failed:**')
    print()
    for cls, name, msgs in failed:
        print(f'- `{cls}::{name}`')
        for m in msgs:
            # Markdown-safe: collapse newlines, escape backticks lightly.
            cleaned = m.replace('`', "'").replace('\n', ' ')
            print(f'  - {cleaned}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '/tmp/pytest_report.xml'))
