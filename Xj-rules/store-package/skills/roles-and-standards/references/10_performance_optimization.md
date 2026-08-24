# 十、通用应用 / 服务开发全局性能优化编码规范

> 适用范围：所有项目、所有源码文件、所有工程配置与工具脚本。
> 强制性：全项目强制落地，违反视为代码缺陷。
> 无关项：本规范不绑定任何 MCP server、不绑定任何特定工作流、不绑定任何业务领域。

## 核心铁律

**任意业务逻辑、工具函数、数据处理逻辑，一行代码 / 单行表达式可完成的，绝不拆分为多行分步实现。**

优先使用单行链式调用、三元表达式、内置单行方法、推导式、lambda 等高密度写法；禁止通过多临时变量、多分步赋值来拉长执行链路。 【建议】

## 1. 代码编写层面

### 1.1 单行优先

- 变量赋值、JSON 构造、路径拼接、条件分支、字符串组装、数据过滤，优先使用单行链式、三元表达式、内置单行工具方法。
- 禁止拆分为多临时变量、多分步赋值。 【建议】

**正面示例：**
```python
result = json.loads(Path(path).read_text(encoding="utf-8"))
label = "ok" if status == 0 else "fail"
items = [x.strip() for x in raw.split(",") if x.strip()]
```

**反面示例：**
```python
file_path = Path(path)
text = file_path.read_text(encoding="utf-8")
data = json.loads(text)
if status == 0:
    label = "ok"
else:
    label = "fail"
```

### 1.2 消除无意义中间缓存变量

数据读取后直接传入下游方法，不额外定义中转变量占用内存与执行周期。

**正面示例：**
```python
return validate(extract_json(path.read_text(encoding="utf-8")))
```

**反面示例：**
```python
raw = path.read_text(encoding="utf-8")
data = extract_json(raw)
result = validate(data)
return result
```

### 1.3 工具方法单行封装

公共能力必须封装为单行通用工具方法，全项目复用。禁止每个业务模块重复编写分段逻辑。 【建议】

- 同一模式出现 2 次 → 抽取为工具函数
- 工具函数目标：调用方一行完成

## 2. IO 文件读写通用优化

### 2.1 单次全量操作

- 读取一次性加载入内存，写入仅执行一次持久化。
- 禁止分段追加、循环读写、多次打开关闭文件句柄。 【建议】

**正面示例：**
```python
Path(dst).write_bytes(Path(src).read_bytes())
```

**反面示例：**
```python
with open(src, "rb") as f:
    while chunk := f.read(1024):
        with open(dst, "ab") as out:
            out.write(chunk)
```

### 2.2 内存上下文传递优先

模块间数据优先使用内存变量传输，非必要不落地临时中转文件，减少磁盘 IO 耗时。

- 允许落地的只有：最终交付物、持久化配置、崩溃排查所需的错误快照
- 临时中间结果一律走函数返回值 / 共享内存对象

## 3. 日志输出性能优化

### 3.1 仅输出必要摘要

- 仅输出业务必要摘要日志
- 禁止打印：文件源码、完整结构化数据、文件行数、调试详情、逐 agent 中间状态等冗余内容 【规范】

### 3.2 批量缓存统一输出

- 日志采用内存批量缓存，流程结束统一输出
- 取消单步实时逐行打印，避免阻塞主线程

**正面示例：**
```python
log_buffer.append({"step": name, "status": "ok"})
# 流程结束时
print("\n".join(format(e) for e in log_buffer))
```

**反面示例：**
```python
print(f"[START] agent={name}")
print(f"[INPUT] {input_files}")
print(f"[OUTPUT] {output_path}")
print(f"[COMPLETE] agent={name}")
```

## 4. 实例与依赖加载优化

### 4.1 单例全局复用

全局工具、解析器、客户端采用单例全局复用，每个业务流程不重复初始化实例、重复加载依赖库。

**正面示例：**
```python
_client: anthropic.Anthropic | None = None

def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(...)
    return _client
```

### 4.2 按需懒加载

- 仅加载当前流程必需第三方包
- 启动阶段不预加载全部工具库
- 执行完成释放闲置内存对象

**正面示例：**
```python
def validate_schema(data, schema):
    from jsonschema import validate
    return validate(instance=data, schema=schema)
```

**反面示例：**
```python
import jsonschema  # 模块顶部无条件加载
```

## 5. 执行链路阻塞消除规范

### 5.1 禁止人为阻塞

- 禁止添加固定 sleep、延时等待、轮询重试等人为阻塞代码 【建议】
- 数据读写、序列化同步极简执行，无额外空闲间隙

**反面示例：**
```python
import time
time.sleep(0.5)  # 等待文件写入完成
```

### 5.2 极简校验

- 数据校验仅保留业务强制必填校验
- 移除多层嵌套校验、美化格式化、冗余合规校验逻辑，减少计算开销

**正面示例：**
```python
if not data.get("id"):
    raise ValueError("id required")
```

**反面示例：**
```python
for key in ["id", "name", "created_at", "updated_at", "meta"]:
    if key not in data:
        raise ValueError(f"{key} missing")
pretty = json.dumps(data, indent=2, ensure_ascii=False)
```

## 6. 调度执行层通用优化

### 6.1 事件回调触发

串行任务采用内存事件回调触发下游流程，不通过轮询文件状态判断任务完成，缩短节点等待时延。

**正面示例：**
```python
for agent in agents:
    output = run_agent(agent, input)
    input = output
```

**反面示例：**
```python
run_agent(agent)
while not output_path.exists():
    time.sleep(0.1)
```

### 6.2 消除调度空窗

任务执行无多余空闲间隔，上一任务完成后立刻触发下一段逻辑，消除调度空窗耗时。

## 例外

以下情况允许分步/多行：

1. **可读性严重受损**：单行超过 120 字符且无法合理拆分链式时，允许折行，但不得引入无意义中间变量
2. **错误处理**：`try/except` 块允许分步，但异常分支仍应极简
3. **性能实测需要**：当单行写法经实测明显慢于分步写法时，保留分步并附注释说明
4. **外部 API 强制要求**：某些 SDK 必须分步调用时，按 SDK 要求执行 【建议】

## 违规判定

代码审查时以下情况视为性能规范违规：

- 可单行完成却拆为多临时变量的实现
- 循环内重复打开文件、重复初始化客户端
- 单步实时打印调试日志阻塞主流程
- 无故添加 sleep、轮询文件状态
- 模块顶部无条件导入大量未使用依赖

违规处理方式：打回修改，不通过代码审查。
