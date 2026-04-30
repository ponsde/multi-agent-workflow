from __future__ import annotations

import json
import unittest
import tempfile
from pathlib import Path

from nanoworker.roles import (
    RoleSpec,
    build_role_card,
    build_skill_doc,
    ensure_role_store,
    import_role_file,
    list_registered_roles,
    remove_registered_role,
    role_store_checks,
    resolve_registered_role_path,
    resolve_role_spec,
    slugify_role_name,
    upsert_role_path,
)


class RoleScaffoldTests(unittest.TestCase):
    def test_role_card_infers_frontend_defaults(self) -> None:
        spec = RoleSpec(name="Frontend Implementer", task="Build a responsive UI component")
        resolved = resolve_role_spec(spec)
        card = build_role_card(spec)

        self.assertEqual(resolved.task_shape, "frontend")
        self.assertEqual(resolved.base_role, "coder")
        self.assertIn("Preferred model: frontend-strong model if available", card)
        self.assertIn("responsive", card)

    def test_role_card_distinguishes_reviewer_and_fixer(self) -> None:
        reviewer = resolve_role_spec(RoleSpec(name="Code Reviewer", task="review this change"))
        fixer = resolve_role_spec(RoleSpec(name="Bug Fixer", task="apply findings from reviewer"))

        self.assertEqual(reviewer.base_role, "reviewer")
        self.assertEqual(fixer.base_role, "fixer")

    def test_skill_doc_uses_slug_and_persistent_shape(self) -> None:
        doc = build_skill_doc(
            RoleSpec(name="Security Reviewer", task="Review auth and secret handling"),
            skill_name="security-reviewer",
            description="Reusable security review role.",
        )

        self.assertIn("name: security-reviewer", doc)
        self.assertIn("description: Reusable security review role.", doc)
        self.assertIn("## Workflow", doc)
        self.assertEqual(slugify_role_name("Frontend UI!"), "frontend-ui")

    def test_managed_role_store_installs_and_indexes_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bundled"
            store = root / "store"
            index = store / "index.json"
            skill = source / "reviewer" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: reviewer\ndescription: Review code.\n---\n\n# Reviewer\n", encoding="utf-8")

            installed = ensure_role_store(source, store, index)
            path = resolve_registered_role_path(store, index, "reviewer")
            path.write_text(path.read_text(encoding="utf-8") + "\nLocal note.\n", encoding="utf-8")
            roles = list_registered_roles(store, index)

            self.assertEqual(installed[0].name, "reviewer")
            self.assertEqual(path, store / "reviewer" / "SKILL.md")
            self.assertTrue(roles[0].modified)

    def test_explicit_import_register_and_remove_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external" / "SKILL.md"
            store = root / "store"
            index = store / "index.json"
            source.parent.mkdir(parents=True)
            source.write_text("---\nname: DB Reviewer\ndescription: Review db changes.\n---\n\n# DB\n", encoding="utf-8")

            imported = import_role_file(source, store, index, role_id="db-reviewer")
            roles = list_registered_roles(store, index)
            path = resolve_registered_role_path(store, index, "db-reviewer")
            removed = remove_registered_role(store, index, "db-reviewer")

        self.assertEqual(imported.name, "db-reviewer")
        self.assertEqual(roles[0].name, "db-reviewer")
        self.assertEqual(path, store / "db-reviewer" / "SKILL.md")
        self.assertEqual(removed.name, "db-reviewer")

    def test_role_registry_records_routing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external" / "SKILL.md"
            store = root / "store"
            index = store / "index.json"
            source.parent.mkdir(parents=True)
            source.write_text(
                "---\n"
                "name: Frontend UI\n"
                "description: Frontend implementation role.\n"
                "tags: frontend, ui, responsive\n"
                "base_role: coder\n"
                "preferred_models: claude-sonnet, gpt-frontend\n"
                "---\n\n"
                "# Frontend UI\n",
                encoding="utf-8",
            )

            imported = import_role_file(source, store, index, role_id="frontend-ui")
            roles = list_registered_roles(store, index)
            record = json.loads(index.read_text(encoding="utf-8"))["roles"]["frontend-ui"]

        self.assertEqual(imported.tags, ("frontend", "ui", "responsive"))
        self.assertEqual(roles[0].base_role, "coder")
        self.assertEqual(roles[0].preferred_models, ("claude-sonnet", "gpt-frontend"))
        self.assertEqual(record["tags"], ["frontend", "ui", "responsive"])
        self.assertEqual(record["base_role"], "coder")
        self.assertEqual(record["preferred_models"], ["claude-sonnet", "gpt-frontend"])

    def test_register_rejects_paths_outside_managed_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external" / "SKILL.md"
            store = root / "store"
            index = store / "index.json"
            source.parent.mkdir(parents=True)
            source.write_text("---\nname: reviewer\n---\n\n# Reviewer\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                upsert_role_path(store, index, source, role_id="reviewer")

    def test_role_store_doctor_reports_unregistered_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store"
            index = store / "index.json"
            skill = store / "reviewer" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: reviewer\n---\n\n# Reviewer\n", encoding="utf-8")

            checks = role_store_checks(store, index)

        self.assertTrue(any(check.name == "unregistered:reviewer" and not check.ok for check in checks))

    def test_remove_registered_role_handles_stale_index_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external" / "SKILL.md"
            store = root / "store"
            index = store / "index.json"
            source.parent.mkdir(parents=True)
            source.write_text("---\nname: reviewer\n---\n\n# Reviewer\n", encoding="utf-8")
            imported = import_role_file(source, store, index, role_id="reviewer")
            imported.path.unlink()

            removed = remove_registered_role(store, index, "reviewer")
            roles = list_registered_roles(store, index)

        self.assertEqual(removed.name, "reviewer")
        self.assertEqual(roles, ())


if __name__ == "__main__":
    unittest.main()
