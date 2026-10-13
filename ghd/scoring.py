"""活动积分结算引擎(纯计算):动态表单数据 -> 各队员积分字典。"""

from dataclasses import dataclass, field

from .constants import (CHIEF_INSTRUCTOR_BONUS, CHIEF_MAX_COUNT, DURATION_MAX,
                        DURATION_MIN, DURATION_STEP, FIELD_DUTY_BONUS, HOUR_SCORE)
from .name_parser import parse_names
from .utils import to_num


@dataclass
class RoundCard:
    """训练/彩排卡片。"""
    kind: str            # "training" | "rehearsal"
    duration: float      # 0.5 ~ 4.0 小时
    instructors: list[str] = field(default_factory=list)
    attendees: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errs: list[str] = []
        d = to_num(self.duration, 0.0)
        if d < DURATION_MIN - 1e-9 or d > DURATION_MAX + 1e-9:
            errs.append(f"{'训练' if self.kind == 'training' else '彩排'}时长须在 {DURATION_MIN}~{DURATION_MAX} 小时之间")
        if abs(d / DURATION_STEP - round(d / DURATION_STEP)) > 1e-9:
            errs.append("时长步长须为 0.5 小时")
        return errs


@dataclass
class EventForm:
    """活动结算表单。"""
    name: str
    chief_instructors: list[str] = field(default_factory=list)
    training_cards: list[RoundCard] = field(default_factory=list)   # N >= 0
    rehearsal_cards: list[RoundCard] = field(default_factory=list)  # M >= 1
    formal_duration: float = 1.0
    formal_attendees: list[str] = field(default_factory=list)   # 参加(原参训)
    field_duty: list[str] = field(default_factory=list)         # 场务(可为空)

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        errs: list[str] = []
        if not self.name or not self.name.strip():
            errs.append("活动名称为必填项")
        if not (1 <= len(self.chief_instructors) <= CHIEF_MAX_COUNT):
            errs.append(f"主教官须输入 1~{CHIEF_MAX_COUNT} 位人名")
        for card in self.training_cards + self.rehearsal_cards:
            errs.extend(card.validate())
        if len(self.rehearsal_cards) < 1:
            errs.append("至少保留 1 张彩排卡片")
        d = to_num(self.formal_duration, 0.0)
        if d < DURATION_MIN - 1e-9 or d > DURATION_MAX + 1e-9:
            errs.append(f"活动时长须在 {DURATION_MIN}~{DURATION_MAX} 小时之间")
        return errs

    # ------------------------------------------------------------------
    # 积分计算
    # ------------------------------------------------------------------
    def compute(self) -> dict[str, float]:
        """结算各队员积分(线性累加),返回 {姓名: 本次活动总积分}。

        - 主教官:每位固定 +2.0
        - 训练/彩排:教官与参训按该次时长计分(1 小时 = 1.0 分)
        - 正式出旗:参加人员按正式时长计分;场务固定 +0.5(与时长无关)
        - 同一队员所有环节线性累加;场务人员若同时参加出旗,两份都计
        """
        scores: dict[str, float] = {}

        def add(name: str, pts: float) -> None:
            scores[name] = round(scores.get(name, 0.0) + pts, 2)

        for chief in self.chief_instructors:
            add(chief, CHIEF_INSTRUCTOR_BONUS)

        for card in self.training_cards + self.rehearsal_cards:
            d = to_num(card.duration, 0.0)
            for name in card.instructors:
                add(name, d * HOUR_SCORE)
            for name in card.attendees:
                add(name, d * HOUR_SCORE)

        d = to_num(self.formal_duration, 0.0)
        for name in self.formal_attendees:
            add(name, d * HOUR_SCORE)
        for name in self.field_duty:
            add(name, FIELD_DUTY_BONUS)

        return scores
