"""Check that exported voices are usable on their own and remain isolated."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


EXPORT = Path(__file__).resolve().parents[1] / "scripts" / "export_voice.py"


def profile(identifier, wording):
    return {
        "schema_version": 1,
        "id": identifier,
        "display_name": "示例团队",
        "version": "1.0.0",
        "shared_rules": [{
            "when": "审阅表达",
            "write": wording,
            "preserve": "保留原文已确认的事实、引文和请求。",
            "exception": "当前文书有指定次序时遵守该次序。",
        }],
        "genres": [],
        "examples": [],
    }


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.export_dir = self.root / "generated"

    def run_export(self, specification):
        source = self.root / "input.json"
        source.write_text(json.dumps(specification, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(EXPORT), str(source), str(self.export_dir)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_two_teams_export_separately(self):
        choices = {
            "team-a-voice": "先说明原裁判认定。",
            "team-b-voice": "先列对方所据材料。",
        }
        for identifier, sentence in choices.items():
            with self.subTest(identifier=identifier):
                result = self.run_export(profile(identifier, sentence))
                self.assertEqual(result.returncode, 0, result.stderr)
        for identifier, sentence in choices.items():
            skill = self.export_dir / identifier
            self.assertTrue((skill / "SKILL.md").is_file())
            product = "\n".join(file.read_text(encoding="utf-8") for file in skill.rglob("*.md"))
            self.assertIn(sentence, product)
            for other in set(choices.values()) - {sentence}:
                self.assertNotIn(other, product)

    def test_bad_identifier_and_extra_fields_make_no_package(self):
        for bad in (profile("../escape", "改写规则。"), {
            **profile("team-c-voice", "改写规则。"),
            "private_source": "source.docx",
        }):
            with self.subTest(identifier=bad["id"]):
                self.assertNotEqual(self.run_export(bad).returncode, 0)
        self.assertEqual(list(self.export_dir.iterdir()) if self.export_dir.exists() else [], [])
        self.assertFalse((self.root / "escape").exists())

    def test_repeated_export_preserves_first_version(self):
        first = profile("team-a-voice", "先交代法庭认定。")
        result = self.run_export(first)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = self.export_dir / "team-a-voice"
        old = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
        result = self.run_export(profile("team-a-voice", "先交代证据。"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(old, {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
