# 审计写入性能基准测试报告

**测试日期：** 2026-06-02
**任务：** M4-F.3.2 - 测量审计写入对关键路径的性能影响
**样本数：** 每种模式 1000 次

## 测试方法

该基准直接调用 `record_audit_event()`。
`disabled` 模式通过临时空 sink 集合测量函数框架开销。
`log` 模式使用真实 logger。
`db` 和 `object_storage` 模式使用 mock repository/object store，
避免结果依赖外部 PostgreSQL 或 S3 网络状态。

## 结果

| 模式 | P50 (ms/event) | P99 (ms/event) | Mean (ms/event) | 阈值 | 结果 |
|------|----------------|----------------|-----------------|------|------|
| disabled | 0.0097 | 0.0574 | 0.0119 | < 0.1 | PASS |
| log | 0.0110 | 0.0504 | 0.0140 | < 0.1 | PASS |
| db | 0.0437 | 0.5462 | 0.1039 | < 5.0 | PASS |
| object_storage | 0.0613 | 0.3698 | 0.0766 | < 50.0 | PASS |

## 结论

验收阈值：log sink P99 < 0.1ms/event，db sink P99 < 5ms/event，
object_storage sink P99 < 50ms/event。
db/object_storage 的本地结果代表框架映射与调用开销；
真实服务延迟需在部署环境继续观测。
