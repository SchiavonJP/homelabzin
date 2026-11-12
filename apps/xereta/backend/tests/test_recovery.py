"""Hard process deaths, persistent remote state, and a PostgreSQL lock check."""
from datetime import UTC, datetime, timedelta
import os
import time

import pytest
from sqlmodel import Session, select

from app.db import make_engine
from app.models import Artifact, Finding, Question, ReviewPage, Run, Source, Version
from app.services import remaining_run_seconds
from app.vault import DomainError
from recovery_support import Backend, FIXTURE, WorkerProcess, guarded_database, run_state, setup_case


@pytest.fixture
def case(tmp_path):
    return setup_case(tmp_path, os.environ.get('XERETA_RECOVERY_DATABASE_URL'))


def assert_complete(settings, run_id):
    result = run_state(settings, run_id)
    assert result['state'] == 'completed' and result['result']['publication'] == 'published'
    engine = make_engine(settings.database_url)
    try:
        with Session(engine) as s:
            assert len(s.exec(select(Run)).all()) == 1
            assert len(s.exec(select(Source)).all()) == len(s.exec(select(Version)).all()) == 1
            assert len(s.exec(select(Question)).all()) == len(s.exec(select(Finding)).all()) == 1
            pages = s.exec(select(ReviewPage)).all()
            assert len(pages) == 3 and all(p.state == 'published' for p in pages)
            assert all(Backend(settings.state_path).body(p.path) == p.body for p in pages)
    finally:
        engine.dispose()


@pytest.mark.parametrize('point', ['retain-intent', 'retain-accepted', 'publication-intent', 'publication-accepted'])
def test_hard_kill_resumes_same_run_and_reuses_operations(case, point):
    settings, run_id = case
    first = WorkerProcess(settings, point)
    try:
        first.barrier()
        before = run_state(settings, run_id)
        assert before['state'] == 'running'
    finally:
        first.kill()
    engine = make_engine(settings.database_url)
    with Session(engine) as s:
        op_id = s.exec(select(Version)).one().operation_id
    engine.dispose()
    replacement = WorkerProcess(settings)
    try:
        replacement.finish()
    finally:
        replacement.kill()
    assert_complete(settings, run_id)
    assert run_state(settings, run_id)['started_at'] == before['started_at']
    backend = Backend(settings.state_path)
    retains = [r for r in backend.rows('calls') if r['method'] == 'POST' and r['path'] == '/memories']
    assert len(retains) == 1 and retains[0]['target'] == op_id
    assert len(backend.rows('docs')) == 1
    puts = [r for r in backend.rows('calls') if r['method'] == 'PUT' and r['path'].startswith('/.fs/')]
    assert len(puts) == (4 if point == 'publication-intent' else 3)
    assert Backend(settings.state_path).body(FIXTURE).startswith('# Synthetic recovery fixture')


@pytest.mark.parametrize('point,remote_operations', [('consolidate-intent', 0), ('consolidate-accepted', 1)])
def test_unknown_consolidation_outcome_stops_without_resubmitting(case, point, remote_operations):
    settings, run_id = case
    first = WorkerProcess(settings, point)
    try:
        first.barrier()
    finally:
        first.kill()
    replacement = WorkerProcess(settings)
    try:
        replacement.finish()
    finally:
        replacement.kill()
    result = run_state(settings, run_id)
    assert result['state'] == 'failed' and result['error'] == 'consolidation_requires_reconciliation'
    remote = Backend(settings.state_path)
    assert sum(r['method'] == 'POST' and r['path'] == '/consolidate' for r in remote.rows('calls')) == 1
    assert sum(r['kind'] == 'consolidation' for r in remote.rows('ops')) == remote_operations


def test_human_edit_after_remote_write_is_preserved_and_other_pages_publish(case):
    settings, run_id = case
    first = WorkerProcess(settings, 'publication-accepted')
    try:
        event = first.barrier()
    finally:
        first.kill()
    backend = Backend(settings.state_path);path = event['value']
    edited = backend.body(path).replace('Synthetic recovery question?', 'My edited question stays here.')
    backend.edit(path, edited)
    replacement = WorkerProcess(settings)
    try:
        replacement.finish()
    finally:
        replacement.kill()
    assert backend.body(path) == edited
    result = run_state(settings, run_id)
    assert result['result']['publication'] == 'partial'
    engine = make_engine(settings.database_url)
    with Session(engine) as s:
        pages = s.exec(select(ReviewPage)).all()
        assert sum(p.state == 'conflict' for p in pages) == 1
        assert sum(p.state == 'published' for p in pages) == 2
        assert s.get(ReviewPage, path).error == 'existing_review_page_requires_adoption'
    engine.dispose()


def test_restart_keeps_original_twenty_minute_budget(case):
    settings, run_id = case
    first = WorkerProcess(settings, 'capture')
    try:
        first.barrier()
    finally:
        first.kill()
    engine = make_engine(settings.database_url)
    # Simulate elapsed downtime without a twenty-minute test sleep.
    original = (datetime.now(UTC) - timedelta(seconds=1201)).isoformat()
    with Session(engine) as s:
        run = s.get(Run, run_id);run.started_at = original;s.add(run);s.commit()
    engine.dispose()
    replacement = WorkerProcess(settings)
    try:
        replacement.finish()
    finally:
        replacement.kill()
    result = run_state(settings, run_id)
    assert result['started_at'] == original
    assert result['state'] == 'failed' and result['error'] == 'run_budget_exhausted'
    assert not Backend(settings.state_path).rows('docs')


def test_remaining_budget_uses_start_and_rejects_invalid_timestamps():
    instant = datetime.now(UTC)
    assert remaining_run_seconds((instant - timedelta(seconds=1195)).isoformat(), instant) == 5
    assert remaining_run_seconds((instant - timedelta(seconds=1201)).isoformat(), instant) == 0
    assert remaining_run_seconds((instant + timedelta(seconds=10)).isoformat(), instant) == 1200
    for invalid in ('', 'not-a-date', instant.replace(tzinfo=None).isoformat()):
        with pytest.raises(DomainError, match='run_budget_timestamp_invalid'):
            remaining_run_seconds(invalid, instant)


def test_recovery_database_guards_reject_production_and_outside_sqlite(tmp_path):
    for url in ('postgresql://localhost/knowledge_curator', 'postgresql://localhost/knowledge_pilot',
                'postgresql://localhost/xereta_recovery_not-a-generated-id'):
        with pytest.raises(ValueError, match='disposable_recovery_database_required'):
            guarded_database(url)
    with pytest.raises(ValueError, match='sqlite_state_must_be_inside_recovery_directory'):
        setup_case(tmp_path, 'sqlite:////outside-recovery.sqlite3')


def test_postgresql_lock_transfers_to_one_replacement_after_death(case):
    settings, run_id = case
    if not settings.database_url.startswith('postgresql'):
        pytest.skip('operator gate supplies a disposable PostgreSQL database')
    first = WorkerProcess(settings, 'capture')
    try:
        first.barrier()
        contender = WorkerProcess(settings)
        try:
            contender.finish()
        finally:
            contender.kill()
        assert run_state(settings, run_id)['state'] == 'running'
        assert sum(r['path'] == '/.fs' for r in Backend(settings.state_path).rows('calls')) == 1
    finally:
        first.kill()
    replacement = WorkerProcess(settings)
    try:
        replacement.finish()
    finally:
        replacement.kill()
    assert_complete(settings, run_id)
