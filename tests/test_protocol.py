from __future__ import annotations

import unittest

from nanoworker.protocol import AssignmentSnapshot, WorkerResult, extract_decision_data, result_to_json_dict


class ProtocolTests(unittest.TestCase):
    def test_result_serializes_assignment_snapshot(self) -> None:
        result = WorkerResult(
            status="done",
            summary="implemented",
            iterations=3,
            files_changed=("src/app.py",),
            role_fit="good",
            risk_level="medium",
            next_recommended_roles=("reviewer", "tester"),
            handoff="Ready for review.",
            evidence=("pytest passed",),
            assignment=AssignmentSnapshot(
                worker="write",
                base_role="coder",
                tool_policy="product-write",
                model="anthropic/claude-sonnet-4-6",
                assignment_id="frontend-a",
                model_profile="claude-sonnet",
                skills=("coder", "frontend-ui"),
                role_file="/tmp/frontend-role.md",
            ),
        )

        payload = result_to_json_dict(result)

        self.assertTrue(payload["success"])
        self.assertEqual(payload["assignment"]["worker"], "write")
        self.assertEqual(payload["assignment"]["assignment_id"], "frontend-a")
        self.assertEqual(payload["assignment"]["base_role"], "coder")
        self.assertEqual(payload["assignment"]["tool_policy"], "product-write")
        self.assertEqual(payload["assignment"]["model_profile"], "claude-sonnet")
        self.assertEqual(payload["assignment"]["skills"], ["coder", "frontend-ui"])
        self.assertEqual(payload["role_fit"], "good")
        self.assertEqual(payload["risk_level"], "medium")
        self.assertEqual(payload["next_recommended_roles"], ["reviewer", "tester"])
        self.assertEqual(payload["handoff"], "Ready for review.")
        self.assertEqual(payload["evidence"], ["pytest passed"])

    def test_extract_decision_data_from_markdown_sections(self) -> None:
        data = extract_decision_data(
            """
Status: DONE_WITH_CONCERNS

Role Fit: partial
Risk Level: medium

Next Recommended Roles:
- reviewer
- tester

Handoff:
- Review src/app.py for API compatibility.

Evidence:
- pytest tests/test_app.py passed
- build skipped: not requested
"""
        )

        self.assertEqual(data["role_fit"], "partial")
        self.assertEqual(data["risk_level"], "medium")
        self.assertEqual(data["next_recommended_roles"], ("reviewer", "tester"))
        self.assertEqual(data["handoff"], "Review src/app.py for API compatibility.")
        self.assertEqual(data["evidence"], ("pytest tests/test_app.py passed", "build skipped: not requested"))

    def test_extract_decision_data_from_json(self) -> None:
        data = extract_decision_data(
            """```json
{"status":"done","role_fit":"good","risk_level":"low","next_recommended_roles":["tester"],"handoff":"Ready.","evidence":["unit test passed"]}
```"""
        )

        self.assertEqual(data["role_fit"], "good")
        self.assertEqual(data["risk_level"], "low")
        self.assertEqual(data["next_recommended_roles"], ("tester",))
        self.assertEqual(data["handoff"], "Ready.")
        self.assertEqual(data["evidence"], ("unit test passed",))


if __name__ == "__main__":
    unittest.main()
