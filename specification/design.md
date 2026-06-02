# personal-task-station 本轮设计说明

## 1. 架构边界

本轮聚焦任务管理主线与生产就绪部署交付。保留既有财务/邮件模块，但新开发只围绕：
- `server/routers/tasks.py`
- `server/services/tasks.py`
- `shared/models.py` / `shared/schemas.py` / `shared/enums.py`
- `client/api_client.py`
- `client/main_window.py`
- `client/widgets/calendar_widget.py`
- `client/dialogs/*`
- `client/views/connection_view.py`
- `client/views/finance_view.py`
- `server/routers/billing.py` / `server/services/billing.py`
- `skills/finance_skill.py`
- `skills/task_skill.py`
- `Dockerfile` / `docker-compose.yml` / `scripts/*`
- `.env.example` / `deploy/systemd/*`
- 相关测试与文档

## 2. 服务端设计

### 2.1 分层

- Router：FastAPI 路由负责参数解析、认证依赖、HTTP 状态码。
- Service：封装任务、子项、状态历史、日历聚合的业务规则。
- Model：SQLAlchemy ORM，SQLite 默认持久化。
- Schema：Pydantic DTO，客户端/skill/API 共用；任务 DTO 在输入层兼容 `scheduled_date`/`task_date`、`start_time`/`start_at`、`due_time`/`due_at`、`notes`/`note`，并将优先级标签或数字字符串规范化为 `1`-`5` 整数。

### 2.2 任务状态与历史

所有状态变更必须通过 service 完成：
1. 校验目标任务存在。
2. 写入任务当前状态与更新时间。
3. 写入 `TaskStatusHistory`，包含 from/to/status note/timestamp。
4. 提交事务。

### 2.3 子项联动

子项具备独立完成状态与排序字段。删除/编辑/重排只影响所属任务。可选规则：当所有子项完成时允许客户端快速将父任务改为完成，但服务端不强制自动完成，避免误操作。

### 2.4 日历聚合

新增或完善日历聚合服务函数：
- 输入 `start_date`、`end_date` 或 year/month。
- 查询区间内所有任务。
- 按公开字段 `scheduled_date`/`start_time`/`due_time`（兼容内部 `task_date`/`start_at`/`due_at`）归入日期。
- 统计总数、未完成、进行中、完成、取消、最高优先级、是否置顶。
- 输出稳定 DTO，供客户端月视图渲染。

## 3. 客户端设计

### 3.1 API Client

`ApiClient` 负责：
- 保存 base_url、api_key、证书配置。
- 健康检查/连接测试。
- 任务 CRUD、状态变更、子项操作、日历聚合请求。
- 财务 CSV 导入、月度汇总、交易列表、重复项查询、撤销合并、重新分析请求。
- 将 HTTP 错误转化为用户可见错误。

### 3.2 主窗口与任务视图

主窗口提供：
- 连接配置入口。
- 任务列表与过滤器。
- 新增/编辑/删除/状态切换入口。
- 日历区域。
- Finance tab，承载手动导入、摘要、交易列表和重复项操作。

### 3.3 日历 Widget

日历 Widget 维护日期标记数据，不直接访问数据库；通过 API Client 或 ViewModel 获取聚合结果。点击日期发出信号，打开日期任务弹窗。

### 3.4 日期任务弹窗与任务编辑

日期弹窗展示当日任务摘要，支持：
- 快速新增（默认 `scheduled_date`/`task_date` 为当前日期）
- 编辑任务
- 状态切换
- 打开详情

任务编辑弹窗处理标题、描述、日期、时间、状态、优先级、标签、备注与子项。

## 4. 财务/交易 MVP 设计

### 4.1 CSV-first 导入边界

财务主路径使用 `POST /billing/import` 接收 CSV/TSV-like 文件与 `source_name`。`BillingService` 解析表格后写入 `BillImportJob`、`RawTransaction`、`NormalizedTransaction`，并通过字段别名兼容常见英文/中文列名。导入失败会保留失败 job、错误信息和审计日志；成功导入后重建 active merged transaction 视图。

邮件导入、provider parser、Alipay API 等遗留/扩展能力不作为桌面 MVP 主路径；它们可以复用同一 normalized transaction 模型，但文档必须明确“可选/实验”，避免把不稳定自动化描述为已完成。

### 4.2 分类、汇总与去重

