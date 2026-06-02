# Security Hardening Spec

## Why

基于 FastAPI 安全最佳实践对 agentManager 项目进行系统性安全审计，发现多个安全漏洞和配置缺陷，包括无认证保护、内部错误信息泄露、SQL 注入风险、安全头缺失、日志凭据泄露等问题。需要按优先级逐步修复以确保生产部署安全。

## What Changes

- 为 FastAPI 应用添加可配置的认证依赖（API Key / Bearer Token）
- 修复 API 端点内部错误信息泄露（`detail=str(e)` → 通用错误消息）
- 禁用或保护生产环境的 OpenAPI 文档端点（`/docs`, `/redoc`, `/openapi.json`）
- 添加安全响应头中间件（X-Content-Type-Options, X-Frame-Options, Referrer-Policy）
- 修复 `vector_backend.py` 中 SQLite f-string SQL 注入风险
- 修复 `redis_stream.py` 中 Redis URL 日志凭据泄露
- 保护 `/metrics` 端点（认证或可配置禁用）
- 添加请求体大小限制中间件
- 添加 TrustedHostMiddleware 配置
- 强化 `docker-compose.yml` 默认凭据安全

## Impact

- Affected specs: API 安全性、认证授权、日志安全、数据库安全
- Affected code:
  - `agentManager/api.py` — 认证、安全头、错误处理、文档端点
  - `agentManager/memory/vector_backend.py` — SQL 注入修复
  - `agentManager/engine/event_bus/redis_stream.py` — 日志凭据泄露
  - `agentManager/config/settings.py` — 安全配置扩展
  - `docker-compose.yml` — 默认凭据强化
  - `tests/unit/test_api.py` — 测试更新

## ADDED Requirements

### Requirement: API 认证保护

系统 SHALL 提供可配置的 API 认证机制，通过环境变量 `API_AUTH_ENABLED`（默认 `false`）和 `API_AUTH_TOKEN` 控制。当认证启用时，所有端点（除 `/health` 外）MUST 要求 `Authorization: Bearer <token>` 头。

#### Scenario: 认证启用时未携带 Token

- **WHEN** `API_AUTH_ENABLED=true` 且请求未携带 `Authorization` 头
- **THEN** 返回 HTTP 401 Unauthorized

#### Scenario: 认证启用时携带正确 Token

- **WHEN** `API_AUTH_ENABLED=true` 且请求携带有效 Bearer Token
- **THEN** 正常处理请求

#### Scenario: 认证禁用时

- **WHEN** `API_AUTH_ENABLED=false`（默认）
- **THEN** 所有端点无需认证即可访问（向后兼容）

### Requirement: 生产环境禁用 OpenAPI 文档

系统 SHALL 支持通过环境变量 `DOCS_ENABLED`（默认 `true`）控制 OpenAPI 文档端点。当 `DOCS_ENABLED=false` 时，`/docs`、`/redoc`、`/openapi.json` MUST 返回 404。

#### Scenario: 生产环境禁用文档

- **WHEN** `DOCS_ENABLED=false`
- **THEN** `/docs`、`/redoc`、`/openapi.json` 返回 404

#### Scenario: 开发环境启用文档

- **WHEN** `DOCS_ENABLED=true`（默认）
- **THEN** 文档端点正常可用

### Requirement: 安全响应头

系统 SHALL 在所有 HTTP 响应中添加以下安全头：
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`

#### Scenario: 所有响应包含安全头

- **WHEN** 客户端发送任何 HTTP 请求
- **THEN** 响应包含上述三个安全头

### Requirement: 内部错误信息不泄露

系统 MUST NOT 在 API 错误响应中返回内部异常详情。所有未预期异常 MUST 返回通用错误消息，详细信息仅记录在服务端日志中。

#### Scenario: 内部异常返回通用消息

- **WHEN** 服务端处理请求时抛出未预期异常
- **THEN** 客户端收到 `"detail": "Internal server error"` 而非异常堆栈

### Requirement: SQLite 表名参数化

`vector_backend.py` 中的 SQLite 查询 MUST NOT 使用 f-string 拼接表名。MUST 在构造函数中验证 `table_name` 仅包含安全字符。

#### Scenario: 恶意表名被拒绝

- **WHEN** 构造 `SQLiteVectorSearchBackend` 时传入包含 SQL 特殊字符的 `table_name`
- **THEN** 抛出 `ValueError`

### Requirement: 日志中不泄露凭据

系统 MUST NOT 在日志中输出包含凭据的连接 URL。MUST 使用 `_mask_url()` 或等效方法遮蔽凭据。

#### Scenario: Redis 连接日志遮蔽凭据

- **WHEN** Redis 事件总线连接成功
- **THEN** 日志中的 URL 不包含密码明文

### Requirement: Metrics 端点保护

系统 SHALL 支持通过环境变量 `METRICS_ENABLED`（默认 `true`）控制 `/metrics` 端点。当认证启用时，`/metrics` 端点 MUST 同样要求认证。

#### Scenario: 认证启用时 Metrics 端点受保护

- **WHEN** `API_AUTH_ENABLED=true` 且请求 `/metrics` 未携带有效 Token
- **THEN** 返回 HTTP 401

### Requirement: 请求体大小限制

系统 SHALL 限制请求体大小，默认最大 1MB，可通过 `MAX_REQUEST_BODY_SIZE` 环境变量配置。

#### Scenario: 超大请求体被拒绝

- **WHEN** 请求体超过配置的最大大小
- **THEN** 返回 HTTP 413 Payload Too Large

### Requirement: Host 头验证

系统 SHALL 支持通过 `ALLOWED_HOSTS` 环境变量配置 TrustedHostMiddleware。当 `ALLOWED_HOSTS` 未设置时，不启用 Host 验证（保持向后兼容）。

#### Scenario: 配置了允许的 Host

- **WHEN** `ALLOWED_HOSTS=api.example.com` 且请求 Host 为 `api.example.com`
- **THEN** 正常处理请求

#### Scenario: 不允许的 Host 被拒绝

- **WHEN** `ALLOWED_HOSTS=api.example.com` 且请求 Host 为 `evil.com`
- **THEN** 返回 HTTP 400 Bad Request

## MODIFIED Requirements

### Requirement: docker-compose.yml 默认凭据安全

开发 compose 文件中的默认凭据 MUST 使用明显非生产值并添加注释警告。`MINIO_SECRET_KEY` 默认值 MUST NOT 为 `minioadmin`。

## REMOVED Requirements

无移除的需求。
