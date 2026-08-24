# Xj-engine 优化空间与调整方案

> 本文档只列优化方向，不代表已采纳。每项包含：现状、问题、调整方案、建议优先级。

## 1. 测试体系缺失

- 现状：目前只有 `py_compile` 和手工 import 验证，没有自动化测试。
- 问题：内核契约、状态流转、审计、签名等改动容易回归。
- 方案：
  - 增加 `tests/`，覆盖：
    - `et_contract` payload 校验
    - `kernel.et` 各 op 成功/拒绝/阻断路径
    - `et_sign` 签名/验签
    - `state_store` 乐观锁冲突
    - `audit` 写入/查询
  - 接入 `pytest`
- 优先级：高

## 2. `skills.py` 仍是 stub

- 现状：`skills.py` 只是占位，原测试技能服务未包含。
- 问题：如果规则/闸需要测试技能能力，会直接不可用。
- 方案：
  - 将测试技能服务按接口抽象后移入 `Xj-engine`，或
  - 提供 `TestSkillProvider` 协议，由外部平台注入实现
- 优先级：高

## 3. `kernel.py` 过大，职责偏重

- 现状：`kernel.py` 约 900+ 行，包含校验、执行、计量、签发、异常等。
- 问题：后续扩展困难，可读性和可测试性下降。
- 方案：
  - 拆分为：
    - `kernel.py`：入口调度
    - `executor.py`：op 执行链
    - `metering.py`：token/cost 计量
    - `signing.py`：签发/验签
    - `errors.py`：异常分类
- 优先级：中

## 4. 数据库/审计/状态存储绑定 SQLAlchemy SQLite

- 现状：`database.py` 默认 SQLite，`audit.py` / `state_store.py` 依赖本地 `Base`。
- 问题：换 PostgreSQL / MySQL / 内存库时仍要改内部实现。
- 方案：
  - 增加 `StorageProvider` 抽象
  - 支持 `XJ_ENGINE_DB_URL` 指向任意 SQLAlchemy 数据库
  - 审计和状态存储通过 provider 注入，而不是直接 import `database`
- 优先级：中

## 5. 默认密钥策略对本地开发不友好

- 现状：`AGENT_ENGINE_SECRET` 未设置时 `et_sign` 会报错。
- 问题：本地首次使用门槛高。
- 方案：
  - 本地开发时若未设置，自动生成并保存到 `~/.xj-engine/secret`
  - 生产环境仍强制环境变量
- 优先级：中

## 6. CLI 功能太薄

- 现状：只有 `health` 和 `run`。
- 问题：Agent/规则直接调用时缺少常用操作。
- 方案：
  - 增加：
    - `xj-engine verify --payload ...`
    - `xj-engine audit --trace-id ...`
    - `xj-engine state get/transition ...`
    - `xj-engine sign --artifact ...`
- 优先级：中

## 7. 缺少配置文件和示例

- 现状：只有 `.env.example`，没有 `config.yaml` 示例。
- 问题：复杂部署时环境变量管理混乱。
- 方案：
  - 增加 `config.example.yaml`
  - 支持 `XJ_ENGINE_CONFIG` 指向配置文件
  - 配置项：数据库、日志级别、审计开关、密钥来源
- 优先级：低

## 8. 没有插件/扩展机制

- 现状：内核 op 和校验逻辑固定。
- 问题：外部想新增 op 或自定义校验必须改内核。
- 方案：
  - 参考 `etl-engine-standalone` 的 `Deps` / `Stage` 模式
  - 增加 `EnginePlugin` 协议：注册自定义 op、hook、校验器
- 优先级：中

## 9. `engine_health` 仍检测 agent-harness 平台

- 现状：`engine_health.json` 检测 `http://127.0.0.1:8001/api`，即平台 API。
- 问题：不能证明 `Xj-engine` 本身可用。
- 方案：
  - 新增 `xj-engine health` 作为引擎健康检查
  - 将 `engine_health` spec 改为同时检查：
    - `xj-engine health`
    - 平台 API（可选）
- 优先级：高

## 10. 规则/闸仍大量调用 `backend/engine`

- 现状：`Xj-rules` 和本机规则里仍写 `backend/engine`。
- 问题：新用户/新环境不知道引擎是 `Xj-engine`。
- 方案：
  - 将规则/闸中的 `backend/engine` 调用统一改为：
    - `from xj_engine.kernel import et`
    - 或 `xj-engine ...`
  - 保留 `agent-harness` 作为平台可选项
- 优先级：高

## 11. 缺少版本管理与发布流程

- 现状：没有 `CHANGELOG.md` / 版本号语义。
- 问题：用户不知道当前版本和升级影响。
- 方案：
  - 使用 `0.x.y` 语义化版本
  - 每次变更更新 `CHANGELOG.md`
  - 增加 GitHub Release 或自动发布
- 优先级：低

## 12. 缺少使用示例

- 现状：README 只有最小调用方式。
- 问题：新用户不知道 payload 怎么写。
- 方案：
  - 增加 `examples/`
  - 提供：
    - `example_ingest_payload.json`
    - `example_verify_payload.json`
    - `example_audit_query.py`
- 优先级：低
