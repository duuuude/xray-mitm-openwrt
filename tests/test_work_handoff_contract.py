#!/usr/bin/env python3
"""Guard the explicit, fail-closed handoff contract in agent instructions."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / "docs/ai/WORKFLOW.md").read_text(encoding="utf-8")
PROMPTS = (ROOT / "docs/ai/PROMPTS.md").read_text(encoding="utf-8")


class WorkHandoffContractTests(unittest.TestCase):
    def test_handoff_request_and_delivery_use_an_exact_thread_id(self) -> None:
        for document in (WORKFLOW, PROMPTS):
            with self.subTest(document="workflow" if document is WORKFLOW else "prompts"):
                self.assertIn("Lead task thread ID", document)
                self.assertIn("send_message_to_thread", document)
                self.assertIn("exact", document.lower())
        self.assertIn('threadId: "<exact Lead task thread ID>"', WORKFLOW)
        self.assertIn('prompt: "<complete report>"', WORKFLOW)

    def test_completion_status_cannot_stand_in_for_a_report(self) -> None:
        self.assertIn("completed or idle", WORKFLOW)
        self.assertIn("UNPROVEN / NOT DELIVERED", WORKFLOW)
        self.assertIn("HANDOFF DELIVERY FAILED", WORKFLOW)
        self.assertIn("UNPROVEN / NOT DELIVERED", PROMPTS)
        self.assertIn("HANDOFF DELIVERY FAILED", PROMPTS)

    def test_reviewer_prompt_requires_direct_delivery_before_finalizing(self) -> None:
        reviewer = PROMPTS.split("## 3. Reviewer Agent", 1)[1].split("## 4.", 1)[0]
        self.assertIn("send_message_to_thread", reviewer)
        self.assertIn("exact `Lead task thread ID`", reviewer)
        self.assertIn("entire report", reviewer)
        self.assertIn("HANDOFF DELIVERY FAILED", reviewer)


if __name__ == "__main__":
    unittest.main()
