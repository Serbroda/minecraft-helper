import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipIf(os.name == "nt", "Benötigt eine POSIX-Shell")
class ShellStarterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.starter = self.base / "folder with spaces" / "update.sh"
        self.starter.parent.mkdir()
        shutil.copyfile(Path(__file__).with_name("update.sh"), self.starter)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.log = self.base / "calls"
        self.env = {**os.environ, "PATH": str(self.bin), "CALL_LOG": str(self.log)}
        self.executable("dirname", '#!/bin/sh\nexec /usr/bin/dirname "$@"\n')
        self.executable("python3", '#!/bin/sh\nprintf "python:%s\\n" "$@" >> "$CALL_LOG"\nexit "${PYTHON_RESULT:-0}"\n')

    def executable(self, name, content):
        path = self.bin / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)

    def git(self):
        self.executable("git", '''#!/bin/sh
printf 'git:%s\n' "$@" >> "$CALL_LOG"
case "$3" in
    rev-parse) exit "${REPO_RESULT:-0}" ;;
    pull) exit "${PULL_RESULT:-0}" ;;
    *) exit 99 ;;
esac
''')

    def run_starter(self, **env):
        result = subprocess.run(
            ["/bin/sh", str(self.starter), "-c", "config with spaces.json", "--dry-run"],
            cwd=self.base, env={**self.env, **env}, input="\n",
            capture_output=True, text=True, timeout=10,
        )
        return result, self.log.read_text(encoding="utf-8")

    def test_pull_precedes_python_and_preserves_arguments(self):
        self.git()
        result, calls = self.run_starter()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"git:-C\ngit:{self.starter.parent}\ngit:pull\ngit:--ff-only\n", calls)
        self.assertLess(calls.index("git:pull"), calls.index("python:"))
        self.assertIn("python:-c\npython:config with spaces.json\npython:--dry-run\n", calls)

    def test_pull_failure_prevents_python(self):
        self.git()
        result, calls = self.run_starter(PULL_RESULT="1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("python:", calls)
        self.assertIn("git pull fehlgeschlagen", result.stderr)

    def test_no_repository_skips_pull(self):
        self.git()
        result, calls = self.run_starter(REPO_RESULT="1")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("git:pull", calls)
        self.assertIn("python:", calls)
        self.assertIn("Kein Git-Repository", result.stdout)

    def test_missing_git_still_starts_python(self):
        result, calls = self.run_starter()
        self.assertEqual(result.returncode, 0)
        self.assertIn("Git nicht installiert", result.stdout)
        self.assertIn("python:", calls)

    def test_python_failure_is_propagated(self):
        self.git()
        result, _ = self.run_starter(PYTHON_RESULT="7")
        self.assertEqual(result.returncode, 7)


if __name__ == "__main__":
    unittest.main()
