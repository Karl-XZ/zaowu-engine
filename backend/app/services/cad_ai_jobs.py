"""Natural-language plans become bounded scripts, real solids and verified files."""
from pathlib import Path
import json

import numpy as np
from sqlalchemy import select
import trimesh

from ..config import settings
from ..models import Entitlement, ProviderCostLedger
from ..providers import cad_ai
from . import cad_sandbox, cost_governor, mesh_pipeline, quota, storage
from .materials import get_material


def run(db, task, spec):
    from . import jobs
    material = get_material(spec.material_id)
    params = dict(task.params)
    budget = params.get("budgetFen", settings.cad_ai_job_budget_fen)
    error = params.get("cadError")
    previous_script = None
    entitlement = db.get(Entitlement, task.entitlement_id) if task.entitlement_id else None
    free_tier = bool(entitlement and entitlement.kind == "free")

    def fail(reason):
        # Estimated external CAD costs still count as failure losses after quota restoration.
        calls = db.scalars(select(ProviderCostLedger).where(
            ProviderCostLedger.ref_type == "task", ProviderCostLedger.ref_id == task.id,
            ProviderCostLedger.endpoint.in_(("cad-script", "cad-review")))).all()
        quota.record_failure(db, task.user_id, sum(call.cost_estimated_fen for call in calls), counts_attempt=False)
        return jobs._fail(db, task, reason)
    max_attempts = max(1, min(settings.cad_ai_max_attempts, 3))
    for attempt in range(max_attempts):
        prefix = f"models/{task.id}/cad_attempt_{attempt}"
        script_path = storage.path_for(f"{prefix}/design.py")
        if script_path.exists():
            script = script_path.read_text(encoding="utf-8")
        else:
            calls = db.scalars(select(ProviderCostLedger).where(
                ProviderCostLedger.ref_type == "task", ProviderCostLedger.ref_id == task.id,
                ProviderCostLedger.endpoint.in_(("cad-script", "cad-review")))).all()
            if any(call.outcome == "pending" for call in calls):
                return fail("建模服务调用被中断，已恢复额度；请重新确认方案")
            spent = sum(call.cost_estimated_fen for call in calls)
            try:
                cost_governor.approve(budget - spent, settings.cost_cad_ai_fen)
            except cost_governor.BudgetExceeded:
                return fail("本次建模预算已用完，已恢复额度，请简化或修改设计后重试")
            jobs._stage(db, task, "RUNNING", "AI 正在编写建模脚本" if attempt == 0 else "根据实际检查结果修正脚本（不重复扣次）")
            call = cost_governor.open_call(db, user_id=task.user_id, ref_type="task", ref_id=task.id,
                provider="deepseek", endpoint="cad-script", estimate_fen=settings.cost_cad_ai_fen,
                free_tier=free_tier)
            try:
                script = cad_ai.generate_script(spec.spec, error=error, previous_script=previous_script)
            except Exception as exc:
                cost_governor.close_call(call, "failed")
                task.params = {**task.params, "cadError": str(exc)[:600] if isinstance(exc, cad_ai.CadAIError) else "AI请求异常"}
                db.commit()
                return fail("建模服务暂不可用，已恢复本次额度")
            staged_script = script_path.with_suffix(".pending")
            staged_script.write_text(script, encoding="utf-8")
            staged_script.replace(script_path)
            cost_governor.close_call(call, "success")  # Billing is an estimate, not an actual vendor bill.
            db.commit()
        previous_script = script
        try:
            jobs._stage(db, task, "RUNNING", "独立进程执行 CAD 内核，构建真实实体")
            built = cad_sandbox.build_script(script, script_path.parent, timeout_s=settings.cad_script_timeout_s)
            metrics = built["metrics"]
            if not metrics["valid"] or metrics["solidCount"] != spec.spec["expectedBodies"]:
                raise ValueError("实体数量或有效性与确认的方案不一致")
            measured = np.asarray(metrics["dimensionMm"], dtype=float)
            if not np.isfinite(measured).all() or measured.max() > material["max_size_mm"]:
                raise ValueError("建模结果超过材料可用尺寸")
            target = np.asarray(spec.spec["dimensionsMm"], dtype=float)
            if np.any(np.abs(measured - target) > np.maximum(2, target * .05)):
                raise ValueError(f"实际外形尺寸 {measured.round(2).tolist()} 与已确认建议尺寸 {spec.spec['dimensionsMm']} 不一致，请修正脚本")
            jobs._stage(db, task, "MANUFACTURING_VALIDATION", "CAD 实体有效性、实际尺寸及网格壁厚检查")
            mesh = trimesh.load(built["stl"], file_type="stl", force="mesh")
            result = mesh_pipeline.process(mesh, material, None, f"models/{task.id}", expected_bodies=metrics["solidCount"])
            if not result["passed"]:
                failed = [item["label"] + ": " + str(item["value"]) for item in result["report"]["check"]["items"] if not item["ok"]]
                raise ValueError("制造预检未通过：" + "；".join(failed or ["首层接触或切片估算不通过"]))
            if result["report"]["repairs"]:
                raise ValueError("CAD 网格需要额外修复，请直接修正实体脚本，确保 STEP 与网格几何一致")
            calls = db.scalars(select(ProviderCostLedger).where(
                ProviderCostLedger.ref_type == "task", ProviderCostLedger.ref_id == task.id)).all()
            if any(call.outcome == "pending" for call in calls):
                return fail("设计检查调用被中断，已恢复额度；请重新确认方案")
            spent = sum(call.cost_estimated_fen for call in calls)
            try:
                cost_governor.approve(budget - spent, settings.cost_cad_ai_fen)
            except cost_governor.BudgetExceeded:
                return fail("本次设计检查预算已用完，已恢复额度")
            review_call = cost_governor.open_call(db, user_id=task.user_id, ref_type="task", ref_id=task.id,
                provider="deepseek", endpoint="cad-review", estimate_fen=settings.cost_cad_ai_fen, free_tier=free_tier)
            try:
                review = cad_ai.review_script(spec.spec, script, metrics)
            except Exception:
                cost_governor.close_call(review_call, "failed")
                db.commit()
                return fail("设计要求检查暂不可用，已恢复本次额度")
            cost_governor.close_call(review_call, "success")
            db.commit()
            if not review["meetsRequirements"]:
                raise ValueError("设计要求检查未通过：" + "；".join(review["missingFeatures"]))
            # The two production files come directly from the SAME native solid,
            # preserving identical geometry and origin; viewer/3MF may be centered.
            storage.save_bytes(result["files"]["stl"], Path(built["stl"]).read_bytes())
            result["hash"] = storage.sha256_file(result["files"]["stl"])
            result["files"]["step"] = storage.save_bytes(f"models/{task.id}/model.step", Path(built["step"]).read_bytes())
            result["report"]["cad"] = {"kernel": "CadQuery/OpenCascade", **metrics,
                "attemptsUsed": attempt + 1, "requestedDimensionsMm": spec.spec["dimensionsMm"],
                "requirementsReview": {**review, "method": "AI script and kernel-metrics review", "requiresUserConfirmation": True}}
            storage.save_bytes(result["files"]["report"], json.dumps(result["report"], ensure_ascii=False, indent=2).encode())
            jobs._stage(db, task, "SLICE_CHECK", "实体和制造预检完成，导出 STEP 与网格文件")
            return jobs._deliver(db, task, spec, result, spec.spec["summary"][:100])
        except Exception as exc:
            error = str(exc)[:1200]
            params = {**task.params, "cadError": error, "cadAttempt": attempt}
            task.params = params
            db.commit()
            if attempt + 1 < max_attempts:
                jobs._stage(db, task, "REPAIRING", f"本地或设计检查未通过，进行第 {attempt + 1} 次预算内修正")
    return fail("暂时无法按此方案完成建模：" + (error or "实体检查失败")[:500])
