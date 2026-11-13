# 面向普通用户的自然语言 CAD 实施计划

目标：口语描述→DeepSeek设计理解→确认假设/补充问题→AI编写CadQuery脚本→受限独立进程执行OpenCascade→实体验证→STEP/STL/GLB/3MF交付。保留原模板API兼容与作品数据，不改变支付宝/嘉立创。

- [x] 内核：cad_sandbox.build_script(script,out_dir,timeout_s=60) 返回stl/step路径及metrics，AST白名单（CadQuery建模子集、无任意文件/网络/导入/反射）与无密钥子进程、时间/内存限制。实体合法、正体积、有限尺寸、数量检查。
- [x] AI：cad_ai.interpret(text,context=None) 返回ready/summary/questions/assumptions/requirements/dimensionsMm/expectedBodies；cad_ai.generate_script(plan,error=None,previous_script=None) 返回script。真实DeepSeek JSON，严格校验，不把未知输入改成铭牌模板。另有独立AI要求核对。
- [x] API：POST /cad/ai/plan {text,previousPlanId?} 生成所属用户DesignSpec(mode=ai)；POST /cad/ai/generate {planId,idempotencyKey,confirmAssumptions} 预留权益创建任务。任务执行AI脚本，预算内最多修正两轮，接现有制造检查和交付。
- [x] UI：默认口语输入、理解摘要/日常语言问题/假设确认、口语修改；模板为折叠高级入口。模型页显示CAD内核验证与STEP下载；不展示脚本给普通用户。
- [x] 测试：非模板新形状、口语单位/模糊需求/修正、真实DeepSeek→OpenCascade样例3类、恶意脚本与资源限制、幂等/额度/失败、全套143项回归与前端build通过。详见 ../../NATURAL_LANGUAGE_CAD_STATUS.md。

安全边界：执行的是受限建模脚本，不是任意Python。保持工艺约束由服务端校验，脚本不得读取宿主凭证。材料最小壁厚仍由独立网格检查核实。CAD可表达的几何不意味着任意雕塑必成功；不支持时明确解释。
恢复与回滚：新计划/任务存入既有JSON，无数据库破坏性迁移。停止新AI入口可回到原模板工作流；已生成作品继续可读。
