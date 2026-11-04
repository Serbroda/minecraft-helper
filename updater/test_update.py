import contextlib
import functools
import http.server
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import update


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = tempfile.TemporaryDirectory()
        handler = functools.partial(QuietHandler, directory=cls.web.name)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        Path(cls.web.name, "mod.jar").write_bytes(b"new mod")
        with zipfile.ZipFile(Path(cls.web.name, "pack.zip"), "w") as archive:
            archive.writestr("mods/example.jar", b"zip mod")
            archive.writestr("shaderpacks/shader.zip", b"shader")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.web.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS's system temp path may contain /var -> /private/var. Use its
        # canonical spelling; user-configured destination links stay forbidden.
        self.base = Path(self.temp.name).resolve()
        self.staging = self.base / "staging"
        self.staging.mkdir()
        self.target = self.base / "mods"

    def config(self, **source):
        return {"targets": [{"directory": "mods", **source}]}

    def prepare(self, config):
        with contextlib.redirect_stdout(io.StringIO()):
            return update.prepare(config, self.base, self.staging)

    def run_main(self, config, *args, answer="n"):
        path = self.base / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with patch("builtins.input", return_value=answer) as prompt:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = update.main(["-c", str(path), *args])
        return result, prompt

    def test_url_preview_replace_new_unchanged_and_no_deletion(self):
        self.target.mkdir()
        (self.target / "mod.jar").write_bytes(b"old")
        (self.target / "keep.jar").write_bytes(b"leave alone")
        (self.target / "same.jar").write_bytes(b"new mod")
        plan = self.prepare(self.config(urls=[
            self.url + "/mod.jar",
            {"url": self.url + "/mod.jar?download=1", "filename": "nested/new.jar"},
            {"url": self.url + "/mod.jar", "filename": "same.jar"},
        ]))
        self.assertEqual([p["action"] for p in plan], ["ERSETZEN", "NEU", "GLEICH"])
        self.assertEqual((self.target / "mod.jar").read_bytes(), b"old")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(update.apply(plan), 2)
        self.assertEqual((self.target / "nested/new.jar").read_bytes(), b"new mod")
        self.assertEqual((self.target / "keep.jar").read_bytes(), b"leave alone")

    def test_remote_zip_prefix(self):
        plan = self.prepare(self.config(zip=self.url + "/pack.zip", zip_prefix="mods"))
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["destination"], self.target / "example.jar")
        self.assertEqual(plan[0]["source"].read_bytes(), b"zip mod")
        self.assertFalse(self.target.exists())

    def test_local_zip_all_files_and_multiple_targets(self):
        archive = self.base / "local.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("nested/resource.zip", b"resource")
        config = self.config(zip="local.zip")
        config["targets"].append({"directory": "shaders", "urls": [self.url + "/mod.jar"]})
        plan = self.prepare(config)
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0]["destination"], self.target / "nested/resource.zip")

    def test_confirmation_no_yes_force_and_dry_run(self):
        config = self.config(urls=[self.url + "/mod.jar"])
        result, prompt = self.run_main(config)
        self.assertEqual(result, 0)
        prompt.assert_called_once()
        self.assertFalse(self.target.exists())
        result, prompt = self.run_main(config, "--dry-run", "-y")
        self.assertEqual(result, 0)
        prompt.assert_not_called()
        self.assertFalse(self.target.exists())
        for flag in ("-y", "-f"):
            result, prompt = self.run_main(config, flag)
            self.assertEqual(result, 0)
            prompt.assert_not_called()
            self.assertEqual((self.target / "mod.jar").read_bytes(), b"new mod")
            (self.target / "mod.jar").unlink()
        result, _ = self.run_main(config, answer="ja")
        self.assertEqual(result, 0)
        self.assertTrue((self.target / "mod.jar").exists())

    def test_download_failure_leaves_targets_untouched(self):
        result, _ = self.run_main(self.config(urls=[self.url + "/mod.jar", self.url + "/missing.jar"]), "-y")
        self.assertEqual(result, 1)
        self.assertFalse(self.target.exists())

    def test_unsafe_paths(self):
        for name in ("../evil", "/absolute", "C:/evil", "a\\evil", "a/../b", "NUL.txt", "trailing.", "a//b"):
            with self.subTest(name=name), self.assertRaises(update.UpdateError):
                update.relative_path(name)

    def test_zip_traversal_and_symlink_rejected(self):
        archive = self.base / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../evil", b"bad")
        with self.assertRaises(update.UpdateError):
            self.prepare(self.config(zip="bad.zip"))
        with zipfile.ZipFile(archive, "w") as bundle:
            entry = zipfile.ZipInfo("link")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(entry, "elsewhere")
        # A fresh staging directory, as each real invocation uses.
        self.staging = self.base / "stage2"
        self.staging.mkdir()
        with self.assertRaises(update.UpdateError):
            self.prepare(self.config(zip="bad.zip"))

    def test_target_symlink_rejected(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        try:
            self.target.symlink_to(elsewhere, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks auf diesem System nicht verfügbar: {error}")
        with self.assertRaises(update.UpdateError):
            self.prepare(self.config(urls=[self.url + "/mod.jar"]))

    def test_duplicate_destinations_rejected_case_insensitively(self):
        with self.assertRaises(update.UpdateError):
            self.prepare(self.config(urls=[
                {"url": self.url + "/mod.jar", "filename": "a.jar"},
                {"url": self.url + "/mod.jar", "filename": "A.jar"},
            ]))

    def test_edit_after_preview_rejected(self):
        plan = self.prepare(self.config(urls=[self.url + "/mod.jar"]))
        self.target.mkdir()
        (self.target / "mod.jar").write_bytes(b"user edit")
        with self.assertRaises(update.UpdateError):
            update.apply(plan)
        self.assertEqual((self.target / "mod.jar").read_bytes(), b"user edit")

    def test_zip_size_limit(self):
        archive = self.base / "large.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("a.jar", b"123456789")
        with patch.object(update, "MAX_BYTES", 5), self.assertRaises(update.UpdateError):
            self.prepare(self.config(zip="large.zip"))


if __name__ == "__main__":
    unittest.main()
