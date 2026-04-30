from __future__ import annotations

import unittest
from pathlib import Path

from nanoworker.config import Config, ModelProfile, WorkerDef
from nanoworker.planner import (
    candidate_feedback,
    candidate_feedback_summary,
    infer_task_shape,
    role_candidate_to_dict,
    suggest_assignment,
    suggest_role_candidates,
    suggestion_to_dict,
)
from nanoworker.roles import SkillInfo


class PlannerTests(unittest.TestCase):
    def test_infer_task_shape_from_keywords(self) -> None:
        self.assertEqual(infer_task_shape("fix traceback in auth flow"), "debug")
        self.assertEqual(infer_task_shape("apply findings from reviewer"), "fix")
        self.assertEqual(infer_task_shape("implement responsive UI component"), "frontend")
        self.assertEqual(infer_task_shape("run tests and verify build"), "verify")

    def test_suggest_assignment_prefers_frontend_model_for_ui_task(self) -> None:
        config = Config(
            models={
                "gpt-5.4": ModelProfile(
                    model="openai/gpt-5.4",
                    strengths=("backend", "reasoning", "tests"),
                    preferred_roles=("coder", "debug", "tester"),
                ),
                "claude-sonnet": ModelProfile(
                    model="anthropic/claude-sonnet-4-6",
                    strengths=("frontend", "ui", "review"),
                    preferred_roles=("coder", "reviewer"),
                ),
            },
            workers={
                "write": WorkerDef(role="coder", model="gpt-5.4", skills=("coder",)),
                "fix": WorkerDef(role="fixer", model="gpt-5.4", skills=("fixer",)),
                "review": WorkerDef(role="reviewer", model="claude-sonnet", skills=("reviewer",)),
                "verify": WorkerDef(role="tester", model="gpt-5.4", skills=("tester",)),
            },
        )

        suggestion = suggest_assignment(config, "Build a responsive UI component", workspace="/repo")
        payload = suggestion_to_dict(suggestion)

        self.assertEqual(payload["worker"], "write")
        self.assertEqual(payload["model"], "claude-sonnet")
        self.assertEqual(payload["tool_policy"], "product-write")
        self.assertTrue(payload["role_card_recommended"])
        self.assertIn("--model claude-sonnet", payload["command"])

        candidates = [
            role_candidate_to_dict(candidate)
            for candidate in suggest_role_candidates(config, "Build a responsive UI component", workspace="/repo")
        ]
        self.assertEqual(candidates[0]["name"], "Frontend Implementer")
        self.assertEqual(candidates[1]["base_role"], "reviewer")
        self.assertEqual(candidates[1]["acceptance_focus"], ["Findings are concrete and severity-ranked."])
        self.assertEqual(candidates[2]["base_role"], "tester")

    def test_candidate_feedback_matches_tags_and_exact_targets(self) -> None:
        config = Config(
            models={
                "claude-sonnet": ModelProfile(
                    model="anthropic/claude-sonnet-4-6",
                    strengths=("frontend", "ui"),
                    preferred_roles=("coder",),
                ),
            },
            workers={
                "write": WorkerDef(role="coder", model="claude-sonnet", skills=("coder", "frontend-ui")),
                "review": WorkerDef(role="reviewer", model="claude-sonnet", skills=("reviewer",)),
                "verify": WorkerDef(role="tester", model="claude-sonnet", skills=("tester",)),
            },
        )
        candidate = suggest_role_candidates(config, "实现前端组件", workspace="/repo")[0]
        feedback_entries = (
            {
                "timestamp": "2",
                "event": "leader_feedback",
                "target": "frontend-ui-card",
                "target_type": "role_card",
                "leader_comment": "Good fit for frontend component polish.",
                "fit_tags": ["frontend", "ui"],
                "role_fit": "good",
                "model_fit": "good",
                "accepted": True,
            },
            {
                "timestamp": "1",
                "event": "leader_feedback",
                "target": "frontend-ui",
                "target_type": "skill",
                "leader_comment": "Useful frontend reusable method.",
                "fit_tags": ["frontend"],
            },
        )

        notes = candidate_feedback(candidate, task="实现前端组件", feedback_entries=feedback_entries)
        payload = role_candidate_to_dict(candidate, task="实现前端组件", feedback_entries=feedback_entries)

        self.assertEqual(notes[0]["leader_comment"], "Good fit for frontend component polish.")
        self.assertEqual(payload["feedback"][1]["target"], "frontend-ui")

        summary = candidate_feedback_summary(candidate, task="实现前端组件", feedback_entries=feedback_entries)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["accepted"], 1)
        self.assertEqual(summary["role_fit"], {"good": 1})
        self.assertEqual(summary["top_tags"][0], {"tag": "frontend", "count": 2})
        self.assertEqual(payload["feedback_summary"]["recent_comments"][0], "Good fit for frontend component polish.")

    def test_suggest_candidates_include_matching_registered_role_metadata(self) -> None:
        config = Config(
            models={
                "gpt-backend": ModelProfile(
                    model="openai/gpt-backend",
                    strengths=("backend", "database", "reasoning"),
                    preferred_roles=("coder",),
                ),
            },
            workers={
                "write": WorkerDef(role="coder", model="gpt-backend", skills=("coder",)),
                "review": WorkerDef(role="reviewer", model="gpt-backend", skills=("reviewer",)),
            },
        )
        role_infos = (
            SkillInfo(
                name="database-migration",
                path=Path("/tmp/database-migration/SKILL.md"),
                description="Database migration role.",
                tags=("backend", "database", "migration"),
                base_role="coder",
                preferred_models=("gpt-backend",),
            ),
        )

        candidates = suggest_role_candidates(
            config,
            "Implement backend database migration",
            workspace="/repo",
            role_infos=role_infos,
        )
        payloads = [role_candidate_to_dict(candidate) for candidate in candidates]
        registered = next(payload for payload in payloads if payload.get("source") == "registered_role")

        self.assertEqual(registered["role_id"], "database-migration")
        self.assertEqual(registered["tags"], ["backend", "database", "migration"])
        self.assertEqual(registered["preferred_models"], ["gpt-backend"])
        self.assertIn("--skill database-migration", registered["command"])


if __name__ == "__main__":
    unittest.main()
