from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from agentquant.api import create_app
from agentquant.worker import run_once

CONTEST = "/api/v1/competitions/track-2"
ADMIN = "/api/v1/admin"
REPORTS = "/api/v1/reports"
BOARD = f"{CONTEST}/leaderboard"


def test_review_access_and_versioned_publication(tmp_path, sign_in) -> None:
    now = datetime(2026, 11, 26, 12, tzinfo=UTC)
    deadline = now + timedelta(minutes=1)
    app = create_app(tmp_path / "jobs.sqlite3", allow_demo=False, clock=lambda: now)
    with (
        TestClient(app) as admin, TestClient(app) as team, TestClient(app) as outsider,
        TestClient(app) as reviewer, TestClient(app) as other_reviewer,
    ):
        sign_in(admin, "admin", "organizer")
        sign_in(team, "participant")
        sign_in(outsider, "outsider")
        reviewer_id = sign_in(reviewer, "reviewer", "reviewer")["id"]
        sign_in(other_reviewer, "reviewer2", "reviewer")
        team.post("/api/v1/teams", json={"name": "现金队"}).raise_for_status()
        outsider.post("/api/v1/teams", json={"name": "其他队"}).raise_for_status()
        assert outsider.get(BOARD).status_code == 404
        assert team.post(REPORTS, json={"title": "报告", "body": "测试"}).status_code == 409
        admin.put(f"{ADMIN}/competitions/track-2", json={
            "validation_deadline": deadline.isoformat(), "official_ready_at": deadline.isoformat(),
            "daily_validation_limit": 10, "quant_weight_bps": 6000,
        }).raise_for_status()
        submission = team.post("/api/v1/submissions", json={
            "name": "空仓", "source": {"kind": "baseline", "baseline_id": "cash"},
        }).raise_for_status().json()
        team.put(f"{CONTEST}/final-selection", json={"submission_id": submission["id"], "revision": 0}).raise_for_status()

        now = deadline
        admin.post(f"{ADMIN}/competitions/track-2/freeze").raise_for_status()
        admin.post(f"{ADMIN}/official-runs").raise_for_status()
        assert admin.post(f"{ADMIN}/leaderboards").json()["code"] == "OFFICIAL_RUNS_INCOMPLETE"
        assert run_once(app.state.jobs)
        assert admin.post(f"{ADMIN}/leaderboards").json()["code"] == "REPORTS_INCOMPLETE"
        first = team.post(REPORTS, json={"title": "报告", "body": "第一版"}).raise_for_status().json()
        assert outsider.get(REPORTS).json() == []
        assert admin.post(f"{ADMIN}/leaderboards").json()["code"] == "REVIEWS_INCOMPLETE"

        def assign(report):
            return admin.post(f"{ADMIN}/review-assignments", json={
                "report_id": report["id"], "reviewer_id": reviewer_id,
            }).raise_for_status().json()

        assignment = assign(first)
        assert assign(first)["id"] == assignment["id"]
        assert other_reviewer.get("/api/v1/reviews/assignments").json() == []
        assert reviewer.get("/api/v1/reviews/assignments").json()[0]["report"]["id"] == first["id"]
        review_url = f"/api/v1/reviews/{assignment['id']}"
        draft = {"revision": 0, "status": "DRAFT", "comment": "待补充"}
        assert other_reviewer.put(review_url, json=draft).status_code == 404
        assert reviewer.put(review_url, json=draft).raise_for_status().json()["revision"] == 1
        assert reviewer.put(review_url, json=draft).status_code == 409
        assert admin.post(f"{ADMIN}/leaderboards").json()["code"] == "REVIEWS_INCOMPLETE"
        scores = {"research": 100, "feedback": 80, "effectiveness": 90, "innovation": 70, "reproducibility": 60}
        final = {"revision": 1, "status": "SUBMITTED", "scores": scores}
        assert reviewer.put(review_url, json=final).raise_for_status().json()["revision"] == 2
        assert reviewer.put(review_url, json=final).status_code == 409
        preview = admin.post(f"{ADMIN}/leaderboards").raise_for_status().json()
        assert admin.post(f"{ADMIN}/leaderboards").json()["id"] == preview["id"]
        assert preview["published_at"] is None
        assert outsider.get(BOARD).status_code == 404

        second = team.post(REPORTS, json={"title": "报告", "body": "第二版"}).raise_for_status().json()
        assert second["version"] == 2
        assignment = assign(second)
        reviewer.put(
            f"/api/v1/reviews/{assignment['id']}", json={**final, "revision": 0},
        ).raise_for_status()
        assert admin.post(f"{ADMIN}/leaderboards/{preview['id']}/publish").json()["code"] == "LEADERBOARD_STALE"
        preview = admin.post(f"{ADMIN}/leaderboards").raise_for_status().json()
        publish_url = f"{ADMIN}/leaderboards/{preview['id']}/publish"
        assert outsider.post(publish_url).status_code == 403
        board = admin.post(publish_url).raise_for_status().json()
        assert board["published_at"]
        assert admin.post(publish_url).json() == board
        assert outsider.get(BOARD).json() == board
        assert outsider.get(CONTEST).json()["phase"] == "published"
        assert team.post(REPORTS, json={"title": "新报告", "body": "已锁定"}).status_code == 409
        assert len(board["entries"]) == 1
        result = board["entries"][0]
        assert result["rank"] == 1
        assert Decimal(result["quant_score"]) == Decimal("50")
        assert Decimal(result["report_score"]) == Decimal("80")
        assert Decimal(result["total_score"]) == Decimal("62")
