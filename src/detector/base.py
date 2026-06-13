"""
BaseDetector — 规则检测器基类

所有具体检测器（ConsecutiveDetector、WrongSymbolDetector 等）继承此基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.core.error_record import ErrorRecord
from src.core.text import TextDoc


class BaseDetector(ABC):
    """检测器基类。"""

    # 检测器名称（用于日志和报告）
    name: str = "base"

    # 优先级（0=最高，数字越大优先级越低）
    priority: int = 99

    @abstractmethod
    def detect(self, text: TextDoc) -> List[ErrorRecord]:
        """
        在文本中检测错误。

        Args:
            text: 已加载的文本文档。

        Returns:
            检测到的错误列表（按 offset 升序）。
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.name} priority={self.priority}>"
