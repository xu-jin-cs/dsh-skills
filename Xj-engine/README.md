# Xj-engine

Xj-rules 配套的轻量、即插即用文档 ETL 引擎：语义分片 + 清洗 + 向量化入库 + 双索引（向量 / BM25），
规则全部外置为 YAML 唯一真源。独立发行版，不依赖任何私有注册表或历史平台。

## 特性

- **六步入库链**：`validate → parse → clean → chunk → write → post`（13 格式白名单，pdf 显式拦截）
- **语义优先分片**：max_token=1200 / overlap=200，表格/代码/幻灯片结构保护，sliding_window 兜底
- **幂等写入**：chunk_id 内容哈希（MD5→int64）+ LanceDB `merge_insert` 同 ID 覆写，重试不膨胀
- **文档级聚合锚**：`meta.parent_chunk_id`（首 chunk 锚定），支持"按句找文、拼回整文件"（重组契约为 opt-in，见 `docs/reassembly_contract.md`）
- **双索引**：LanceDB 向量（BAAI/bge-m3 1024 维，**只写模型名，首跑自动拉取权重**）+ BM25（重建节流）
- **规则即数据**：8 张 `contract_rules/*.yaml` 唯一真源，执行器零字面量，缺键即 `RuleMissingError`
- **三分类异常**：resource(3×30s 重试) / content(1 次) / business(直接拒绝)，落队可自愈
- **三方对账**：SQLite ↔ LanceDB ↔ outbox reconcile，孤儿向量回补自愈

## 快速开始

```bash
# 核心引擎
pip install -r requirements.txt

# 可选：使用 middleware/ 时再安装
pip install -r requirements-mq.txt

PYTHONPATH=. python3 - <<'PY'
import hashlib, uuid
from engine.kernel import etl_engine

p = "/path/to/your.md"
r = etl_engine({
    "op": "general_ingest",
    "trace_id": uuid.uuid4().hex[:16],
    "artifact": {"tenant_id": "default", "source_path": p,
                 "file_md5": hashlib.md5(open(p, "rb").read()).hexdigest()},
    "doc_meta": {"file_suffix": "md"},
})
print(r["code"], r["detail"].get("chunk_ids"))
PY
```

> 首次运行自动下载 `BAAI/bge-m3`（约 2.2GB）；离线环境设 `HF_HUB_OFFLINE=1`。
> 数据落 `./data/`（LanceDB / SQLite / BM25 / tmp），路径在 `engine/contract_rules/storage.yaml` 可调。
> 环境变量示例见 `.env.example`；生产环境请通过环境变量注入账号密码，禁止写死在代码/文档中。

## 内核 op

| op | 说明 |
|---|---|
| `general_ingest` | 单文件入库（断点续跑 + 知情幂等重放） |
| `general_delete` | 按 doc_unique_ids 删（向量+SQLite+记账） |
| `general_reconcile` | 三方对账（`artifact` 固定 `{}`） |

出参 `code` 四态：`success / reject / block / error`。

## 目录结构

```
engine/               # 内核（kernel/contract/rules_loader/outbox/embed）+ general 执行器
engine/contract_rules/  # 8 张规则表（唯一真源，CI 可机械断言）
middleware/           # RabbitMQ/Redis/MinIO 基础封装（etl_mq.py / minio_ops.py / prometheus_rules）
docs/                 # 契约三份 + PAINPOINTS.md（规则↔痛点地图，Why 章节）
config.yaml           # 中间件与部署参数清单（唯一配置入口）
.env.example          # 环境变量示例（不含真实凭据）
```

## 中间件（可选异步化层）

RabbitMQ（direct 交换机 + 主队列 TTL 30min + DLQ）/ Redis（幂等键 `SET NX EX 7d`）/
MinIO（原始对象对账基准源）/ Prometheus（积压告警三件套）。

本仓库包含：

- `middleware/etl_mq.py`：RabbitMQ 发布端基础封装
- `middleware/minio_ops.py`：MinIO 上传/下载/删除封装
- `middleware/prometheus_rules/etl_engine.yaml`：告警规则示例

