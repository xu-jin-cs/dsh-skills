# Xj-engine

`Xj-rules` 配套的独立 AgentEngine，从原引擎提取并做 standalone 化。

## 内容

- `kernel.py` — 内核统一入口
- `et_contract.py` — ET 契约校验
- `et_sign.py` — 签名/验签
- `audit.py` — 审计事件
- `state_store.py` — 状态持久化
- `state_wiring.py` — 状态双写收口
- `et_test_gates.py` — 测试门禁 ET 模块
- `claude_engine.py` — Claude API 执行引擎（可选）
- `database.py` — 独立 SQLite 数据库入口

## 安装

```bash
pip install -r requirements.txt
```

可选 Claude 执行引擎：

```bash
pip install -r requirements-optional.txt
```

## 使用

```python
from xj_engine.kernel import et
# 按 ET 契约传入 payload 调用
```

或参考 `et_contract.py` 中的 payload/输出契约。

## 环境变量

见 `.env.example`。

- `XJ_ENGINE_DB_URL`：数据库地址
- `AGENT_ENGINE_SECRET`：内核签发密钥

## 兼容性说明

- 已移除原平台数据库依赖，改为本地 `database.py`
- 已移除外部测试技能服务依赖，`skills.py` 为 stub
- 已移除原平台私有路径依赖
- 不包含原平台业务代码
