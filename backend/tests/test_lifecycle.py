from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (User, DesignSpec, DesignSession, ConceptImage, GenerationTask,
                        Entitlement, ProviderCostLedger, now)
from app.routers import design, cad, models
from app.providers.aholo_client import AholoError
from app.services import jobs, quota, storage


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    monkeypatch.setattr(storage, "ROOT", tmp_path / "files")
    monkeypatch.setattr(jobs, "enqueue", lambda _: None)
    with factory() as db:
        u = User(email="owner@test.com", password_hash="x")
        other = User(email="other@test.com", password_hash="x")
        db.add_all([u, other]); db.flush()
        sp = DesignSpec(user_id=u.id, engine="creative", category="figurine", material_id="mono_resin",
                        material_profile_version="v1", size_mm=60, spec={"subject": "bear"})
        db.add(sp); db.flush()
        s = DesignSession(user_id=u.id, design_spec_id=sp.id, state="concept_ready", budget_fen=350,
                          expires_at=now() + timedelta(hours=1), current_version=0)
        db.add(s); db.flush()
        s.entitlement_id = quota.reserve(db, u, "session", s.id).id
        db.add(ConceptImage(session_id=s.id, version=0, qc_result={"passed": True}, file_path="concept.png"))
        storage.save_bytes("concept.png", b"image")
        db.commit()
        yield factory, u, other, s
    engine.dispose()


def test_confirm_freezes_session_against_abandon(lifecycle):
    factory, user, _, s = lifecycle
    with factory() as db:
        design.confirm(s.id, design.ConfirmIn(version=0), user, db)
        design.abandon(s.id, user, db)
        assert db.get(Entitlement, s.entitlement_id).state == "reserved"
        assert db.get(DesignSession, s.id).state == "confirmed"


def test_idempotency_key_never_discloses_another_users_task(lifecycle):
    factory, user, other, s = lifecycle
    with factory() as db:
        design.confirm(s.id, design.ConfirmIn(version=0, idempotencyKey="shared"), user, db)
    with factory() as db, pytest.raises(HTTPException) as exc:
        cad.generate(cad.GenIn(template="keychain", params={}, idempotencyKey="shared"), other, db)
    assert exc.value.status_code == 409


def test_first_image_failure_preserves_cost_and_releases_entitlement(lifecycle, monkeypatch):
    factory, user, _, _ = lifecycle
    def fail(*args):
        with factory() as inspect:
            assert inspect.scalar(select(ProviderCostLedger)) is not None
        raise RuntimeError("supplier secret response")
    monkeypatch.setattr(design.image_provider, "generate", fail)
    with factory() as db, pytest.raises(HTTPException) as exc:
        design.open_session(design.OpenIn(prompt="一只小熊"), user, db)
    assert exc.value.status_code == 502
    with factory() as db:
        call = db.scalar(select(ProviderCostLedger))
        assert call.outcome == "failed" and call.bill_status == "estimated"
        assert call.cost_actual_fen is None
        failed = db.scalar(select(DesignSession).where(DesignSession.id == call.ref_id))
        assert db.get(Entitlement, failed.entitlement_id).state == "released"


def test_poll_timeout_keeps_provider_id_and_reservation(lifecycle, monkeypatch):
    factory, user, _, s = lifecycle
    monkeypatch.setattr(jobs.aholo, "submit", lambda *args: "existing-provider-id")
    def timeout(*args):
        raise TimeoutError("network")
    monkeypatch.setattr(jobs.aholo, "poll", timeout)
    with factory() as db:
        tid = design.confirm(s.id, design.ConfirmIn(version=0), user, db)["taskId"]
    jobs._run_safe(tid)
    with factory() as db:
        task = db.get(GenerationTask, tid)
        assert task.state == "RUNNING"
        assert task.provider_task_id == "existing-provider-id"
        assert db.get(Entitlement, task.entitlement_id).state == "reserved"


