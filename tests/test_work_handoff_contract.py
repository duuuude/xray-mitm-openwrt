#!/usr/bin/env python3
"""Guard the explicit, fail-closed handoff contract in agent instructions."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
WORKFLOW = (ROOT / "docs/ai/WORKFLOW.md").read_text(encoding="utf-8")
PROMPTS = (ROOT / "docs/ai/PROMPTS.md").read_text(encoding="utf-8")
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")


def wait_threads_status(snapshot: dict, task_id: str) -> str | None:
    polls = snapshot.get("polls")
    if not isinstance(polls, list):
        return None
    matches = [
        poll for poll in polls
        if isinstance(poll, dict)
        and isinstance(poll.get("thread"), dict)
        and poll["thread"].get("id") == task_id
    ]
    if len(matches) != 1:
        return None
    latest_turn = matches[0].get("latestTurn")
    if not isinstance(latest_turn, dict):
        return None
    status = latest_turn.get("status")
    return status if isinstance(status, str) and status else None


def read_thread_status(snapshot: dict, task_id: str) -> str | None:
    thread = snapshot.get("thread")
    page = snapshot.get("page")
    turns = snapshot.get("turns")
    if not isinstance(thread, dict) or thread.get("id") != task_id:
        return None
    if not isinstance(page, dict) or page.get("order") != "newest_first":
        return None
    if not isinstance(turns, list) or not turns or not isinstance(turns[0], dict):
        return None
    status = turns[0].get("status")
    return status if isinstance(status, str) and status else None


class WorkHandoffContractTests(unittest.TestCase):
    def test_handoff_request_and_delivery_use_an_exact_thread_id(self) -> None:
        for document in (WORKFLOW, PROMPTS):
            with self.subTest(document="workflow" if document is WORKFLOW else "prompts"):
                self.assertIn("Lead task thread ID", document)
                self.assertIn("send_message_to_thread", document)
                self.assertIn("exact", document.lower())
        self.assertIn('--destination-task-id "<Lead task thread ID>"', WORKFLOW)
        self.assertIn('threadId: "<exact Lead task thread ID>"', WORKFLOW)
        self.assertIn('prompt: "<artifact receipt>"', WORKFLOW)

    def test_completion_status_cannot_stand_in_for_a_report(self) -> None:
        self.assertIn("completed or idle", WORKFLOW)
        self.assertIn("UNPROVEN / NOT DELIVERED", WORKFLOW)
        self.assertIn("HANDOFF DELIVERY FAILED", WORKFLOW)
        self.assertIn("UNPROVEN / NOT DELIVERED", PROMPTS)
        self.assertIn("HANDOFF DELIVERY FAILED", PROMPTS)

    def test_status_claims_require_a_fresh_task_snapshot(self) -> None:
        for name, document in (("AGENTS.md", AGENTS), ("WORKFLOW.md", WORKFLOW), ("PROMPTS.md", PROMPTS)):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("wait_threads", normalized)
                self.assertIn("timeoutMs: 0", normalized)
                self.assertIn("polls[]", normalized)
                self.assertIn("thread.id", normalized)
                self.assertIn("latestTurn.status", normalized)
                self.assertIn("page.order", normalized)
                self.assertIn("newest_first", normalized)
                self.assertIn("turns[0].status", normalized)
                self.assertIn("inProgress", normalized)
                self.assertIn("latest completed turn", normalized)
                self.assertIn("heartbeat", normalized)
                self.assertIn("UNPROVEN / NOT DELIVERED", normalized)

    def test_status_extractors_match_each_tool_response_shape(self) -> None:
        task_id = "task-123"
        wait_snapshot = {
            "polls": [{"thread": {"id": task_id}, "latestTurn": {"status": "inProgress"}}]
        }
        read_snapshot = {
            "thread": {"id": task_id},
            "page": {"order": "newest_first"},
            "turns": [{"status": "completed"}, {"status": "inProgress"}],
        }
        self.assertEqual(wait_threads_status(wait_snapshot, task_id), "inProgress")
        self.assertEqual(read_thread_status(read_snapshot, task_id), "completed")

    def test_missing_or_ambiguous_status_shapes_fail_closed(self) -> None:
        task_id = "task-123"
        ambiguous_wait = {
            "polls": [
                {"thread": {"id": task_id}, "latestTurn": {"status": "inProgress"}},
                {"thread": {"id": task_id}, "latestTurn": {"status": "completed"}},
            ]
        }
        self.assertIsNone(wait_threads_status(ambiguous_wait, task_id))
        self.assertIsNone(wait_threads_status({"polls": []}, task_id))
        self.assertIsNone(wait_threads_status({"polls": [{"thread": {"id": task_id}}]}, task_id))

        missing_turn = {
            "thread": {"id": task_id},
            "page": {"order": "newest_first"},
            "turns": [],
        }
        wrong_order = {
            "thread": {"id": task_id},
            "page": {"order": "oldest_first"},
            "turns": [{"status": "inProgress"}],
        }
        wrong_thread = {
            "thread": {"id": "other-task"},
            "page": {"order": "newest_first"},
            "turns": [{"status": "inProgress"}],
        }
        self.assertIsNone(read_thread_status(missing_turn, task_id))
        self.assertIsNone(read_thread_status(wrong_order, task_id))
        self.assertIsNone(read_thread_status(wrong_thread, task_id))

    def test_reviewer_prompt_requires_direct_delivery_before_finalizing(self) -> None:
        reviewer = PROMPTS.split("## 3. Reviewer Agent", 1)[1].split("## 4.", 1)[0]
        self.assertIn("scripts/work-report-handoff.py", reviewer)
        self.assertIn("`Handoff repository root`", reviewer)
        self.assertIn("`Source task thread ID`", reviewer)
        self.assertIn("`Lead task thread ID`", reviewer)
        self.assertIn("`Report ID`", reviewer)
        self.assertIn("artifact receipt plus the full report", reviewer)
        self.assertIn("HANDOFF DELIVERY FAILED", reviewer)

    def test_review_gate_waits_for_terminal_turn_and_reconciles_context(self) -> None:
        self.assertIn("artifact receipt arriving while the source task is still `inProgress` is", AGENTS)
        self.assertIn("Wait for that exact turn to", WORKFLOW)
        self.assertIn("Assignment verified: <PR number and full exact candidate SHA>", PROMPTS)
        self.assertIn("Context conflict: NONE / <details; BLOCK if unresolved>", PROMPTS)
        for document in (AGENTS, WORKFLOW, PROMPTS):
            self.assertIn("unique report ID", document)
            self.assertIn("final", document)
        self.assertIn("read-final", AGENTS)
        self.assertIn("read-final", WORKFLOW)
        self.assertIn("A running CI timer does not replace", " ".join(WORKFLOW.split()))

    def test_generic_prompt_carries_every_handoff_identity(self) -> None:
        generic = PROMPTS.split("## 11. Generic Prompt Template", 1)[1]
        self.assertIn("Handoff repository root:", generic)
        self.assertIn("Source task thread ID:", generic)
        self.assertIn("Lead task thread ID:", generic)
        self.assertIn("Report ID:", generic)
        self.assertIn("scripts/work-report-handoff.py", generic)

    def test_recovery_checks_the_artifact_not_a_native_receipt(self) -> None:
        normalized_workflow = " ".join(WORKFLOW.split())
        normalized_prompts = " ".join(PROMPTS.split())
        self.assertNotIn("If no artifact receipt exists", normalized_workflow)
        self.assertNotIn(
            "completed without an artifact receipt",
            normalized_workflow,
        )
        self.assertIn("verification confirms the artifact is absent", normalized_workflow)
        self.assertIn("verify and read the exact durable artifact", normalized_prompts)
        self.assertNotIn(
            "inspect the latest completed turn and the Lead task for its full report",
            normalized_prompts,
        )

    def test_durable_artifact_is_primary_and_git_ignored(self) -> None:
        for name, document in (("AGENTS.md", AGENTS), ("WORKFLOW.md", WORKFLOW), ("PROMPTS.md", PROMPTS)):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("scripts/work-report-handoff.py", normalized)
                self.assertIn("artifact", normalized.lower())
                self.assertIn("before", normalized.lower())
                self.assertIn("native", normalized.lower())
                self.assertIn("Never ask the owner", normalized)
        self.assertIn("/.codex/handoffs/", GITIGNORE)

    def test_metadata_only_snapshot_does_not_prove_report_absence(self) -> None:
        for name, document in (("AGENTS.md", AGENTS), ("WORKFLOW.md", WORKFLOW), ("PROMPTS.md", PROMPTS)):
            normalized = " ".join(document.split())
            with self.subTest(document=name):
                self.assertIn("latestAssistantMessage: null", normalized)
                self.assertIn("items: []", normalized)
                self.assertIn("do not prove", normalized)
                self.assertIn("UNPROVEN / REPORT CONTENT NOT EXPOSED", normalized)
                self.assertIn("Only use `UNPROVEN / NOT DELIVERED`", normalized)
                self.assertIn("Never ask the owner", normalized)


    def test_transport_probe_cannot_self_target_or_bypass_a_rejection(self) -> None:
        for name, document in (("AGENTS.md", AGENTS), ("WORKFLOW.md", WORKFLOW), ("PROMPTS.md", PROMPTS)):
            normalized = " ".join(document.split()).lower()
            with self.subTest(document=name):
                self.assertIn("source task id", normalized)
                self.assertIn("destination task id", normalized)
                self.assertIn("they must differ", normalized)
                self.assertIn("self-send", normalized)
                self.assertIn("actual conversation content", normalized)
                self.assertIn("wait_threads` cannot wait on the calling task", normalized)
                self.assertIn("do not retry by using shell, cli, app-server", normalized)

    def test_policy_rejection_is_terminal_and_recovery_is_strictly_scoped(self) -> None:
        for name, document in (("AGENTS.md", AGENTS), ("WORKFLOW.md", WORKFLOW), ("PROMPTS.md", PROMPTS)):
            normalized = " ".join(document.split()).lower()
            with self.subTest(document=name):
                self.assertIn("terminal for the rejected operation", normalized)
                self.assertIn("before", normalized)
                self.assertIn("native", normalized)
                self.assertIn("do not retry", normalized)
                self.assertIn("another account/session", normalized)
                self.assertIn("handoff delivery failed", normalized)
                self.assertIn("no prior artifact write/verification failure", normalized)
                self.assertNotIn(
                    "verify the received content in the destination",
                    normalized,
                )
                self.assertNotIn(
                    "use the persistent reviewer work to regenerate/deliver the report",
                    normalized,
                )
                self.assertNotIn("if the retry also fails", normalized)

if __name__ == "__main__":
    unittest.main()
