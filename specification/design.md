# personal-task-station 本轮设计说明

## 1. 架构边界

本轮聚焦任务管理主线与部署交付。保留既有财务模块，但新开发只围绕：
- `server/routers/tasks.py`
- `server/services/tasks.py`
- `shared/models.py` / `shared/schemas.py` / `shared/enums.py`
- `client/api_client.py`
- `client/main_window.py`
- `client/widgets/calendar_widget.py`
- `client/dialogs/*`
- `client/views/connection_view.py`
- `skills/task_skill.py`
- `Dockerfile` / `docker-compose.yml` / `scripts/*`
- 相关测试与文档

## 2. 服务端设计

### 2.1 分层

- Router：FastAPI 路由负责参数解析、认证依赖、HTTP 状态码。
- Service：封装任务、子项、状态历史、日历聚合的业务规则。
- Model：SQLAlchemy ORM，SQLite 默认持久化。
- Schema：Pydantic DTO，客户端/skill/API 共用。

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
- 按 `scheduled_date`/`start_time`/`due_time` 归入日期。
- 统计总数、未完成、进行中、完成、取消、最高优先级、是否置顶。
- 输出稳定 DTO，供客户端月视图渲染。

## 3. 客户端设计

### 3.1 API Client

`ApiClient` 负责：
- 保存 base_url、api_key、证书配置。
- 健康检查/连接测试。
- 任务 CRUD、状态变更、子项操作、日历聚合请求。
- 将 HTTP 错误转化为用户可见错误。

### 3.2 主窗口与任务视图

主窗口提供：
- 连接配置入口。
- 任务列表与过滤器。
- 新增/编辑/删除/状态切换入口。
- 日历区域。

### 3.3 日历 Widget

日历 Widget 维护日期标记数据，不直接访问数据库；通过 API Client 或 ViewModel 获取聚合结果。点击日期发出信号，打开日期任务弹窗。

### 3.4 日期任务弹窗与任务编辑

日期弹窗展示当日任务摘要，支持：
- 快速新增（默认 scheduled_date 为当前日期）
- 编辑任务
- 状态切换
- 打开详情

任务编辑弹窗处理标题、描述、日期、时间、状态、优先级、标签、备注与子项。

## 4. 部署设计

### 4.1 Docker

`Dockerfile` 使用 Python slim 基础镜像，安装项目运行依赖，暴露服务端端口。entrypoint 负责初始化运行目录、数据库路径和启动 uvicorn。

`docker-compose.yml` 提供本地可用服务：
- 挂载数据卷。
- 注入 API Key 与数据库路径。
- 暴露端口。
- 健康检查。

### 4.2 Linux 脚本

Linux 部署脚本采用 bash，职责：
- 校验 docker/compose 可用。
- 创建数据目录和 `.env`。
- 构建镜像并启动服务。
- 输出健康检查命令。

Linux 打包脚本生成源码/客户端可执行分发包；如 PyInstaller 可用则生成二进制，否则生成包含 venv 安装说明的 tarball。

### 4.3 Windows 脚本

Windows 脚本采用 PowerShell：
- 创建 venv。
- 安装依赖与 PyInstaller。
- 以 `personal_task_station.client.main` 为入口打包客户端。
- 输出 dist 目录与启动说明。

## 5. 测试策略

- Unit：任务 service、日历聚合、schema 校验。
- Integration：任务 API CRUD、状态历史、子项、日历接口。
- UI：日历 widget 标记与日期点击、任务弹窗基本字段、连接配置。
- Deploy：Docker/Compose 文件静态检查、脚本语法检查；如当前环境支持 Docker，则执行 build/up/health smoke。
- Kimi：独立复核任务主流程、日历接口/UI、Docker 与 Linux/Windows 脚本自洽性。
