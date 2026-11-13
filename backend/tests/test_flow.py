"""端到端测试（MOCK 模式）。覆盖 PRD T-05/T-09/T-21/T-30/T-50～T-55 等核心用例。"""
import os
import tempfile
import time

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/t.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/files"
os.environ["IMAGE_PROVIDER"] = os.environ["AHOLO_API_KEY"] = os.environ["ALIPAY_APP_ID"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
client.__enter__()


def auth(email="u1@test.com"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": "secret123", "privacyConsent": True})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def wait_task(h, tid, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/v1/generations/{tid}", headers=h).json()
        if j["state"] in ("VERIFIED_DELIVERABLE", "FAILED_REFUND"):
            return j
        time.sleep(0.5)
    raise AssertionError("task timeout")


def test_design_flow_and_limits():
    h = auth()
    q = client.get("/api/v1/quota", headers=h).json()
    assert q["freeRemaining"] == 3
    # T-21：无限薄 → 生成前阻断，额度未用
    r = client.post("/api/v1/design-sessions", headers=h, json={"prompt": "做一个无限薄的挂件"})
    assert r.status_code == 422
    assert client.get("/api/v1/quota", headers=h).json()["freeRemaining"] == 3
    # T-50：首图
    s = client.post("/api/v1/design-sessions", headers=h, json={"prompt": "一个站在月亮上的Q版小熊", "sizeMm": 60}).json()
    assert s["turnsRemaining"] == 10 and len(s["concepts"]) == 1
    assert client.get("/api/v1/quota", headers=h).json()["freeReserved"] == 1
    sid = s["id"]
    # T-52：飘浮指令被拦截，不消耗次数
    s = client.post(f"/api/v1/design-sessions/{sid}/turns", headers=h, json={"instruction": "让一颗星星飘在它头顶"}).json()
    assert s["turnsUsed"] == 0 and s["messages"][-1]["role"] == "block"
    # T-54：颜色调整提示材料本色
    s = client.post(f"/api/v1/design-sessions/{sid}/turns", headers=h, json={"instruction": "颜色换成暖粉色"}).json()
    assert s["turnsUsed"] == 1 and "本色" in s["messages"][-1]["text"]
    for i in range(9):
        r = client.post(f"/api/v1/design-sessions/{sid}/turns", headers=h, json={"instruction": f"耳朵再圆一点 {i}"})
        assert r.status_code == 200, r.text
    # T-51：第 11 次被拒绝
    r = client.post(f"/api/v1/design-sessions/{sid}/turns", headers=h, json={"instruction": "再胖一点"})
    assert r.status_code == 409
    # T-53：选 v3 确认
    tid = client.post(f"/api/v1/design-sessions/{sid}/confirm", headers=h, json={"version": 3}).json()["taskId"]
    t = wait_task(h, tid)
    assert t["state"] == "VERIFIED_DELIVERABLE", t
    m = client.get(f"/api/v1/models/{t['modelVersionId']}", headers=h).json()
    assert m["report"]["check"]["passed"] and m["conceptVersion"] == 3 and "stl" in m["files"]
    q = client.get("/api/v1/quota", headers=h).json()
    assert q["freeUsed"] == 1 and q["freeReserved"] == 0
    # 签名下载
    assert client.get(m["files"]["glb"]).status_code == 200


def test_cad_and_free_rebuild():
    h = auth("cad@test.com")
    p = client.post("/api/v1/cad/parse", headers=h, json={"text": "80 mm 长、30 mm 宽、4 mm 厚，两个直径 5 mm 对称孔的铭牌，孔中心距 58 mm"}).json()
    assert p["template"] == "nameplate" and p["params"]["length"] == 80 and p["params"]["hole_spacing"] == 58 and not p["errors"]
    tid = client.post("/api/v1/cad/generate", headers=h, json={"template": "nameplate", "params": p["params"]}).json()["taskId"]
    t = wait_task(h, tid)
    assert t["state"] == "VERIFIED_DELIVERABLE", t
    m = client.get(f"/api/v1/models/{t['modelVersionId']}", headers=h).json()
    dims = sorted(m["dimensionMm"])
    assert abs(dims[2] - 80) < 0.05 and abs(dims[1] - 30) < 0.05 and abs(dims[0] - 4) < 0.05  # T-03
    # T-30：同模板改尺寸 → 免费重建，不扣额度
    r = client.post("/api/v1/cad/generate", headers=h, json={"template": "nameplate", "params": {**p["params"], "length": 90},
                                                              "parentModelId": m["id"]}).json()
    assert r["free"] is True
    wait_task(h, r["taskId"])
    assert client.get("/api/v1/quota", headers=h).json()["freeUsed"] == 1
    # 违反壁厚 → 422
    r = client.post("/api/v1/cad/generate", headers=h, json={"template": "nameplate", "params": {**p["params"], "thickness": 1}})
    assert r.status_code == 422


def test_quota_exhaust_and_payment_idempotent():
    h = auth("pay@test.com")
    for i in range(3):
        tid = client.post("/api/v1/cad/generate", headers=h, json={"template": "keychain", "params": {}}).json()["taskId"]
        wait_task(h, tid)
    # T-05：第 4 次需要付款
    r = client.post("/api/v1/cad/generate", headers=h, json={"template": "keychain", "params": {}})
    assert r.status_code == 402
    o = client.post("/api/v1/pay/orders", headers=h).json()
    # T-09：重复通知只入账一次
    for _ in range(5):
        client.post("/api/v1/pay/mock/confirm", headers=h, json={"outTradeNo": o["outTradeNo"]})
    assert client.get("/api/v1/quota", headers=h).json()["paidCredits"] == 1
    tid = client.post("/api/v1/cad/generate", headers=h, json={"template": "keychain", "params": {}}).json()["taskId"]
    assert wait_task(h, tid)["state"] == "VERIFIED_DELIVERABLE"
    assert client.get("/api/v1/quota", headers=h).json()["paidCredits"] == 0


def test_abandon_releases_quota():
    h = auth("ab@test.com")
    s = client.post("/api/v1/design-sessions", headers=h, json={"prompt": "一只戴围巾的橘猫"}).json()
    client.post(f"/api/v1/design-sessions/{s['id']}/abandon", headers=h)
    q = client.get("/api/v1/quota", headers=h).json()
    assert q["freeRemaining"] == 3 and q["abandonedSessions"] == 1 and q["failedCostFen"] > 0  # T-55
