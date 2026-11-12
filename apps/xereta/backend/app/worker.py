import time

from sqlmodel import Session, select

from app.config import Settings
from app.db import initialize, make_engine, worker_lock
from app.models import Artifact, Heartbeat, Run, now
from app.services import due_schedule, execute_run


def tick(engine, settings):
    with worker_lock(engine) as acquired:
        if not acquired:
            return
        with Session(engine) as s:
            # A process holding the global lock is the only worker. A running row
            # left behind belongs to an interrupted process; resume its checkpoints.
            job = s.exec(select(Run).where(Run.state.in_(["running", "queued"])).order_by(Run.created_at)).first()
            beat = s.get(Heartbeat, 1) or Heartbeat()
            beat.at = now()
            s.add(beat)
            s.commit()
            due_schedule(s, settings)
            if not job:
                job = s.exec(select(Run).where(Run.state == "queued").order_by(Run.created_at)).first()
            if job:
                job.state = "running"
                job.started_at = job.started_at or now()
                s.add(job)
                s.commit()
                job_id = job.id
            else:
                job_id = None
        if job_id:
            execute_run(engine, settings, job_id)
        elif settings.publish_enabled:
            from app.review import publish_review
            from app.vault import Vault
            with Session(engine) as s:
                outbox = s.get(Artifact, "review:outbox")
                if not s.get(Artifact, "review:layout-v2") or (outbox and outbox.value.get("state") == "pending"):
                    vault = Vault(settings)
                    try:
                        publish_review(s, settings, vault)
                    finally:
                        vault.close()

        if not job_id and settings.library_enabled:
            from app.references import tick as library_tick
            from app.vault import Vault
            with Session(engine) as s:
                vault=Vault(settings)
                try:library_tick(s,settings,vault)
                finally:vault.close()


def main():
    settings = Settings()
    engine = make_engine(settings.database_url)
    initialize(engine, settings)
    while True:
        try:
            tick(engine, settings)
        except Exception:
            print("xereta_worker_dependency_unavailable", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
