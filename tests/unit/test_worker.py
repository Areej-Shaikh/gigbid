"""Worker de-duplication rule (E1): a job is queued at most once per user, analysed jobs are skipped."""
from worker.main import WorkerSettings, plan_new_jobs


def test_skips_seen_and_analysed_jobs_and_caps_the_round():
    jobs = [{"job_id": "a"}, {"job_id": "b", "status": "awaiting_approval"}, {"job_id": "c"}, {"job_id": "a"},
            {"job_id": "d", "action": "skip"}, {"job_id": "e"}, {"job_id": "f"}]
    picked = [f.job_id for f in plan_new_jobs("demo", jobs, seen={"c"}, limit=2)]
    assert picked == ["a", "e"]


def test_schedule_and_retries_are_declared():
    assert WorkerSettings.max_tries == 3 and WorkerSettings.cron_jobs and WorkerSettings.functions
