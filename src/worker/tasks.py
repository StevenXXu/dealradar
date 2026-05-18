import sys
import json
import redis
from .celery_app import celery_app
from run import (
    run_harvest,
    run_reason,
    run_push,
    run_archive_and_raise,
    run_alerts,
    run_digest,
)


class LogToRedis:
    def __init__(self, task_id, redis_client):
        self.task_id = task_id
        self.redis = redis_client
        self.key = f"task_logs:{task_id}"

    def write(self, text):
        if text:
            # Publish to a channel so listeners get it instantly
            self.redis.publish(self.key, text)
            # Also store it in a list so new listeners get history
            self.redis.rpush(f"{self.key}:history", text)
            # Expire logs after 2 hours
            self.redis.expire(f"{self.key}:history", 7200)

    def flush(self):
        pass


@celery_app.task(bind=True)
def run_pipeline(self, force_restart=False):
    """Run the main DealRadar pipeline as a background task."""
    import os

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)

    logger = LogToRedis(self.request.id, redis_client)
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = logger
    sys.stderr = logger

    raw_path = "data/raw_companies.json"
    enriched_path = "data/enriched_companies.json"

    try:
        run_harvest(raw_path, force_restart=force_restart)
        run_reason(raw_path, enriched_path)
        run_push(enriched_path)
        raise_events = run_archive_and_raise(enriched_path)
        if raise_events:
            run_alerts(raise_events)
        run_digest(enriched_path)
        print("\n" + "=" * 60)
        print("DONE")
        print("=" * 60)

        # Store latest completed task ID so the UI can find it
        redis_client.set("latest_pipeline_task", self.request.id)

        return {"status": "success"}
    except Exception as e:
        import traceback

        print(f"\n[ERROR] Pipeline failed: {str(e)}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        # Signal completion
        redis_client.publish(logger.key, "event: done\n")
