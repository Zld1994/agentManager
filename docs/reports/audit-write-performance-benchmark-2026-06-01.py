#!/usr/bin/env python3
"""Measure audit event write overhead for configured sink modes."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

from agentManager.observability import audit
from agentManager.observability.audit import (
    AuditEvent,
    AuditEventType,
    configure_audit_sinks,
    record_audit_event,
    reset_audit_sinks,
)

ITERATIONS = 1000
REPORT_PATH = Path(__file__).with_suffix(".md")


@dataclass
class Result:
    mode: str
    p50: float
    p99: float
    mean: float
    threshold_ms: float
    threshold_passed: bool


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * percentile))
    return ordered[index]


def _sample_event(index: int) -> AuditEvent:
    return AuditEvent(
        event_type=AuditEventType.TASK_EXECUTED,
        actor="benchmark",
        resource=f"task-{index}",
        outcome="success",
        detail={"duration_ms": index % 10, "token": "secret"},
        timestamp="2026-06-02T00:00:00+00:00",
    )


def _measure(mode: str, threshold_ms: float, setup) -> Result:
    reset_audit_sinks()
    original_get_sinks = audit._get_audit_sinks
    try:
        setup()
        latencies: list[float] = []
        for index in range(ITERATIONS):
            start = time.perf_counter()
            record_audit_event(_sample_event(index))
            latencies.append((time.perf_counter() - start) * 1000)
    finally:
        audit._get_audit_sinks = original_get_sinks
        reset_audit_sinks()

    p50 = statistics.median(latencies)
    p99 = _percentile(latencies, 0.99)
    return Result(
        mode=mode,
        p50=p50,
        p99=p99,
        mean=statistics.mean(latencies),
        threshold_ms=threshold_ms,
        threshold_passed=p99 < threshold_ms,
    )


def _render_report(results: list[Result]) -> str:
    rows = "\n".join(
        "| {mode} | {p50:.4f} | {p99:.4f} | {mean:.4f} | < {threshold:.1f} | {status} |".format(
            mode=result.mode,
            p50=result.p50,
            p99=result.p99,
            mean=result.mean,
            threshold=result.threshold_ms,
            status="PASS" if result.threshold_passed else "FAIL",
        )
        for result in results
    )
    return "\n".join(
        [
            "# 审计写入性能基准测试报告",
            "",
            "**测试日期：** 2026-06-02",
            "**任务：** M4-F.3.2 - 测量审计写入对关键路径的性能影响",
            f"**样本数：** 每种模式 {ITERATIONS} 次",
            "",
            "## 测试方法",
            "",
            "该基准直接调用 `record_audit_event()`。",
            "`disabled` 模式通过临时空 sink 集合测量函数框架开销。",
            "`log` 模式使用真实 logger。",
            "`db` 和 `object_storage` 模式使用 mock repository/object store，",
            "避免结果依赖外部 PostgreSQL 或 S3 网络状态。",
            "",
            "## 结果",
            "",
            "| 模式 | P50 (ms/event) | P99 (ms/event) | Mean (ms/event) | 阈值 | 结果 |",
            "|------|----------------|----------------|-----------------|------|------|",
            rows,
            "",
            "## 结论",
            "",
            "验收阈值：log sink P99 < 0.1ms/event，db sink P99 < 5ms/event，",
            "object_storage sink P99 < 50ms/event。",
            "db/object_storage 的本地结果代表框架映射与调用开销；",
            "真实服务延迟需在部署环境继续观测。",
            "",
        ]
    )


def main() -> None:
    results = [
        _measure(
            "disabled",
            0.1,
            lambda: setattr(audit, "_get_audit_sinks", lambda: frozenset()),
        ),
        _measure("log", 0.1, lambda: configure_audit_sinks("log")),
        _measure(
            "db",
            5.0,
            lambda: configure_audit_sinks("db", repository=MagicMock()),
        ),
        _measure(
            "object_storage",
            50.0,
            lambda: configure_audit_sinks("object_storage", object_store=MagicMock()),
        ),
    ]
    report = _render_report(results)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
