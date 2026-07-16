#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
状态机模块 — 状态枚举 + 去抖 + 变化检测

职责：
  - 接收每帧匹配结果
  - 通过去抖（连续 N 帧一致才触发）避免误切换
  - 仅在确认状态变化时输出切换事件
  - 支持「无匹配」作为一个可切换的虚拟状态 (none_state)
"""

from typing import Optional

# 内部虚拟状态 ID：表示"无匹配"（none_state）
STATE_NONE = "__none__"


class StateMachine:
    """基于模板匹配的状态机，带去抖 + 优先级。

    支持 none_state：当启用时，无匹配帧也可以触发到 __none__ 状态的切换。
    none_state_allowed=False 则保持旧行为（无匹配不触发任何动作）。

    优先级：当多个 state 同时匹配时，按 priority 降序选择（越大越优先），
    同 priority 取最高匹配率。

    用法:
        sm = StateMachine(states=["walk", "drive"], threshold=0.75, debounce_count=3,
                         none_state_allowed=True,
                         priorities={"drive": 1, "walk": 0})
        sm.reset(None)
        for match_results in frame_stream:
            changed, old, new = sm.update(match_results)
            if changed:
                print(f"切换到 {new}")
    """

    def __init__(self,
                 states: list,
                 threshold: float = 0.75,
                 debounce_count: int = 3,
                 none_state_allowed: bool = False,
                 none_state_debounce: int = 20,
                 priorities: dict = None):
        """
        参数：
            states:             状态 ID 列表，如 ["walk", "drive"]
            threshold:          匹配率阈值，低于此值视为未识别
            debounce_count:     普通状态切换的去抖帧数
            none_state_allowed: 启用 __none__ 虚拟状态
            none_state_debounce: 进入 __none__ 的去抖帧数（独立于普通状态）
            priorities:         状态优先级 {state_id: int}，越大越优先，默认 0
        """
        self._real_states = list(states)
        self._none_state_allowed = none_state_allowed
        self._threshold = threshold
        self._debounce_count = debounce_count
        self._none_debounce = none_state_debounce
        self._priorities = dict(priorities) if priorities else {}
        self._current: Optional[str] = None
        self._pending: Optional[str] = None
        self._pending_count: int = 0
        self._none_pending_count: int = 0  # 独立的 none 去抖计数

    @property
    def current(self) -> Optional[str]:
        """当前确认的状态 ID，初始为 None。"""
        return self._current

    def reset(self, initial_state: Optional[str] = None):
        """重置状态机，可选指定初始状态。

           调用 update() 之前必须先 reset() 设置初始状态。
        """
        self._current = initial_state
        self._pending = initial_state
        self._pending_count = self._debounce_count  # 初始状态无需去抖
        self._none_pending_count = 0

    def update(self, match_results: dict) -> tuple:
        """
        输入一帧匹配结果，返回 (changed: bool, old_state: str|None, new_state: str|None)。

        match_results 格式: {state_id: {"val": float, ...}, ...}
        仅考虑 real_states 中声明的 ID（不含 __none__）。

        返回：
            changed:  是否发生了状态切换
            old_state: 切换前状态 ID（可能为 STATE_NONE）
            new_state: 切换后状态 ID（changed=False 时返回 None）
        """
        # 找出所有高于阈值的最佳候选
        candidates = []
        for sid in self._real_states:
            val = match_results.get(sid, {}).get("val", 0.0)
            if val >= self._threshold:
                candidates.append((sid, val))

        # 按优先级降序，同优先级按匹配率降序
        best_state = None
        if candidates:
            candidates.sort(key=lambda x: (self._priorities.get(x[0], 0), x[1]),
                            reverse=True)
            best_state = candidates[0][0]

        # 未识别到任何状态
        if best_state is None:
            if self._none_state_allowed:
                best_state = STATE_NONE
            else:
                return False, self._current, None

        # 候选状态与上一帧相同 → 累加计数
        # STATE_NONE 使用独立的去抖计数器
        if best_state == self._pending:
            if best_state == STATE_NONE:
                self._none_pending_count += 1
            else:
                self._pending_count += 1
        else:
            self._pending = best_state
            if best_state == STATE_NONE:
                self._none_pending_count = 1
                self._pending_count = 0
            else:
                self._pending_count = 1
                self._none_pending_count = 0

        # 去抖通过 → 触发切换
        if best_state == STATE_NONE:
            threshold_met = (self._none_pending_count >= self._none_debounce)
        else:
            threshold_met = (self._pending_count >= self._debounce_count)

        if threshold_met and self._pending != self._current:
            old = self._current
            self._current = self._pending
            return True, old, self._current

        return False, self._current, None
