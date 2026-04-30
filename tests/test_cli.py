from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from typer.testing import CliRunner

    from nanoworker.cli import _can_retry_with_fallback, _model_attempts, app
    from nanoworker.config import Config, ModelProfile, resolve_model
    from nanoworker.protocol import WorkerResult
except ModuleNotFoundError:  # pragma: no cover - local bare Python may not have project deps installed.
    CliRunner = None
    app = None
    Config = None
    ModelProfile = None
    WorkerResult = None


class CliTests(unittest.TestCase):
    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_root_help_lists_diagnostic_commands(self) -> None:
        result = CliRunner().invoke(app, ["--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("list", result.output)
        self.assertIn("doctor", result.output)
        self.assertIn("smoke", result.output)
        self.assertIn("init", result.output)
        self.assertIn("migrate-config", result.output)
        self.assertIn("suggest", result.output)
        self.assertIn("journal", result.output)
        self.assertIn("feedback", result.output)
        self.assertIn("stats", result.output)
        self.assertIn("role", result.output)

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_unknown_first_token_routes_to_run_command(self) -> None:
        result = CliRunner().invoke(app, ["write", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Usage:", result.output)
        self.assertIn("nanoworker run", result.output)
        self.assertIn("--tool-policy", result.output)

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_init_writes_env_first_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "config.json"
            result = CliRunner().invoke(app, ["init", "--output", str(output)])

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(payload["providers"]["openai"]["api_key_env"], "LLM_API_KEY")
        self.assertEqual(payload["providers"]["openai"]["api_base_env"], "LLM_API_BASE")
        self.assertEqual(payload["models"]["gpt-5.4"]["model"], "openai/gpt-5.4")
        self.assertEqual(payload["workers"]["write"]["tool_policy"], "product-write")
        self.assertEqual(payload["workers"]["fix"]["role"], "fixer")
        self.assertEqual(payload["workers"]["review"]["role"], "reviewer")

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_migrate_config_defaults_to_stdout_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "config.json"
            source.write_text(
                json.dumps(
                    {
                        "providers": {"openai": {"api_key_env": "XIANYU_API_KEY"}},
                        "workers": {"coder-1": {"role": "coder", "model": "fast"}},
                    }
                ),
                encoding="utf-8",
            )
            result = CliRunner().invoke(app, ["migrate-config", "--input", str(source), "--json"])
            migrated = json.loads(result.output)["config"]
            original = json.loads(source.read_text(encoding="utf-8"))

        self.assertEqual(result.exit_code, 0)
        self.assertIn("coder-1", original["workers"])
        self.assertEqual(migrated["providers"]["openai"]["api_key_env"], "LLM_API_KEY")
        self.assertIn("write", migrated["workers"])

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_journal_command_reads_jsonl_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            path.write_text(
                '{"timestamp":"1","status":"done","assignment":{"worker":"write","model":"openai/test","assignment_id":"a"},"files_changed":[],"tests_run":[]}\n',
                encoding="utf-8",
            )

            result = CliRunner().invoke(app, ["journal", "--path", str(path), "--json"])
            payload = json.loads(result.output)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(payload["entries"][0]["assignment"]["worker"], "write")

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_feedback_command_records_leader_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            result = CliRunner().invoke(
                app,
                [
                    "feedback",
                    "frontend-role",
                    "--target-type",
                    "role-card",
                    "--assignment-id",
                    "frontend-a",
                    "--comment",
                    "Good fit for frontend UI polish.",
                    "--tag",
                    "frontend",
                    "--tag",
                    "ui",
                    "--accepted",
                    "--path",
                    str(path),
                    "--json",
                ],
            )
            payload = json.loads(result.output)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(payload["entry"]["event"], "leader_feedback")
        self.assertEqual(payload["entry"]["target_type"], "role_card")
        self.assertEqual(payload["entry"]["fit_tags"], ["frontend", "ui"])

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_feedback_list_filters_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            CliRunner().invoke(
                app,
                [
                    "feedback",
                    "frontend-role",
                    "--comment",
                    "Good fit for frontend UI polish.",
                    "--tag",
                    "frontend",
                    "--path",
                    str(path),
                ],
            )
            result = CliRunner().invoke(
                app,
                ["feedback", "list", "--target", "frontend-role", "--filter-tag", "frontend", "--path", str(path), "--json"],
            )
            payload = json.loads(result.output)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(payload["entries"][0]["target"], "frontend-role")

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_stats_command_aggregates_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            path.write_text(
                '{"timestamp":"1","status":"done","success":true,"assignment":{"worker":"write","base_role":"coder","model":"openai/test","skills":["frontend-ui"],"assignment_id":"a"},"role_fit":"good","risk_level":"low","next_recommended_roles":["tester"]}\n'
                '{"timestamp":"2","event":"leader_feedback","target":"frontend-ui","target_type":"skill","leader_comment":"Good fit.","fit_tags":["frontend"],"accepted":true}\n',
                encoding="utf-8",
            )
            result = CliRunner().invoke(app, ["stats", "--target", "frontend-ui", "--target-type", "skill", "--path", str(path), "--json"])
            payload = json.loads(result.output)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(payload["assignments"]["count"], 1)
        self.assertEqual(payload["feedback"]["accepted"], 1)

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_stats_command_filters_since_until(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            path.write_text(
                '{"timestamp":"2026-01-01T00:00:00+00:00","status":"done","success":true,'
                '"assignment":{"worker":"write","base_role":"coder","model":"openai/old","skills":["frontend-ui"]}}\n'
                '{"timestamp":"2026-01-03T00:00:00+00:00","status":"failed","success":false,'
                '"assignment":{"worker":"write","base_role":"coder","model":"openai/new","skills":["frontend-ui"]}}\n',
                encoding="utf-8",
            )
            result = CliRunner().invoke(
                app,
                [
                    "stats",
                    "--target",
                    "frontend-ui",
                    "--target-type",
                    "skill",
                    "--since",
                    "2026-01-02T00:00:00+00:00",
                    "--until",
                    "2026-01-04T00:00:00+00:00",
                    "--path",
                    str(path),
                    "--json",
                ],
            )
            payload = json.loads(result.output)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(payload["assignments"]["count"], 1)
        self.assertEqual(payload["assignments"]["models"], {"openai/new": 1})

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_role_install_defaults_is_hidden_from_regular_help(self) -> None:
        help_result = CliRunner().invoke(app, ["role", "--help"])

        self.assertEqual(help_result.exit_code, 0)
        self.assertNotIn("install-defaults", help_result.output)

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_role_create_outputs_temporary_role_card(self) -> None:
        result = CliRunner().invoke(
            app,
            [
                "role",
                "create",
                "Frontend Implementer",
                "Build responsive UI component",
                "--preferred-model",
                "claude-sonnet",
                "--skill",
                "frontend-ui",
            ],
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn("# Role Card: Frontend Implementer", result.output)
        self.assertIn("Preferred model: claude-sonnet", result.output)
        self.assertIn("--role-file", result.output)

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_role_skill_writes_persistent_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = CliRunner().invoke(
                app,
                [
                    "role",
                    "skill",
                    "Security Reviewer",
                    "--description",
                    "Reusable security review role.",
                    "--base-role",
                    "reviewer",
                    "--preferred-model",
                    "claude-sonnet",
                    "--tag",
                    "security",
                    "--tag",
                    "backend",
                    "--skills-dir",
                    tmp,
                    "--json",
                ],
            )
            payload = json.loads(result.output)
            skill_path = Path(payload["path"])

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(skill_path.exists())
            self.assertEqual(skill_path.parent.name, "security-reviewer")
            self.assertEqual(payload["base_role"], "reviewer")
            self.assertEqual(payload["tags"], ["security", "backend"])
            self.assertEqual(payload["preferred_models"], ["claude-sonnet"])
            self.assertIn("name: security-reviewer", skill_path.read_text(encoding="utf-8"))

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_role_list_show_path_and_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "reviewer" / "SKILL.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                "---\nname: reviewer\ndescription: Review code.\n---\n\n# Reviewer\n",
                encoding="utf-8",
            )

            register_result = CliRunner().invoke(
                app,
                ["role", "register", "reviewer", "--path", str(source), "--skills-dir", tmp, "--json"],
            )
            list_result = CliRunner().invoke(app, ["role", "list", "--skills-dir", tmp, "--json"])
            show_result = CliRunner().invoke(app, ["role", "show", "reviewer", "--skills-dir", tmp])
            path_result = CliRunner().invoke(app, ["role", "path", "reviewer", "--skills-dir", tmp])
            copy_result = CliRunner().invoke(
                app,
                ["role", "copy", "reviewer", "style-reviewer", "--skills-dir", tmp, "--json"],
            )
            copy_payload = json.loads(copy_result.output)
            copied = Path(copy_payload["path"])

            self.assertEqual(register_result.exit_code, 0)
            self.assertEqual(list_result.exit_code, 0)
            self.assertEqual(json.loads(list_result.output)["roles"][0]["name"], "reviewer")
            self.assertEqual(show_result.exit_code, 0)
            self.assertIn("# Reviewer", show_result.output)
            self.assertEqual(path_result.exit_code, 0)
            self.assertEqual(Path(path_result.output.strip()), source)
            self.assertEqual(copy_result.exit_code, 0)
            self.assertTrue(copied.exists())
            self.assertIn("name: style-reviewer", copied.read_text(encoding="utf-8"))

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_role_import_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "external" / "SKILL.md"
            store = Path(tmp) / "store"
            source.parent.mkdir(parents=True)
            source.write_text(
                "---\nname: DB Reviewer\ndescription: Review db changes.\n---\n\n# DB Reviewer\n",
                encoding="utf-8",
            )
            import_result = CliRunner().invoke(
                app,
                ["role", "import", str(source), "--id", "db-reviewer", "--skills-dir", str(store), "--json"],
            )
            remove_result = CliRunner().invoke(
                app,
                ["role", "remove", "db-reviewer", "--skills-dir", str(store), "--json"],
            )

        self.assertEqual(import_result.exit_code, 0)
        self.assertEqual(json.loads(import_result.output)["name"], "db-reviewer")
        self.assertEqual(remove_result.exit_code, 0)
        self.assertEqual(json.loads(remove_result.output)["name"], "db-reviewer")

    @unittest.skipIf(CliRunner is None or app is None, "typer is not installed")
    def test_fallback_helpers_only_retry_llm_failure_without_side_effects(self) -> None:
        config = Config(
            models={
                "primary": ModelProfile(model="openai/primary", fallbacks=("secondary",)),
                "secondary": ModelProfile(model="anthropic/secondary"),
            }
        )
        attempts = _model_attempts(config, resolve_model(config, "primary"), use_fallbacks=True)

        self.assertEqual([attempt.model for attempt in attempts], ["openai/primary", "anthropic/secondary"])
        self.assertTrue(_can_retry_with_fallback(WorkerResult(status="failed", summary="LLM call failed: timeout", iterations=1)))
        self.assertFalse(
            _can_retry_with_fallback(
                WorkerResult(
                    status="failed",
                    summary="LLM call failed: timeout",
                    iterations=2,
                    files_changed=("src/app.py",),
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
