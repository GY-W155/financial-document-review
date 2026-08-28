"""通用工具：金额、分页、结果包裹、审计。"""
from dataclasses import dataclass, field


@dataclass
class PageParams:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass
class PageResult:
    items: list = field(default_factory=list)
    total: int = 0


def paginate(items: list, total: int, page: int, page_size: int) -> dict:
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def to_float(value) -> float | None:
    """安全转 float，便于计算与展示。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def money_equal(a, b, tolerance: float) -> bool:
    """金额在容差内视为相等。"""
    fa, fb = to_float(a), to_float(b)
    if fa is None or fb is None:
        return False
    return abs(fa - fb) <= tolerance


def percent_diff(actual, reference) -> float | None:
    """计算差异比例（相对参考值）。"""
    fa, fr = to_float(actual), to_float(reference)
    if fa is None or fr is None or fr == 0:
        return None
    return round((fa - fr) / abs(fr) * 100, 4)
