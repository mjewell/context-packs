import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
NPX = re.compile(r'npx (?:--yes )?context-packs(?:@[\w.-]+)?')


class SkillPinTests(unittest.TestCase):
    """Each skill runs the CLI version it was written for, so a version published later can't change what it runs."""

    def test_every_npx_command_in_a_skill_pins_the_packages_version(self):
        version = json.loads((ROOT / 'package.json').read_text())['version']
        commands = [(path.relative_to(ROOT).as_posix(), m.group(0))
                    for path in sorted((ROOT / 'skills').glob('*/SKILL.md'))
                    for m in NPX.finditer(path.read_text())]

        self.assertTrue(commands, 'no skill runs npx context-packs')
        self.assertEqual([c for c in commands if not c[1].endswith(f'context-packs@{version}')], [])


if __name__ == '__main__':
    unittest.main()