- 分类优先使用配置的 classifier；失败时自动回退 `RuleBasedClassifier`。
- 去重以外部订单号优先，否则使用方向、日期、绝对金额、规范化商户构造 dedupe key。
- `rebuild_merged_transactions` 为每个 dedupe group 创建 active merged transaction；重复 group 标记成员为 `merged`。
- `undo_merge` 将选中合并组设为 inactive、成员标记为 `undone`，随后重建 active 视图，确保月度汇总反映撤销结果。
- `monthly_summary` 以 active merged transaction 计算收入、支出、分类/来源/账户汇总、重复项和大额异常。

### 4.3 桌面 Finance tab

Finance tab 连接同一 `ServerApiClient`，提供：
- month selector 与 Load summary。
- source name 输入和 Import CSV 文件选择。
- Reanalyze 重新分类/去重。
- 月度摘要、分类表、交易列表、重复项表。
- Undo selected duplicate，对选中的重复合并调用 `/billing/merged/{id}/undo` 并刷新汇总。

## 5. 部署与访问设计

### 5.1 访问边界

默认设计是 personal/small-team service，而不是直接公网服务：
- 服务端默认绑定 `127.0.0.1:8000`，供同机客户端、skill wrapper、curl/smoke 使用。
- LAN/私有 VPN 通过 `PTS_HOST`/`PTS_PORT` 切换到 `0.0.0.0` 或指定网卡 IP，并由操作者用防火墙/VPN 限制来源。
- 公网访问推荐外置反向代理或隧道终止 HTTPS；应用本身不建议裸露到公网。
- API key 是应用层必需控制；`/health` 保持无认证，便于 systemd/Docker/运维探活。
- 直接 HTTPS/mTLS 能力保留在 `PTS_SSL_CERTFILE`、`PTS_SSL_KEYFILE`、`PTS_SSL_CAFILE` 中，作为高级/可选部署。

### 5.2 Host-based 服务（主路径）

host 启动脚本负责：
- 读取或创建 `.env.host`。
- 生成/保留 `PTS_API_KEY`，避免覆盖既有敏感配置。
- 创建 `PTS_DATA_DIR` 并设置 SQLite `PTS_DATABASE_URL`。
- 在 `.venv` 缺失服务端入口时安装 `.[server]`。
- 有 Alembic 时执行 `alembic upgrade head`。
- 通过 `pts-server` 使用 `AppSettings` 启动服务。

systemd user service 模板只引用已准备好的 `.env.host` 和 `.venv/bin/pts-server`，避免在 service 内执行安装逻辑，降低启动时副作用。

smoke test 脚本使用 `curl` 验证：
1. `GET /health`。
2. 认证 `GET /tasks`。
3. 认证 `POST /tasks` 创建临时任务。
4. 认证 `GET /tasks/{id}` 校验标题。
5. 认证 `DELETE /tasks/{id}` 清理。

### 5.3 Docker Compose（备用路径）

`Dockerfile` 使用 Python slim 基础镜像，安装项目运行依赖，暴露服务端端口。entrypoint 负责初始化运行目录、数据库路径和启动 uvicorn。

`docker-compose.yml` 提供本地可用服务：
- 挂载数据卷。
- 注入 API Key 与数据库路径。
- 暴露端口。
- 健康检查。

Docker entrypoint 与 host 脚本保持同一配置模型：`PTS_API_KEY`、`PTS_HOST`、`PTS_PORT`、`PTS_DATABASE_URL`、可选 TLS 路径。

### 5.4 Linux 打包脚本

Docker 部署脚本采用 bash，职责：
- 校验 docker/compose 可用。
- 创建数据目录和 `.env`。
- 构建镜像并启动服务。
- 输出 health/API smoke 命令。

Linux 打包脚本生成源码/客户端可执行分发包；如 PyInstaller 可用则生成二进制，否则生成包含 venv 安装说明的 tarball。

### 5.5 Windows 脚本

Windows 脚本采用 PowerShell：
- 创建 venv。
- 安装依赖与 PyInstaller。
- 以 `personal_task_station.client.main` 为入口打包客户端。
- 输出 dist 目录与启动说明。

## 6. 测试策略

- Unit：任务 service、日历聚合、schema 校验、billing CSV pipeline/undo。
- Integration：任务 API CRUD、状态历史、子项、日历接口、billing import/summary/duplicates/undo。
- UI：日历 widget 标记与日期点击、任务弹窗基本字段、连接配置、Finance tab 摘要/重复项/撤销操作。
- Deploy：host/Docker/systemd/env/smoke 资产静态检查、脚本语法检查、dry-run；如当前环境支持服务启动，则执行 API smoke。
- Docs：README/DEPLOYMENT/spec 与实际命令、默认 host/port、HTTP/HTTPS 客户端限制保持一致。
