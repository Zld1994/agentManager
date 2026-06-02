# OTEL Span 性能基准测试报告

**测试日期：** 2026-06-02
**任务：** M4-F.3.1 - 测量 OTEL span 对关键路径的性能影响
**样本数：** 每个路径 1000 次

## 测试方法

该基准在本地进程内对比 tracing disabled 与 tracing enabled 两种状态。
enabled 状态使用内存 tracer，不连接 OTLP Collector。
因此测量的是同步 span 创建和属性设置开销，不包含网络导出耗时。

## 结果

| 路径 | Disabled P50 (ms) | Disabled P99 (ms) | Enabled P50 (ms) | Enabled P99 (ms) | Overhead P50 (ms) | Overhead P99 (ms) | 阈值 |
|------|-------------------|-------------------|------------------|------------------|-------------------|-------------------|------|
| scheduler.add_task | 0.0029 | 0.0043 | 0.0035 | 0.0066 | 0.0006 | 0.0023 | PASS |
| state_manager.transition+get_state | 0.0053 | 0.0248 | 0.0062 | 0.0071 | 0.0009 | 0.0000 | PASS |
| task_executor.run_task | 0.6396 | 3.5169 | 0.6427 | 2.4311 | 0.0031 | 0.0000 | PASS |

## 结论

验收阈值为 P99 开销 < 1ms/span。上表中所有路径均按该阈值判定。
该测试覆盖 scheduler、state_manager、task_executor 的真实 instrumentation 入口。
OTLP exporter 的异步批量导出不计入同步关键路径。
