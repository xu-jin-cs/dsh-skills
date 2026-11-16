# ArchMap — 架构测绘 Agent（中文说明）

> 终端原生静态分析：架构基线建一次，之后每次变更都被度量——影响面、行级 diff、测试选择——**不再让 LLM 重读整个仓库**。
>
> [English](README.md) · [← 返回 dsh-skills](../README.md)

## 是什么 / 治什么痛点

Agent 回答「这个改动影响什么」时重读整仓——烧 token 还漏路由漏闭包。ArchMap 用**确定性计算**替代全仓重读：

- **零参自动分流**：无基线 → `full` 全量初始化；有基线 → `lite` 极简增量（秒级，未变更模块复用基线）。
- **需求 → 影响面**：需求文本 → 受影响模块/文件/函数/路由（`precise_analysis.json`）。
- **行级 diff（零 LLM）**：精确变更行区间、导入闭包、测试选择 + 变更台账——纯确定性计算，不烧 token。
- 精准开发、节约 tokens。

## 30 秒安装

```bash
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install archmap --with-deps
```

符号链接装入 `~/.dsh/skills`（DSH watcher 热加载）；`--with-deps` 装齐 `PyYAML / numpy / scipy`。已 clone 本仓：`./install.sh archmap --with-deps`。卸载/体检走同一安装器。

## 5 分钟上手

五模式一个入口（零参自动分流；`full`/`lite` 显式词兜底）：

```bash
/archmap <项目路径>                        # 自动：无基线→full；有基线→lite
/archmap <项目路径> full | lite [备注]      # 强制模式
/archmap <项目路径> <需求文本>              # 增量影响面
/archmap <项目路径> sync                   # 同步基线并重生成报告
/archmap <项目路径> diff [备注]             # 行级 diff 影响面 + 测试选择
```

典型节奏：

1. 建基线：`/archmap /path/to/project`
2. 定影响面：`/archmap /path/to/project "新增用户积分系统"` → `precise_analysis.json`
3. 开发。
4. 复盘前：`/archmap /path/to/project diff 本次修改备注` → `diff_impact.json` + 变更台账
5. 验收后刷新：`/archmap /path/to/project sync`

## 输入 / 输出

全部产物写入 `<项目路径>/archmap/`：

```
full_index.json        # 完整架构基线
vector_cache.json      # 模块向量缓存
module_hashes.json     # 模块内容指纹（SHA256）
file_line_hashes.json  # 行级快照（diff/lite 比对依据）
01_执行摘要.md ~ 09_粒度校验报告.md   # 报告（含 Mermaid 架构图/数据链路图/时序图）
precise_analysis.json  # 增量影响面（文件/函数/路由精准定位）
diff_impact.json       # diff 影响面与测试选择
diff_history.jsonl     # 变更留痕（机器可读）
10_变更历史.md          # 变更台账（复盘输入）
recall_report.json     # 召回验证
etl_rules/             # ETL 特征项目自动产出
```

**五种模式**：full（零参无基线）· lite（零参有基线）· 增量影响面（路径+需求）· sync（路径+sync）· diff（路径+diff）。

## 能力与边界

- **擅长**：中大型代码库架构摸底（模块拆分、API/存储资产盘点、依赖矩阵、Mermaid 图）；日常增量维护；需求落地前影响面分析；复盘前变更留痕；ETL 特征项目（7 分层规则文档 + 契约漂移检测）。
- **不在射程**：只读分析方——不执行代码、不改业务源码、不校验执行结果（消费侧负责）；粒度到 api/函数级（有意设计，省 token 优先）；不起 Web 服务；状态全在 `<项目>/archmap/`；产物纯文本（JSON/Markdown/Mermaid）。
- **依赖**：必需 PyYAML/numpy/scipy；可选 sentence-transformers（离线自动回退确定性哈希向量化——功能完整，精度略降）。离线友好：全程无网络请求。

## 组合用法

- **test-case-designer**：消费 02~08 号产物；增量场景读 `precise_analysis.json` 圈定测试范围。
- **whitebox-coverage**：diff 模式以 `diff_impact.json` 圈定范围。
- **复盘流程**：`10_变更历史.md` + `diff_history.jsonl` 为台账输入。
- **[gate-switch](../gate-switch/README_zh.md)**：消费产物前用 `mtime_after` 核验新鲜度。

细节：[`SKILL.md`](SKILL.md)（触发方式、专家槽位、测试节点清单）。

---

许可：[自定义源码可用许可](../LICENSE)（中文对照：[LICENSE-zh.md](../LICENSE-zh.md)）——仅供个人非商用本地使用；未经书面授权禁止公开 Fork、商用分发、SaaS 服务。作者 [xu-jin-cs](https://github.com/xu-jin-cs)。
