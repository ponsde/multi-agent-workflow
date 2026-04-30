from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nanoworker.journal import (
    append_feedback_entry,
    append_journal_entry,
    build_journal_stats,
    read_feedback_entries,
    read_journal_entries,
)
from nanoworker.protocol import AssignmentSnapshot, WorkerResult


class JournalTests(unittest.TestCase):
    def test_append_journal_entry_writes_assignment_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            append_journal_entry(
                WorkerResult(
                    status="done",
                    summary="ok",
                    iterations=2,
                    files_changed=("tests/test_app.py",),
                    tests_run=("pytest",),
                    role_fit="good",
                    risk_level="low",
                    next_recommended_roles=("reviewer",),
                    handoff="Ready for review.",
                    evidence=("pytest passed",),
                    assignment=AssignmentSnapshot(
                        worker="verify",
                        base_role="tester",
                        tool_policy="test-write-only",
                        model="openai/test",
                        assignment_id="verify-a",
                    ),
                ),
                path,
            )

            entry = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(entry["success"])
        self.assertEqual(entry["assignment"]["worker"], "verify")
        self.assertEqual(entry["assignment"]["tool_policy"], "test-write-only")
        self.assertEqual(entry["files_changed"], ["tests/test_app.py"])
        self.assertEqual(entry["role_fit"], "good")
        self.assertEqual(entry["risk_level"], "low")
        self.assertEqual(entry["next_recommended_roles"], ["reviewer"])
        self.assertEqual(entry["handoff"], "Ready for review.")
        self.assertEqual(entry["evidence"], ["pytest passed"])

    def test_read_journal_entries_filters_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            path.write_text(
                '{"timestamp":"1","status":"done","assignment":{"worker":"write","assignment_id":"a"}}\n'
                '{"timestamp":"2","status":"failed","assignment":{"worker":"debug","assignment_id":"b"}}\n',
                encoding="utf-8",
            )

            entries = read_journal_entries(path, limit=1, worker="debug")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["timestamp"], "2")

    def test_append_feedback_entry_records_leader_role_card_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            entry = append_feedback_entry(
                path,
                target="frontend-ui-card",
                target_type="role-card",
                leader_comment="Good fit for frontend component polish.",
                assignment_id="frontend-a",
                fit_tags=("frontend", "ui", " "),
                role_fit="good",
                model_fit="partial",
                accepted=True,
                reuse_when=("component work",),
                avoid_when=("backend contract design",),
            )
            entries = read_journal_entries(path, assignment_id="frontend-a")
            feedback_entries = read_feedback_entries(path)

        self.assertEqual(entry["event"], "leader_feedback")
        self.assertEqual(entry["target_type"], "role_card")
        self.assertEqual(entry["fit_tags"], ["frontend", "ui"])
        self.assertEqual(entries[0]["leader_comment"], "Good fit for frontend component polish.")
        self.assertEqual(feedback_entries[0]["target"], "frontend-ui-card")

    def test_read_feedback_entries_filters_by_target_type_tag_and_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            append_feedback_entry(
                path,
                target="frontend-ui-card",
                target_type="role-card",
                leader_comment="Good fit.",
                assignment_id="frontend-a",
                fit_tags=("frontend",),
            )
            append_feedback_entry(
                path,
                target="db-card",
                target_type="role-card",
                leader_comment="DB fit.",
                assignment_id="backend-a",
                fit_tags=("database",),
            )

            entries = read_feedback_entries(path, target="frontend-ui-card", target_type="role_card", tag="frontend")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["assignment_id"], "frontend-a")

    def test_build_journal_stats_aggregates_assignments_and_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            append_journal_entry(
                WorkerResult(
                    status="done",
                    summary="ok",
                    iterations=1,
                    role_fit="good",
                    risk_level="low",
                    next_recommended_roles=("tester",),
                    assignment=AssignmentSnapshot(
                        worker="write",
                        base_role="coder",
                        tool_policy="product-write",
                        model="openai/test",
                        assignment_id="a",
                        skills=("frontend-ui",),
                    ),
                ),
                path,
            )
            append_feedback_entry(
                path,
                target="frontend-ui",
                target_type="skill",
                leader_comment="Useful for UI work.",
                fit_tags=("frontend",),
                accepted=True,
            )

            stats = build_journal_stats(path, target="frontend-ui", target_type="skill")

        self.assertEqual(stats["assignments"]["count"], 1)
        self.assertEqual(stats["assignments"]["role_fit"], {"good": 1})
        self.assertEqual(stats["assignments"]["next_recommended_roles"], {"tester": 1})
        self.assertEqual(stats["feedback"]["count"], 1)
        self.assertEqual(stats["feedback"]["accepted"], 1)

    def test_build_journal_stats_filters_by_time_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            path.write_text(
                '{"timestamp":"2026-01-01T00:00:00+00:00","status":"done","success":true,'
                '"assignment":{"worker":"write","base_role":"coder","model":"openai/old","skills":["frontend-ui"]}}\n'
                '{"timestamp":"2026-01-03T00:00:00+00:00","status":"failed","success":false,'
                '"assignment":{"worker":"write","base_role":"coder","model":"openai/new","skills":["frontend-ui"]}}\n'
                '{"timestamp":"2026-01-03T01:00:00+00:00","event":"leader_feedback","target":"frontend-ui",'
                '"target_type":"skill","leader_comment":"Recent note.","fit_tags":["frontend"],"accepted":true}\n',
                encoding="utf-8",
            )

            stats = build_journal_stats(
                path,
                target="frontend-ui",
                target_type="skill",
                since="2026-01-02T00:00:00+00:00",
                until="2026-01-04T00:00:00+00:00",
            )

        self.assertEqual(stats["assignments"]["count"], 1)
        self.assertEqual(stats["assignments"]["failed"], 1)
        self.assertEqual(stats["assignments"]["models"], {"openai/new": 1})
        self.assertEqual(stats["feedback"]["count"], 1)
        self.assertEqual(stats["filters"]["since"], "2026-01-02T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
