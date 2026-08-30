# ArchMap 架构测绘 Agent

终端原生架构测绘 Agent（无 Web 界面），对目标项目做静态源码分析，生成架构基线与全套文本报告；支持增量影响面分析、变更同步与行级 diff 影响面，让开发只动该动的文件——精准开发、节约 tokens。

## 一条命令安装

无需 clone 仓库，直接远程自举安装：

```bash
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install archmap --with-deps
```

- 默认以符号链接装入 `~/.dsh/skills`，DSH watcher 热加载即生效；`--with-deps` 自动执行 `pip3 install -r requirements.txt`。
- 已 clone 本仓库的场景：`./install.sh archmap --with-deps`。
- 卸载：`... | bash -s -- uninstall archmap`；体检：`... | bash -s -- doctor`。

## 作用范围

**适用**：

- 中大型代码库的架构摸底：模块拆分、API/存储资产盘点、依赖矩阵、Mermaid 架构图/数据链路图/时序图。
- 日常迭代的增量维护：变更检测 + 变更模块局部重解析，未变更模块复用基线，不重复消耗 LLM。
- 需求落地前的影响面分析：需求文本 → 受影响模块/文件/函数/路由清单（`precise_analysis.json`），指导精准开发。
- 复盘前的变更留痕：行级 diff 影响面 + 测试选择（`diff_impact.json`）+ 变更台账（`10_变更历史.md` / `diff_history.jsonl`）。
- 含 ETL 特征目录的项目：自动产出 7 分层 ETL 规则维护文档与配置契约漂移检测报告（`etl_rules/`）。

**不适用 / 边界**：

- 纯分析方：只做架构测绘与影响面分析，**不执行代码、不修改业务源码、不校验执行结果**；消费侧（如 whitebox-coverage）如何使用产物归消费侧负责。
- 模块粒度上限为 api/方法（函数）级（有意设计：够用即可，核心是省 token），不做语句级拆解。
- 不启动任何 Web 服务；状态全部保存在 `<项目路径>/archmap/` 目录内，无外部数据库依赖。
- 输出均为 JSON/Markdown/Mermaid 纯文本，不生成图片。

## 能力矩阵（五种模式）

| 模式 | 触发 | 说明 |
|------|------|------|
| full 全量分析 | 零参（无基线） | 全量扫描源码，生成完整架构基线 `full_index.json` 与 01~09 号 Markdown/Mermaid 报告 |
| lite 极简增量 | 零参（有基线） | 日常迭代默认：变更检测 + 变更模块局部重解析 + 台账留痕，秒级完成 |
| 增量影响面 | 路径 + 需求文本 | 需求向量化匹配模块，叠加路由闭包/关键词硬匹配召回补强，产出 `precise_analysis.json` |
| sync 同步更新 | 路径 + sync | 变更合并回基线并重生成全套报告，附召回验证（`recall_report.json`）与 ETL 产物回填 |
| diff 影响面 | 路径 + diff | git 无关的行级快照比对：精确变更行区间、导入闭包、测试选择（`diff_impact.json`） |

零参调用按基线存在与否自动分流 full/lite；`full` / `lite` 显式词可强制兜底。

## 使用方式

```bash
/archmap <项目路径>                        # 零参自动分流（推荐）
/archmap <项目路径> full | lite [备注]      # 强制模式兜底
/archmap <项目路径> <需求文本>              # 增量影响面分析
/archmap <项目路径> sync                   # 同步变更并重生成全套报告
/archmap <项目路径> diff [修改内容备注]     # diff 影响面 + 变更台账
```

典型节奏：

1. 建基线：`/archmap /path/to/project`
2. 定影响面：`/archmap /path/to/project "新增用户积分系统"` → `precise_analysis.json`
3. 开发并修改源码
4. 复盘前留痕：`/archmap /path/to/project diff 本次修改备注` → `diff_impact.json` + `10_变更历史.md`
5. 验收通过后刷新：`/archmap /path/to/project sync`

## 产物清单

全部产物写入 `<项目路径>/archmap/`：

```
full_index.json        # 完整架构基线
vector_cache.json      # 模块向量缓存
module_hashes.json     # 模块内容指纹（SHA256）
file_line_hashes.json  # 行级快照（diff/lite 比对依据）
01_执行摘要.md ~ 09_粒度校验报告.md   # 含 Mermaid 架构图/数据链路图/时序图
precise_analysis.json  # 增量影响面（文件/函数/路由精准定位）
diff_impact.json       # diff 影响面与测试选择
diff_history.jsonl     # 变更留痕（机器可读）
10_变更历史.md          # 变更台账（复盘输入）
recall_report.json     # 召回验证报告
etl_rules/             # ETL 项目自动产出（规则索引/依赖链/契约对齐报告等）
```

## 依赖

- 必需：`PyYAML` / `numpy` / `scipy`（`--with-deps` 一键装齐）。
- 可选：`sentence-transformers`（向量召回增强）；缺失时自动回退本地确定性哈希向量化，功能完整可用、精度略降。
- 离线友好：模型加载优先本地缓存，无缓存时快速失败并走哈希回退，全程不产生网络请求。

## 下游生态对接

- **test-case-designer**：消费 02~08 号产物做三要素测试设计；增量场景读 `precise_analysis.json` 圈定测试范围。
- **whitebox-coverage**：增量模式以 `diff_impact.json` 为范围依据。
- **复盘流程**：以 `10_变更历史.md` + `diff_history.jsonl` 为变更台账输入。

更多细节见同目录 `SKILL.md`。
