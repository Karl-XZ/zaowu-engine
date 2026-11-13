# 自然语言 CAD 更新（2026-11-13）

`/cad` 现在默认提供面向普通用户的自由描述入口：说清用途→AI理解与日常语言补问→确认建议尺寸/假设→DeepSeek编写CadQuery脚本→独立进程OpenCascade构建→尺寸/网格/独立AI设计核对→STEP/STL/GLB/3MF下载。

固定模板仅保留在折叠的高级模式。AI方案不会回退成固定铭牌或盒子模板。CAD脚本使用受限AST解释器，不执行任意Python，且不把密钥传入CAD进程。Windows Job限制内存/CPU，单文件导出限制64MB。

脚本错误可在预算内最多修正两轮（含首次共三次）；未通过检查不扣模型次数。AI设计核对不是数学证明或承重认证，交付模型仍需用户预览确认，复杂曲面、雕塑和精密装配可能不支持。真实验收记录见 [自然语言CAD验收](docs/NATURAL_LANGUAGE_CAD_STATUS.md)。

依赖新增 `cadquery==2.6.1`；已有环境请先在项目根运行 `uv pip install --python backend/.venv/Scripts/python.exe -r backend/requirements.txt` 后再启动。

---

# 造物引擎 ZAOWU ENGINE

> 心意，要有形状。—— AI 个性化 3D 打印礼物定制平台（对应 PRD V1.4，见 `docs/`）

**主流程（创意路线）**：一句话描述 → AI 设计效果图 → 对话调整造型 / 风格 / 颜色（每次设计最多 10 次）→ 确认后 Aholo Lux3D 图生 3D → 修复 · 制造预检 · 切片 → 嘉立创打印。
**实用物品 CAD 路线**：日常语言 → AI理解与补问 → 确认方案 → AI编写CAD脚本 → 真实CAD内核执行 → 检查 → STEP及网格文件交付。高级入口保留本地参数模板。

---

## Windows 启动（已配置真实生成）

运行 `./start.ps1`，浏览器打开 http://127.0.0.1:5173/ 。真实 API 配置只保存在本机 `.env`；不要分发该文件。

Aholo 生图/参考图编辑/3D 已按官方协议接通，DeepSeek 解析设计规格。`AHOLO_QUOTE_ENABLED=true` 时每次真实创建先检查账户、精确请求积分报价和单次积分上限；人民币成本字段仍为内部估计，不能当作真实账单。

支付宝继续模拟，嘉立创继续手动导出跳转。AI CAD 输出 STEP/STL/3MF/GLB 与报告；旧模板输出 STL/3MF/GLB。切片器未配置时明确显示几何估算。

## Bash 启动

```bash
./start.sh
```

- 前端：http://localhost:5173 后端 API：http://localhost:8010（接口文档 http://localhost:8010/docs）
- 首次运行会自动创建 `.env`、Python 虚拟环境（需 Python ≥ 3.10）并安装前端依赖。
- 用 `ADMIN_EMAILS` 里的邮箱（默认 `admin@zaowu.local`）注册即为管理员，可进入 `/admin`。
- 后端端口可改：`API_PORT=8020 ./start.sh`。

### 模拟模式（API 还没填时）

仅在对应第三方能力未配置时，系统进入**模拟模式**，完整流程可以直接演示：

| 能力 | 模拟方式 | 真实接入后 |
|---|---|---|
| 效果图生成 | Pillow 绘制示意效果图，颜色 / 风格 / 造型随对话变化 | 调用你选定的生图供应商 |
| Aholo Lux3D | manifold3d 生成与效果图一致的水密网格 | 调用 Lux3D 图生 3D，轮询任务、转存结果 |
| 支付宝 | 站内「模拟收银台」，与真实异步通知走同一入账逻辑 | 跳转支付宝收银台，验签 + 主动查单 |
| 嘉立创 | 模式 B：下载生产文件包 + 跳转官网上传 | 模式 A：自动报价 / 下单（API 审核通过后） |
| 切片 | 几何估算（首层面积、悬垂、支撑、耗时、耗材） | OrcaSlicer / PrusaSlicer 命令行真实切片 |

后台 `/admin` 顶部会显示每项能力当前是「模拟模式」还是「已接入」。

---

## 需要你填的 API（都在 `.env` + 对应适配器的 `TODO(接入)` 处）

| 配置项 | 适配器文件 | 说明 |
|---|---|---|
| `IMAGE_PROVIDER` / `IMAGE_API_BASE` / `IMAGE_API_KEY` | `backend/app/providers/image.py` → `_real_generate` | 首图 = 文生图；调整 = 以上一版为参考图做编辑。返回 PNG 字节 + 实际扣费（分） |
| `AHOLO_API_BASE` / `AHOLO_API_KEY` / `AHOLO_MODEL_VERSION` | `backend/app/providers/aholo.py` → `submit` / `poll` / `download` | 端点与字段名以你绑定地区控制台的 OpenAPI 为准；纯图生 3D 无公开 prompt 字段，需要文字约束时走文生 3D 的 img + prompt |
| `ALIPAY_*` | `backend/app/providers/alipay.py` | 已实现 RSA2 签名、验签、查单骨架；按 Vibe Pay 文档确认 method 与 biz_content，补全 `refund` |
| `JLC_*` | `backend/app/providers/jlc.py` | 获批后实现报价 / 下单签名；未获批保持模式 B |
| `SLICER_CLI_PATH` | `backend/app/services/slicer.py` | 填 OrcaSlicer / PrusaSlicer 可执行文件路径（注意 AGPL 许可，以独立进程调用） |
| `COST_*` | `.env` | 拿到真实单价后修改，Cost Governor 依此预留预算；未知成本禁止调用 |