def test_uncertain_submission_never_retries_paid_creation(lifecycle, monkeypatch):
    factory, user, _, s = lifecycle
    calls = []
    def uncertain(*args):
        calls.append(1)
        with factory() as inspect:
            assert inspect.scalar(select(ProviderCostLedger)) is not None
        raise TimeoutError("accepted but response lost")
    monkeypatch.setattr(jobs.aholo, "submit", uncertain)
    with factory() as db:
        tid = design.confirm(s.id, design.ConfirmIn(version=0), user, db)["taskId"]
    jobs._run_safe(tid)
    jobs._run_safe(tid)
    assert len(calls) == 1
    with factory() as db:
        assert db.get(GenerationTask, tid).state not in jobs.TERMINAL


def test_concurrent_confirm_creates_one_task(lifecycle):
    factory, user, _, s = lifecycle
    def confirm(_):
        with factory() as db:
            return design.confirm(s.id, design.ConfirmIn(version=0), user, db)["taskId"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(confirm, range(4)))
    assert len(set(ids)) == 1


def test_confirm_cannot_run_during_image_edit(lifecycle):
    factory, user, _, s = lifecycle
    with factory() as db:
        db.get(DesignSession, s.id).state = "generating"
        db.commit()
    with factory() as db, pytest.raises(HTTPException) as exc:
        design.confirm(s.id, design.ConfirmIn(version=0), user, db)
    assert exc.value.status_code == 409


def test_qc_reports_actual_integrity_without_claiming_visual_checks():
    import io
    from PIL import Image
    output = io.BytesIO()
    Image.new("RGB", (512, 512)).save(output, "PNG")
    qc = design._qc({"connectedBase": True}, output.getvalue())
    assert qc["passed"] and qc["estimated"]
    assert qc["method"] == "image-integrity-and-design-rules"
    assert qc["singleSubject"] is None and qc["noFloating"] is None
    assert not design._qc({"connectedBase": True}, b"broken PNG")["passed"]


def test_recovery_does_not_charge_already_recorded_provider_cost(lifecycle, monkeypatch):
    factory, user, _, s = lifecycle
    with factory() as db:
        tid = design.confirm(s.id, design.ConfirmIn(version=0), user, db)["taskId"]
        task = db.get(GenerationTask, tid)
        task.provider_task_id = "already-billed"
        task.cost_actual_fen = 100
        db.get(DesignSession, s.id).spent_fen = 110
        db.add(ProviderCostLedger(user_id=user.id, ref_type="task", ref_id=tid, provider="aholo",
                                 endpoint="image-to-3d", provider_task_id="already-billed", outcome="success",
                                 cost_estimated_fen=100, cost_actual_fen=100, bill_status="actual"))
        db.commit()
    monkeypatch.setattr(jobs.aholo, "poll", lambda _: {"status": "failed", "costFen": 100})
    jobs._run_safe(tid)
    with factory() as db:
        assert db.get(GenerationTask, tid).cost_actual_fen == 100
        assert db.get(DesignSession, s.id).spent_fen == 110


def test_concurrent_quota_reservation_cannot_overspend(lifecycle):
    factory, user, _, _ = lifecycle
    def reserve(i):
        with factory() as db:
            try:
                quota.reserve(db, user, "task", str(i))
                db.commit()
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(reserve, range(4)))
    assert sorted(statuses) == [200, 200, 402, 402]


