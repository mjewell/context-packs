#!/usr/bin/env python3
"""Write one finder's record for the merge job: its answer, cleaned, and who read each of its unit's docs in full, from
its transcript. It runs in the finder's job, so the transcript, which can hold file
contents, never leaves it."""
import argparse
import json
import os
from pathlib import Path

import reads
from report import findings_in
import units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit', type=int, required=True, help="the unit's number, from units.py list")
    parser.add_argument('--docs', type=Path, required=True, help='what `context-packs docs` printed')
    parser.add_argument('--findings', type=Path, required=True, help="the finder's structured output")
    parser.add_argument('--transcript', type=Path, required=True,
                        help="the finder's claude-execution-output.json, from claude-code-action")
    parser.add_argument('--out', type=Path, required=True, help='where to write the record')
    args = parser.parse_args()
    name = f"unit {args.unit}'s finder"
    messages = json.loads(args.transcript.read_text(encoding='utf-8'))
    record = {'unit': args.unit, 'findings': findings_in(args.findings),
              'docs': reads.readers(messages, units.units(args.docs)[args.unit], os.path.realpath('.'), name)}
    args.out.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