---

## 已实现的 PRD 能力

**计次与权益**（§5）：每日 3 次免费（北京时间重置，创意与 CAD 共用）· 超出 ¥5 · 开启设计即预留 · 只有 `VERIFIED_DELIVERABLE` 才核销 · 失败 / 放弃释放 · 付费失败恢复为权益并可原路退款 · 失败次数 / 失败成本 / 连续失败 / 放弃会话上限 · 平台每日免费预算熔断 · 并发原子预留 · 幂等键防重复创建。

**对话设计**（§2.4）：首图 + ≤10 次调整服务端原子计数 · 每轮本地预检（飘浮、细杆、无限薄、版权角色、违禁品、尺寸），被拦下不计次 · 版本 v0…v10 全保留，可回看、以任一版为基础继续改或直接确认 · 单色材料改颜色时提示材料本色 · 转换前构图质检。

**生成与验收**（§3、§4）：Prompt Compiler（DesignSpec + 版本化模板）· Cost Governor（调用前预留、成本账本只增不减）· 网格修复（法线、孔洞、流形重建、孤立碎片）· 制造预检（水密、体积、尺寸、实体数、射线法壁厚 P5 / P1，不可测即阻断）· 切片检查 · STL / 3MF / GLB / 检测报告 · SHA-256 锁定 · 预算内最多一次付费重生成。

**精确 CAD**（§3.2）：自然语言抽取参数 · 铭牌 / 钥匙扣 / 圆形底座 / 收纳盒四个模板 · 材料规则校验（壁厚、孔径、孔边距、尺寸上限）· 同模板纯参数重建不计次（每日 30 次）。

**申诉与售后**（§5.6、§4.8）：24 小时内、未下载生产文件前可申诉；清单项 / 与效果图不符自动或人工判定；平台责任自动恢复额度（跨日补 1 次付费权益）。

**安全**（§10）：私有文件 + 短效签名下载链接 · 金额只由服务端决定 · 支付通知验签 + 查单 + 幂等 · 版权角色与违禁品拦截 · 注册需同意隐私与照片授权。

**前端**：构成主义视觉系统（红 / 黑 / 纸三色、对角线、几何体、硬阴影）· WebGL 礼盒随滚动「解构」· 逐字砸入的大标题 · 滚动点亮的宣言 · 横向钉住滚动的四步流程 · 自动播放的对话演示 · 斜切页面转场 · 十字准星光标与毫米坐标 · 印章砸下动画 · 实时重绘的 CAD 工程图 · 三维模型查看器（实体 / 红陶 / 线框 / 透视）· 移动端适配 · `prefers-reduced-motion` 降级。

---

## 测试

```bash
cd backend && .venv/bin/python -m pytest -q
```

覆盖：生成前阻断、首图、预检拦截不计次、10 次上限、选旧版本确认、交付核销、签名下载、CAD 尺寸实测与免费重建、额度用尽需付款、支付回调重复 5 次只入账一次、放弃会话退回额度。

## 生产部署

```bash
cd frontend && npm run build          # 生成 frontend/dist
cd ../backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010 --workers 1
```

后端会直接托管 `frontend/dist`。上线前务必：修改 `SECRET_KEY`、换用 PostgreSQL、把文件存储换成 S3 兼容存储（`services/storage.py`）、配置 HTTPS 与 `ALIPAY_NOTIFY_URL`。任务队列默认进程内线程池（重启自动恢复），多实例部署时替换为 Celery / RQ（`services/jobs.py`，任务函数不变）。

## 目录

```
backend/app/
  config.py            全部配置（.env）
  models.py            数据实体（PRD §9.1）
  routers/             auth · design（对话设计）· cad · models（任务/作品/申诉）· pay · misc（额度/文件/嘉立创/后台）
  services/            quota 额度账本 · preflight 预检 · prompt_compiler · cost_governor · mesh_pipeline · slicer · cad_templates · jobs
  providers/           image · aholo · alipay · jlc   ← 在这里接真实 API
frontend/src/
  pages/               Home · Create（设置 + 对话工作室）· Cad · Model（任务进度 + 交付）· Misc（登录/付费/作品/后台/规则）
  components/          HeroScene（WebGL）· ModelViewer · Motion（动效原语）· Chrome（导航/转场/光标）
docs/                  PRD V1.4 · UI 设计方案
```


## 本轮实现与验证

- 真实接口：Aholo CN 原始 Authorization、异步任务、统一 Asset/OUS 上传、模型 ZIP/GLB 转存；真实失败不切回模拟。
- 流程可靠性：创建前持久化账本、重复提交归属与互斥、已知任务查询恢复、未知创建不自动重发、失败恢复额度。
- 模型：UV/法线接缝几何焊接，保留原始外观预览；修复后的生产网格独立导出。
- 测试必须在 backend 目录运行：`.venv/Scripts/python.exe -m pytest -q`。所有自动测试强制使用临时数据库和模拟传输，不消耗真实密钥。
- 中断后的图像任务保留供应商任务号，但需人工核对后恢复；不自动重新付费创建。当前是共享本地文件与 SQLite 的单机部署，不代表多机生产集群验收。
- 几何预检通过不等于制造商承诺可打印；真实切片、STEP、全彩生产打包需后续单独验收。
