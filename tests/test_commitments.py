"""Contract tests for the promise ledger. stdlib only: python tests/test_commitments.py"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import commitments as C  # noqa: E402


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.path = C.store_path(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_then_open(self):
        rec = C.add("今晚做 REA", "插機後由眼鏡 APK 入手", "2026-10-19", path=self.path)
        self.assertTrue(rec["id"])
        items = C.open_items(self.path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["promise"], "插機後由眼鏡 APK 入手")
        self.assertEqual(items[0]["quoted"], "今晚做 REA")

    def test_empty_promise_rejected(self):
        with self.assertRaises(ValueError):
            C.add("x", "   ", path=self.path)

    def test_close_requires_evidence(self):
        rec = C.add("q", "do the thing", path=self.path)
        with self.assertRaises(ValueError):
            C.transition(rec["id"], "done", path=self.path)
        C.transition(rec["id"], "done", evidence="reports/verify-1/", path=self.path)
        self.assertEqual(C.open_items(self.path), [])
        folded = C.fold(C.read_events(self.path))
        self.assertEqual(folded[rec["id"]]["status"], "done")
        self.assertEqual(folded[rec["id"]]["evidence"], "reports/verify-1/")

    def test_drop_requires_owner_words(self):
        rec = C.add("q", "do the thing", path=self.path)
        with self.assertRaises(ValueError):
            C.transition(rec["id"], "dropped", path=self.path)
        out = C.transition(rec["id"], "dropped", words="唔使做住", path=self.path)
        self.assertEqual(out["status"], "dropped")
        self.assertEqual(out["dropped_words"], "唔使做住")
        self.assertEqual(C.open_items(self.path), [])

    def test_close_unknown_id(self):
        with self.assertRaises(KeyError):
            C.transition("nope-0000", "done", evidence="x", path=self.path)

    def test_append_only_keeps_history(self):
        rec = C.add("q", "thing", path=self.path)
        C.transition(rec["id"], "done", evidence="ev", path=self.path)
        events = C.read_events(self.path)
        self.assertEqual(len(events), 2)  # creation + closure, never rewritten
        self.assertEqual(events[0]["promise"], "thing")

    def test_torn_line_does_not_hide_the_rest(self):
        rec = C.add("q", "survivor", path=self.path)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write('{"id": "broken"')  # no closing brace, no newline
        items = C.open_items(self.path)
        self.assertEqual([i["id"] for i in items], [rec["id"]])

    def test_ordering_by_due_then_said(self):
        a = C.add("q", "no due", path=self.path)
        b = C.add("q", "later", (date.today() + timedelta(days=5)).isoformat(), path=self.path)
        c = C.add("q", "sooner", (date.today() + timedelta(days=1)).isoformat(), path=self.path)
        order = [i["id"] for i in C.open_items(self.path)]
        self.assertEqual(order, [c["id"], b["id"], a["id"]])

    def test_overdue(self):
        C.add("q", "late one", (date.today() - timedelta(days=1)).isoformat(), path=self.path)
        C.add("q", "later one", (date.today() + timedelta(days=1)).isoformat(), path=self.path)
        C.add("q", "no due", path=self.path)
        items = C.open_items(self.path)
        late = C.overdue(items)
        self.assertEqual(len(late), 1)
        self.assertIn("過期", C.render(items))

    def test_render_empty_is_empty_string(self):
        self.assertEqual(C.render([]), "")

    def test_render_caps_and_counts(self):
        for n in range(9):
            C.add("q", f"promise {n}", path=self.path)
        block = C.render(C.open_items(self.path), limit=3)
        self.assertIn("仲欠主人 9 件事", block)
        self.assertEqual(block.count("- ["), 3)
        self.assertIn("仲有 6 件未列", block)

    def test_cli_roundtrip(self):
        self.assertEqual(C.main(["--home", str(self.home), "add", "--quote", "q", "--promise", "cli task"]), 0)
        self.assertEqual(C.main(["--home", str(self.home), "open"]), 0)
        rid = C.open_items(self.path)[0]["id"]
        self.assertEqual(C.main(["--home", str(self.home), "close", rid, "--evidence", "ev"]), 0)
        self.assertEqual(C.open_items(self.path), [])

    def test_cli_errors_exit_2(self):
        self.assertEqual(C.main(["--home", str(self.home), "drop", "nope", "--words", "x"]), 2)


class PluginInjectionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "scripts").mkdir(parents=True)
        src = Path(__file__).resolve().parent.parent / "commitments.py"
        (self.home / "scripts" / "commitments.py").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        self._old_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(self.home)
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
        for mod in ("hermes_commitments_plugin",):
            sys.modules.pop(mod, None)
        import importlib

        self.plugin = importlib.import_module("hermes_commitments_plugin") if "hermes_commitments_plugin" in sys.modules else None
        if self.plugin is None:
            spec = importlib.util.spec_from_file_location(
                "hermes_commitments_plugin",
                Path(__file__).resolve().parent.parent / "plugin" / "__init__.py",
            )
            self.plugin = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.plugin)

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old_home
        self.tmp.cleanup()

    def test_injects_once_per_session_and_never_when_empty(self):
        self.assertIsNone(self.plugin.on_pre_llm_call(session_id="s-empty"))
        C.add("q", "owed thing", path=C.store_path(self.home))
        self.plugin._INJECTED.clear()
        first = self.plugin.on_pre_llm_call(session_id="s1")
        self.assertIn("owed thing", first)
        self.assertIsNone(self.plugin.on_pre_llm_call(session_id="s1"))  # once only

    def test_disabled_by_env(self):
        C.add("q", "owed thing", path=C.store_path(self.home))
        os.environ["HERMES_COMMITMENTS_ENABLED"] = "0"
        try:
            self.plugin._INJECTED.clear()
            self.assertIsNone(self.plugin.on_pre_llm_call(session_id="s2"))
        finally:
            os.environ.pop("HERMES_COMMITMENTS_ENABLED", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
