"""生成前本地预检（PRD §3.4、§4.4）：在任何付费调用前阻断不可制造/违规/超预算的请求。外部成本 = 0。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FLOATING = re.compile(r"(悬浮|漂浮|飘在|飘浮|飘着|浮在|悬空|飞在空中|悬在|飘起来|浮起来)")
THIN = re.compile(r"(细杆|细线|发丝|极细|无限薄|零厚度|纸一样薄|薄如蝉翼|镂空花边|一根根|细铁丝|蕾丝)")
SEPARATE = re.compile(r"(分开的|分离的|几个独立|拆开|分体|散落)")
FORBIDDEN = re.compile(r"(枪支|手枪|步枪|子弹|刀具|匕首|管制刀|弩|爆炸|炸弹|毒品|纳粹)")
IP_RISK = re.compile(r"(皮卡丘|宝可梦|米老鼠|米奇|迪士尼|漫威|蜘蛛侠|钢铁侠|hello ?kitty|凯蒂猫|奥特曼|哆啦a梦|海绵宝宝|小黄人)", re.I)
CAD_HINT = re.compile(r"(\d+(\.\d+)?\s*(mm|毫米|厘米|cm)).*(孔|公差|厚)")


@dataclass
class Issue:
    code: str
    level: str  # block | warn
    message: str
    suggestion: str = ""


@dataclass
class PreflightResult:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "block" for i in self.issues)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issues": [i.__dict__ for i in self.issues]}


def check_text(text: str, material: dict, size_mm: float | None = None, engine: str = "creative") -> PreflightResult:
    r = PreflightResult()
    t = text.strip()
    if len(t) < 2:
        r.issues.append(Issue("empty", "block", "描述太短，请说说想送什么礼物。"))
        return r
    if len(t) > 400:
        r.issues.append(Issue("too_long", "block", "描述请控制在 400 字以内。"))
    if FORBIDDEN.search(t):
        r.issues.append(Issue("forbidden", "block", "这个内容属于平台不支持制作的物品。"))
    if IP_RISK.search(t):
        r.issues.append(Issue("ip_risk", "block", "描述里提到了受版权保护的角色，无法直接制作。",
                              "换成你自己的原创形象，比如“一只戴围巾的橘猫”。"))
    if FLOATING.search(t):
        r.issues.append(Issue("floating", "block", "飘浮/悬空的部件打印不出来。",
                              "改成与主体一体连接，例如抱在手里、立在底座上或贴在身上。"))
    if THIN.search(t):
        r.issues.append(Issue("thin", "block", f"过细或过薄的结构低于{material['name']}最小特征 {material['min_feature_mm']} mm。",
                              "把细节加粗，或改成浮雕/刻画在主体表面。"))
    if SEPARATE.search(t):
        r.issues.append(Issue("separate", "warn", "多个分离部件可能无法一体打印。", "建议用底座把它们连成一个整体。"))
    if size_mm is not None:
        if size_mm < material["min_size_mm"]:
            r.issues.append(Issue("too_small", "block", f"{material['name']}建议最小尺寸 {material['min_size_mm']} mm，太小细节会糊掉。"))
        if size_mm > material["max_size_mm"]:
            r.issues.append(Issue("too_large", "block", f"{material['name']}当前最大支持 {material['max_size_mm']} mm。"))
    if engine == "creative" and CAD_HINT.search(t):
        r.issues.append(Issue("cad_hint", "warn", "你的描述包含精确尺寸和孔位，精确 CAD 更合适。", "可以切换到“精确 CAD”。"))
    return r


def classify_dimension(instr: str) -> str:
    dims = []
    if re.search(r"(颜色|色|红|粉|蓝|绿|黄|紫|黑|白|金|银|橙|灰|棕)", instr):
        dims.append("颜色")
    if re.search(r"(风格|风|质感|黏土|粘土|水彩|像素|写实|卡通|赛博|手绘|陶瓷|毛绒|金属感|复古|极简)", instr):
        dims.append("风格")
    if not dims or re.search(r"(大|小|圆|胖|瘦|高|矮|耳朵|眼睛|表情|姿势|抱|手|脚|尾巴|底座|帽|围巾|形状|造型)", instr):
        dims.insert(0, "造型")
    return " + ".join(dict.fromkeys(dims))


def detect_category(text: str) -> str:
    if re.search(r"(钥匙扣|挂件|挂饰)", text):
        return "keychain"
    if re.search(r"(铭牌|名牌|牌子)", text):
        return "nameplate"
    if re.search(r"(徽章|胸针)", text):
        return "badge"
    if re.search(r"(手机支架|支架)", text):
        return "stand"
    return "figurine"
