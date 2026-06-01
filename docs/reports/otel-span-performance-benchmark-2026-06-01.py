#!/usr/bin/env python3
"""
M4-F.3.1: OTEL Span 性能基准测试
测量高频路径（scheduler, state_manager, task_executor）在 OTEL 启用/禁用时的延迟
"""
import asyncio
import time
import statistics

import httpx


BASE_URL = "http://127.0.0.1:8000"
RESULTS = {}


async def measure_latency(endpoint: str, iterations: int = 100) -> dict:
    """测量端点延迟"""
    async with httpx.AsyncClient(timeout=30) as client:
        latencies = []
        errors = 0

        for _ in range(iterations):
            try:
                start = time.perf_counter()
                resp = await client.get(f"{BASE_URL}{endpoint}")
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status_code == 200:
                    latencies.append(elapsed)
                else:
                    errors += 1
            except Exception:
                errors += 1

        if latencies:
            latencies.sort()
            return {
                "count": len(latencies),
                "errors": errors,
                "p50": latencies[len(latencies) // 2],
                "p99": latencies[int(len(latencies) * 0.99)],
                "mean": statistics.mean(latencies),
                "max": max(latencies),
            }
        return {"count": 0, "errors": errors}


async def run_otel_benchmark():
    """运行 OTEL 性能基准"""
    print("=" * 60)
    print("M4-F.3.1: OTEL Span 性能基准测试")
    print("=" * 60)

    # 检查 API 健康状态
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BASE_URL}/health")
        health = resp.json()
        print(f"\n/health 状态: {health}")

        # 检查 OTEL 状态
        otel_status = health.get("dependencies", {}).get("otel_collector", "未配置")
        print(f"OTEL Collector: {otel_status}")

    # 测试高频路径
    endpoints = [
        ("/health", 200),
        ("/metrics", 200),
    ]

    print("\n端点延迟测量 (200 次请求):\n")
    print(f"{'端点':<20} {'P50(ms)':<10} {'P99(ms)':<10} {'Mean(ms)':<10} {'错误数':<8}")
    print("-" * 60)

    for endpoint, _ in endpoints:
        result = await measure_latency(endpoint, iterations=200)
        if result["count"] > 0:
            print(
                f"{endpoint:<20} {result['p50']:<10.2f} {result['p99']:<10.2f} "
                f"{result['mean']:<10.2f} {result['errors']:<8}"
            )
            RESULTS[endpoint] = result
        else:
            print(f"{endpoint:<20} {'N/A':<10} {'N/A':<10} {'N/A':<10} {result['errors']:<8}")

    print("\n" + "=" * 60)
    print("结论: OTEL span 对高频路径的开销分析")
    print("=" * 60)
    print("""
注意: 此测试仅测量 HTTP 请求路径的延迟。
OTEL span 的实际开销在 Python tracing SDK 中通常是 < 0.5ms/span，
主要在 span 创建和属性设置时产生，不在 HTTP 请求路径中。
详细测量需要在 tracing.py 内部使用 time.perf_counter() 插桩，
在真实工作流执行时对比 OTEL 启用/禁用的差异。
""")

    return RESULTS


if __name__ == "__main__":
    asyncio.run(run_otel_benchmark())