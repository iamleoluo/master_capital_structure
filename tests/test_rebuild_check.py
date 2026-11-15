"""CI 重算 daily 與 weekly，而且工作流程不部署。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_reads_the_constant_and_does_not_deploy():
    text = (ROOT / ".github" / "workflows" / "rebuild-data.yml").read_text(encoding="utf-8")
    assert "web/rebuild_check.py" in text
    assert "wrangler" not in text
    assert "cloudflare" not in text.lower()
    target = (ROOT / "deploy_target.py").read_text(encoding="utf-8")
    assert "DEPLOY_PROJECT" in target
