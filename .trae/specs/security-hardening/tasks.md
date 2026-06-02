# Tasks

- [x] Task 1: 修复 API 内部错误信息泄露
  - [x] SubTask 1.1: 将 `api.py` 中 `create_task`、`complete_task`、`fail_task` 的 `detail=str(e)` 替换为 `detail="Internal server error"`，保留 `logger.error` 日志
  - [x] SubTask 1.2: 确认所有端点的异常处理不泄露内部信息

- [x] Task 2: 添加安全响应头中间件
  - [x] SubTask 2.1: 在 `api.py` 中添加中间件，为所有响应设置 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: strict-origin-when-cross-origin`

- [x] Task 3: 生产环境禁用 OpenAPI 文档端点
  - [x] SubTask 3.1: 读取 `DOCS_ENABLED` 环境变量，当为 `false` 时设置 `docs_url=None`、`redoc_url=None`、`openapi_url=None`
  - [x] SubTask 3.2: 在 `.env.prod.example` 中添加 `DOCS_ENABLED=false`

- [x] Task 4: 添加可配置的 API 认证
  - [x] SubTask 4.1: 在 `config/settings.py` 中添加 `get_auth_settings()` 函数，读取 `API_AUTH_ENABLED` 和 `API_AUTH_TOKEN`
  - [x] SubTask 4.2: 在 `api.py` 中创建 `verify_token` 依赖函数，当 `API_AUTH_ENABLED=true` 时验证 `Authorization: Bearer <token>`
  - [x] SubTask 4.3: 将认证依赖应用到所有端点（`/health` 除外），`/metrics` 端点同样受保护
  - [x] SubTask 4.4: 在 `.env.prod.example` 中添加 `API_AUTH_ENABLED=true` 和 `API_AUTH_TOKEN` 配置项

- [x] Task 5: 修复 SQLite f-string SQL 注入风险
  - [x] SubTask 5.1: 在 `SQLiteVectorSearchBackend.__init__` 中添加 `table_name` 验证（仅允许字母、数字、下划线）
  - [x] SubTask 5.2: 将 f-string SQL 替换为参数化查询或验证后的安全拼接

- [x] Task 6: 修复 Redis URL 日志凭据泄露
  - [x] SubTask 6.1: 在 `redis_stream.py` 中导入或实现 `_mask_url`，替换 `logger.info(f"Connected to Redis at {self.redis_url}")`

- [x] Task 7: 添加请求体大小限制
  - [x] SubTask 7.1: 在 `api.py` 中添加中间件，检查 `Content-Length` 头，超过限制返回 413
  - [x] SubTask 7.2: 在 `config/settings.py` 中添加 `MAX_REQUEST_BODY_SIZE` 配置（默认 1MB）

- [x] Task 8: 添加 Host 头验证
  - [x] SubTask 8.1: 读取 `ALLOWED_HOSTS` 环境变量，当设置时添加 `TrustedHostMiddleware`
  - [x] SubTask 8.2: 在 `.env.prod.example` 中添加 `ALLOWED_HOSTS` 配置项

- [x] Task 9: 强化 docker-compose.yml 默认凭据
  - [x] SubTask 9.1: 将 `POSTGRES_PASSWORD` 默认值改为 `dev_only_change_me`，添加注释警告
  - [x] SubTask 9.2: 将 `MINIO_SECRET_KEY` 默认值改为 `dev_only_change_me`，添加注释警告

- [x] Task 10: 更新测试
  - [x] SubTask 10.1: 为认证依赖添加单元测试（启用/禁用/无效 token）
  - [x] SubTask 10.2: 为安全头中间件添加测试
  - [x] SubTask 10.3: 为文档禁用添加测试
  - [x] SubTask 10.4: 为请求体大小限制添加测试
  - [x] SubTask 10.5: 为 SQLite 表名验证添加测试
  - [x] SubTask 10.6: 为 Host 验证添加测试

# Task Dependencies

- [Task 4] depends on [Task 3] (认证依赖需在文档禁用后应用)
- [Task 10] depends on [Task 1-9] (测试依赖所有功能实现)
- [Task 1, 2, 5, 6] 可并行执行（互不依赖）
- [Task 3, 7, 8] 可并行执行（互不依赖）
