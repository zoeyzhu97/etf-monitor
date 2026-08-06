# -*- coding: utf-8 -*-
"""自动发布工作流的回归测试。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DAILY_WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"
FALLBACK_WORKFLOW = (ROOT / ".github" / "workflows" /
                     "daily-runner-fallback.yml")


class TestDailyWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = DAILY_WORKFLOW.read_text(encoding="utf-8")

    def test_freshness_gate_precedes_all_derived_outputs(self):
        """不能先生成或提交半新半旧的数据，再检查日期。"""
        gate = self.workflow.index("- name: Check ETF data freshness")
        for step in (
                "- name: Event study",
                "- name: Daily multi-model assessment",
                "- name: Daily comment",
                "- name: Commit & push"):
            self.assertLess(gate, self.workflow.index(step), step)

    def test_publish_steps_require_complete_etf_snapshot(self):
        """衍生结果和提交都必须受完整性校验保护。"""
        required_condition = "if: steps.freshness.outcome == 'success'"
        for step in (
                "- name: Event study",
                "- name: Daily multi-model assessment",
                "- name: Daily comment",
                "- name: Commit & push"):
            start = self.workflow.index(step)
            following = self.workflow[start:start + 220]
            self.assertIn(required_condition, following, step)

    def test_cloudbase_deploy_is_chained_to_actual_publication(self):
        """机器人提交不会触发push工作流，国内镜像须在同一流水线部署。"""
        self.assertIn(
            "if: needs.update.outputs.published == 'true'",
            self.workflow,
        )
        self.assertIn("ref: main", self.workflow)
        self.assertIn(
            'tcb hosting deploy "$RUNNER_TEMP/etf-monitor-site"',
            self.workflow,
        )

    def test_has_redundant_attempts_around_official_release(self):
        """23点披露窗口前后须有冗余，降低GitHub定时排队造成的延迟。"""
        for utc_hour in range(12, 19):
            self.assertIn(
                f"cron: '17 {utc_hour} * * 1-5'",
                self.workflow,
            )

    def test_delayed_runs_are_queued_instead_of_replaced(self):
        self.assertIn("queue: max", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_reusable_workflow_accepts_alternate_runner(self):
        self.assertIn("workflow_call:", self.workflow)
        self.assertGreaterEqual(
            self.workflow.count("inputs.runner || 'ubuntu-latest'"), 3)

    def test_parallel_runner_publications_rebase_before_push(self):
        pull = self.workflow.index("git pull --rebase origin main")
        push = self.workflow.index("git push", pull)
        self.assertLess(pull, push)


class TestRunnerFallbackWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = FALLBACK_WORKFLOW.read_text(encoding="utf-8")

    def test_failed_primary_run_uses_macos_pool(self):
        self.assertIn("workflow_run:", self.workflow)
        self.assertIn("- daily-update", self.workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'failure'",
                      self.workflow)
        self.assertIn("uses: ./.github/workflows/daily.yml", self.workflow)
        self.assertIn("runner: macos-latest", self.workflow)

    def test_fallback_inherits_deployment_secrets(self):
        self.assertIn("secrets: inherit", self.workflow)


if __name__ == "__main__":
    unittest.main()