def test_two_workers_never_submit_same_task_twice(lifecycle, monkeypatch):
    from threading import Event
    factory, user, _, s = lifecycle
    entered, release = Event(), Event()
    submissions = []
    def submit(*args):
        submissions.append(1)
        return "only-one"
    def poll(_):
        entered.set()
        assert release.wait(5)
        return {"status": "failed", "costFen": 100}
    monkeypatch.setattr(jobs.aholo, "submit", submit)
    monkeypatch.setattr(jobs.aholo, "poll", poll)
    with factory() as db:
        tid = design.confirm(s.id, design.ConfirmIn(version=0), user, db)["taskId"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(jobs._run_safe, tid)
        try:
            assert entered.wait(5)
            second = pool.submit(jobs._run_safe, tid)
            second.result(timeout=5)
        finally:
            release.set()
        first.result(timeout=5)
    assert len(submissions) == 1


def test_explicit_provider_rejection_releases_reservation(lifecycle, monkeypatch):
    factory, user, _, s = lifecycle
    def rejected(*args):
        raise AholoError("insufficient provider balance")
    monkeypatch.setattr(jobs.aholo, "submit", rejected)
    with factory() as db:
        tid = design.confirm(s.id, design.ConfirmIn(version=0), user, db)["taskId"]
    jobs._run_safe(tid)
    with factory() as db:
        task = db.get(GenerationTask, tid)
        assert task.state == "FAILED_REFUND"
        assert db.get(Entitlement, task.entitlement_id).state == "released"
        call = db.scalar(select(ProviderCostLedger))
        assert call.outcome == "failed" and call.cost_actual_fen == 0


def test_get_requeues_only_stale_known_provider_queries(lifecycle, monkeypatch):
    factory, user, other, s = lifecycle
    enqueued = []
    monkeypatch.setattr(jobs, "enqueue", enqueued.append)
    with factory() as db:
        tid = design.confirm(s.id, design.ConfirmIn(version=0), user, db)["taskId"]
        enqueued.clear()
        task = db.get(GenerationTask, tid)
        task.state, task.error = "RUNNING", "poll timed out"
        task.updated_at = now() - timedelta(seconds=60)
        db.commit()
        models.get_generation(tid, user, db)
        assert enqueued == []  # Unknown creation cannot be repeated.
        task.provider_task_id = "known"
        task.updated_at = now() - timedelta(seconds=60)
        db.commit()
        models.get_generation(tid, user, db)
        assert enqueued == [tid]
        models.get_generation(tid, user, db)
        assert enqueued == [tid]  # Recovery is throttled even before worker starts.
        with pytest.raises(HTTPException):
            models.get_generation(tid, other, db)


def test_real_image_ledger_retains_task_id_and_estimated_price(lifecycle, monkeypatch):
    import io
    from types import SimpleNamespace
    from PIL import Image
    factory, user, _, _ = lifecycle
    monkeypatch.setattr(design.settings, "image_provider", "aholo")
    monkeypatch.setattr(design.settings, "image_api_key", "fake-not-network")
    buffer = io.BytesIO()
    Image.new("RGB", (512, 512)).save(buffer, "PNG")
    def generate(*args, on_task_created=None):
        on_task_created("image-task")
        with factory() as inspect:
            call = inspect.scalar(select(ProviderCostLedger))
            assert call.provider_task_id == "image-task" and call.outcome == "pending"
        return SimpleNamespace(png=buffer.getvalue(), provider="aholo", cost_fen=10,
                               actual_cost_known=False, task_id="image-task")
    monkeypatch.setattr(design.image_provider, "generate", generate)
    with factory() as db:
        design.open_session(design.OpenIn(prompt="一只小熊"), user, db)
        call = db.scalar(select(ProviderCostLedger))
        assert call.bill_status == "estimated" and call.cost_actual_fen is None
        assert call.provider_task_id == "image-task"


def test_definite_image_rejection_is_not_recorded_as_spending(lifecycle, monkeypatch):
    factory, user, _, _ = lifecycle
    def rejected(*args):
        raise AholoError("explicit request rejection before task creation")
    monkeypatch.setattr(design.image_provider, "generate", rejected)
    with factory() as db, pytest.raises(HTTPException):
        design.open_session(design.OpenIn(prompt="一只小熊"), user, db)
    with factory() as db:
        call = db.scalar(select(ProviderCostLedger))
        assert call.outcome == "failed" and call.cost_actual_fen == 0
        assert db.get(DesignSession, call.ref_id).spent_fen == 0