原消费进程/巡检进程依赖历史业务后端（任务模型 / 后端 API），
**已从 standalone 包移除**。接入时按你的任务存储适配 `task_id ↔ 任务模型` 查询接口即可。

## 依赖注入（自定义 DB / Store / Stage）

内核默认使用 `engine/contract_rules/storage.yaml` 自动构造默认 SQLite / LanceDB 实例，
并使用 `general_stages` 默认 stage 注册表。如果你需要替换存储、新增/替换步骤、自定义文档 ID 或异常分类，
可以通过 `Deps` 注入，内核不再自己锁死实例构建：

```python
from engine.deps import Deps
from engine.kernel import etl_engine
from engine.contract import Stage

# 方式一：直接传入已构造实例
deps = Deps(db=my_db, store=my_store)
r = etl_engine(payload, deps=deps)

# 方式二：传入无参工厂
deps = Deps(db_factory=lambda: MyDB(), store_factory=lambda: MyStore())
r = etl_engine(payload, deps=deps)

# 方式三：自定义 stage 注册表、文档 ID、异常分类
class MyStage(Stage):
    def __call__(self, ctx, artifact):
        return {"custom": True}

deps = Deps(
    stages={"my_stage": MyStage()},
    doc_id_factory=lambda tenant_id, file_md5: f"{tenant_id}-{file_md5[:8]}",
    exception_classifier=lambda exc: {"queue": "etl_general_failed", "backoff_seconds": 0, "max_retries": 1},
)
r = etl_engine(payload, deps=deps)
```

DB / Store / Stage 只需满足 `engine/deps.py` 与 `engine/contract.py` 中的协议；
不传 `deps` 时行为与旧版完全一致。

## 上传必看：Git 发布前兼容性检查

> 以后任何项目上传到 Git 前，必须先按此清单检查；不通过禁止上传。

### 1. 路径必须可移植

- [ ] 禁止出现本机绝对路径：`/Users/<用户名>`、`C:\Users\...`、`/home/...`
- [ ] 路径统一使用相对路径 `./data/...`、`$HOME`、`Path.home()` 或环境变量
- [ ] 代码、文档、配置中不得出现私人目录名

### 2. 凭据必须清零

- [ ] 不得出现真实 `password` / `secret` / `token` / `api_key` / 私钥
- [ ] 已泄露的账号密码必须删除
- [ ] 新增 `.env.example`，真实配置通过环境变量注入

### 3. 私有依赖必须剥离

- [ ] 不得 import 外部私有项目模块，例如 `backend.*`、`etl.common.*`
- [ ] 不得出现内部私有项目名：`agent-harness`、`retro-skills-registry`、`Xj-rules`、个人名等
- [ ] 仓库必须能独立 `clone` 后按 README 安装并运行

### 4. 无关文件必须忽略

- [ ] `data/`、`__pycache__/`、`*.pyc`、`.DS_Store`、`node_modules/`、`*.tgz`、`*.zip` 不入库
- [ ] 数据库文件、模型权重、大体积临时文件不入库

### 5. 上传前必须执行校验

```bash
# 绝对路径扫描：应无命中
grep -RIn --exclude-dir=.git --exclude-dir=data -E '/Users/|C:\\Users|/home/' .

# 凭据扫描：不应出现真实密码/密钥
grep -RIn --exclude-dir=.git -iE 'password|secret|token|api[_-]?key' .

# 语法/配置校验
python3 -m py_compile $(find . -name '*.py' -not -path './.git/*')
```

- [ ] Python 语法检查通过
- [ ] YAML / JSON 解析通过
- [ ] 在全新目录 `git clone` 后，按 README 跑通最小示例

## License

**PolyForm Noncommercial License 1.0.0** — 可自由学习、研究、自用与二次开发；
**禁止商用**（含 SaaS、付费支持、商业再分发）。衍生分发必须保留 LICENSE 头部
`Required Notice` 声明。商业授权请联系作者。
