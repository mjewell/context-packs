#!/usr/bin/env python3
"""Write the review job's prompt and claude_args as step outputs. Its agent runs the pack-findings skill on the
reviewed range, as a local review does, so both run the wizard the same way."""
import argparse

import args as claude


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--base', required=True, help='the commit the reviewed change starts from')
    parser.add_argument('--head', required=True, help='the commit that is reviewed')
    parser.add_argument('--model', default='', help="the model to review with, if not Claude Code's default")
    args = parser.parse_args()
    claude.output('prompt', f'Use the pack-findings skill on the commit range {args.base}..{args.head}.')
    claude.output('claude-args', claude.reviewer(args.model))


if __name__ == '__main__':
    main()
