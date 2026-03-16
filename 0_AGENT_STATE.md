# 项目状态快照 (Agent State)

> **Last Updated**: 2026-03-16
> **Purpose**: 为 AI 智能体提供项目当前状态的完整快照，确保会话断续后能快速恢复上下文。

---

## 📋 项目概览

**Toolify** 是一个中间件代理服务，为不原生支持函数调用的 LLM 注入 OpenAI 兼容的函数调用能力。它拦截客户端请求，注入 XML 格式的工具调用指令，解析上游响应中的 XML 工具调用，并转换为标准的 OpenAI `tool_calls` 格式。

**核心价值**：让任何 LLM（如 Gemini、本地模型等）都能像 GPT-4 一样支持函数调用。

**最新重大更新**：现已支持 Anthropic Messages API 格式，可与 Claude Code CLI 无缝集成。

---

## 🏗️ 核心架构

### 请求流程

```
客户端 (OpenAI/Anthropic 格式)
    ↓
Toolify (/v1/chat/completions 或 /v1/messages)
    ↓
[格式转换] → OpenAI 内部格式
    ↓
[消息预处理] preprocess_messages()
    ↓
[注入 FC 提示] generate_function_prompt() (如果有 tools)
    ↓
[上游格式转换] (如果上游是 Anthropic 格式)
    ↓
上游 LLM (OpenAI/Anthropic 格式)
    ↓
[响应格式转换] (如果上游是 Anthropic 格式)
    ↓
[XML 解析] parse_function_calls_xml()
    ↓
[转换为 tool_calls] (OpenAI 格式)
    ↓
[响应格式转换] (如果客户端是 Anthropic 格式)
    ↓
客户端收到标准格式的 tool_calls
```

### 双向格式支持

**下游（客户端 → Toolify）**：
- `/v1/chat/completions` - OpenAI 格式（标准）
- `/v1/messages` - Anthropic Messages API 格式（新增）

**上游（Toolify → LLM）**：
- `api_format: "openai"` - 默认，使用 OpenAI Chat Completions API
- `api_format: "anthropic"` - 使用 Anthropic Messages API

---

## 📁 核心文件结构

```
Toolify/
├── main.py                    # FastAPI 主应用 (~2700 行)
│   ├── /v1/chat/completions   # OpenAI 端点
│   ├── /v1/messages           # Anthropic 端点 (新增)
│   ├── /v1/models             # 模型列表
│   └── verify_api_key()       # 支持 Bearer 和 x-api-key
│
├── anthropic_adapter.py       # Anthropic 格式转换器 (新增, ~1000 行)
│   ├── AnthropicMessagesRequest        # Pydantic 模型
│   ├── anthropic_request_to_openai()   # Anthropic → OpenAI
│   ├── openai_response_to_anthropic()  # OpenAI → Anthropic
│   ├── openai_request_to_anthropic()   # 上游 Anthropic 转换
│   ├── anthropic_upstream_response_to_openai()
│   ├── openai_sse_to_anthropic_sse()   # 流式转换
│   └── anthropic_sse_to_openai_sse()   # 流式转换
│
├── config_loader.py           # 配置管理 (~260 行)
│   ├── UpstreamService        # 新增 api_format, anthropic_version
│   ├── ServerConfig
│   ├── ClientAuthConfig
│   ├── FeaturesConfig
│   └── AppConfig
│
├── admin.py                   # Web 管理界面 (~900 行)
│   └── Alpine.js SPA          # 新增 api_format 下拉框
│
├── config.yaml                # 运行时配置 (不在 git)
├── config.example.yaml        # 配置模板 (新增 Anthropic 示例)
├── requirements.txt           # Python 依赖
├── README.md / README_zh.md   # 项目文档
├── CLAUDE.md                  # Claude Code 开发指南
├── 0_REQUIRE.md               # AI 开发准则
├── 0_AGENT_STATE.md           # 本文件
└── 0_TODO.md                  # 任务清单
```

---

## 🔧 核心模块与逻辑

### 1. 认证模块 (`verify_api_key`)

**位置**: `main.py:1386`

**功能**: 验证客户端 API 密钥

**支持的认证方式**:
- `Authorization: Bearer <key>` (OpenAI 标准)
- `x-api-key: <key>` (Anthropic 标准)

**逻辑**:
```python
if x_api_key:
    client_key = x_api_key
elif authorization:
    client_key = authorization.replace("Bearer ", "")
else:
    raise 401

if key_passthrough:
    return client_key  # 直接透传
if client_key not in ALLOWED_CLIENT_KEYS:
    raise 401
```

### 2. 上游路由模块 (`find_upstream`)

**位置**: `main.py:1249`

**功能**: 根据模型名称路由到对应的上游服务

**逻辑**:
1. 如果 `model_passthrough=true`，所有请求路由到 'openai' 服务
2. 否则，从 `MODEL_TO_SERVICE_MAPPING` 查找模型对应的服务
3. 如果模型名包含 `:`，处理别名（如 `gemini-2.5:gemini-2.5-pro`）
4. 如果找不到，使用默认服务

**返回**: `(service_dict, actual_model_name)`

### 3. URL/Headers 构建模块 (`build_upstream_url_and_headers`)

**位置**: `main.py:1310`

**功能**: 根据上游服务的 `api_format` 构建正确的 URL 和 headers

**OpenAI 格式**:
```python
url = f"{base_url}/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
```

**Anthropic 格式**:
```python
url = f"{base_url}/v1/messages"  # 智能处理 /v1 路径
headers = {
    "x-api-key": api_key,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}
```

### 4. 消息预处理模块 (`preprocess_messages`)

**位置**: `main.py:1396`

**功能**: 将 OpenAI 格式的消息转换为上游兼容格式

**转换规则**:
- `role=tool` → `role=user` (带格式化的工具结果上下文)
- `assistant.tool_calls` → XML 格式的 content
- `role=developer` → `role=system` (如果配置启用)

**工具结果格式化**:
```xml
<tool_result>
<tool_name>search</tool_name>
<tool_arguments>{"query": "test"}</tool_arguments>
<result>
搜索结果内容
</result>
</tool_result>
```

**新增配置（Claude Code 兼容性）**:
- `features.tool_result_style`: `"legacy"`（默认）或 `"xml"`（推荐给 Claude Code；减少模型模仿“Tool execution result”等工具回显）

### 5. 函数调用提示注入模块 (`generate_function_prompt`)

**位置**: `main.py:791`

**功能**: 生成包含工具定义和调用指令的系统提示

**提示结构**:
```
你可以使用以下工具：

1. **tool_name**
   描述: ...
   参数:
   - param1 (type): 描述

输出格式：
<trigger_signal/>
<function_calls>
  <function_call>
    <tool>tool_name</tool>
    <args_json><![CDATA[{"param": "value"}]]></args_json>
  </function_call>
</function_calls>
```

**触发信号**: 随机生成（如 `<Function_AB1c_Start/>`），避免与模型输出冲突

### 6. XML 解析模块 (`parse_function_calls_xml`)

**位置**: `main.py:1080`

**功能**: 从模型响应中解析 XML 格式的工具调用

**解析步骤**:
1. 移除 `<think>` 块（避免误判）
2. 查找最后一个触发信号位置
3. 提取 `<function_calls>` XML 块
4. 使用 `xml.etree.ElementTree` 解析
5. 如果 XML 解析失败，使用正则表达式回退

**返回**: `List[{"name": str, "args": dict}]`

### 7. 工具调用验证模块 (`validate_parsed_tools`)

**位置**: `main.py:424`

**功能**: 验证解析的工具调用是否符合 JSON Schema

**验证内容**:
- 工具名称是否在声明的工具列表中
- 参数是否符合 schema 定义
- 必需参数是否存在
- 类型、枚举、模式等约束

### 8. 流式代理模块 (`stream_proxy_with_fc_transform`)

**位置**: `main.py:2074`

**功能**: 流式代理，支持动态检测和解析工具调用

**核心组件**: `StreamingFunctionCallDetector` (line 985)

**状态机**:
- `detecting`: 检测触发信号
- `tool_parsing`: 缓冲并解析工具调用 XML

**特性**:
- 避免 `<think>` 块内的误判
- 支持早期终止（检测到 `</function_calls>` 立即解析）
- 支持错误重试（如果配置启用）
- 解析失败时返回流式 `error`（不再“沉默 stop/突然截断”），便于 Claude Code CLI 可靠判断失败原因

**新增配置（/v1/messages 流式保活）**:
- `features.stream_keepalive_seconds`: `0` 关闭；>0 时当上游长时间无数据，周期性输出 Anthropic `ping` 事件

**新增配置（强制流式响应）**:
- `features.force_streaming_for_non_stream_requests`: 开启后，即使客户端 `stream=false`，也会强制上游使用流式（`stream=true`），待流式结束后再以非流式 JSON 返回（假非流式）

**Anthropic 上游处理**:
- 如果 `upstream_api_format == "anthropic"`，先通过 `anthropic_sse_to_openai_sse()` 转换流
- 然后应用相同的 FC 检测逻辑

### 9. Anthropic 格式转换模块 (`anthropic_adapter.py`)

**核心转换函数**:

#### `anthropic_request_to_openai()`
- 提取 `system` 参数 → `role=system` 消息
- `user` 消息中的 `tool_result` 块 → `role=tool` 消息
- `assistant` 消息中的 `tool_use` 块 → `tool_calls` 数组
- `thinking` 块 → `reasoning_content` 字段
- `tools[].input_schema` → `tools[].function.parameters`
- `tool_choice: "any"` → `"required"`

#### `openai_response_to_anthropic()`
- `message.content` → `[{"type": "text", "text": ...}]`
- `message.tool_calls` → `[{"type": "tool_use", "id": "toolu_...", ...}]`
- `message.reasoning_content` → `[{"type": "thinking", ...}]`
- `finish_reason: "tool_calls"` → `stop_reason: "tool_use"`
- 工具调用 ID 重映射：`call_` → `toolu_`

#### `openai_request_to_anthropic()`
- 提取 `system` 消息 → `system` 参数
- `role=tool` → `tool_result` 内容块（在 `user` 消息中）
- `assistant.tool_calls` → `tool_use` 内容块
- **强制消息交替**：合并连续相同角色的消息
- 确保第一条消息是 `user`

#### `anthropic_upstream_response_to_openai()`
- `content` 数组 → 分离 text/tool_use/thinking
- `stop_reason: "tool_use"` → `finish_reason: "tool_calls"`
- `usage.input_tokens` → `usage.prompt_tokens`

#### 流式转换
- `openai_sse_to_anthropic_sse()`: 状态机生成 Anthropic SSE 事件
  - `message_start` → `content_block_start` → `content_block_delta` → `content_block_stop` → `message_delta` → `message_stop`
- `anthropic_sse_to_openai_sse()`: 解析 Anthropic 事件，生成 OpenAI SSE

### 10. 端点模块

#### `/v1/chat/completions` (OpenAI 端点)
**位置**: `main.py:1531`

**流程**:
1. 验证 API 密钥
2. 查找上游服务
3. 预处理消息
4. 注入 FC 提示（如果有 tools）
5. 根据上游 `api_format` 转换请求
6. 发送到上游
7. 转换响应（如果上游是 Anthropic）
8. 解析工具调用
9. 返回 OpenAI 格式响应

#### `/v1/messages` (Anthropic 端点)
**位置**: `main.py:2450`

**流程**:
1. 验证 API 密钥（支持 `x-api-key`）
2. 解析 Anthropic 请求
3. **转换为 OpenAI 内部格式**
4. 查找上游服务
5. 预处理消息
6. 注入 FC 提示（如果有 tools）
7. 根据上游 `api_format` 转换请求
8. 发送到上游
9. 转换响应（如果上游是 Anthropic）
10. 解析工具调用
11. **转换为 Anthropic 格式**
12. 返回 Anthropic 格式响应

**关键差异**:
- 入口/出口使用 Anthropic 格式
- 内部处理完全复用 OpenAI 管道
- 错误响应使用 Anthropic 格式：`{"type": "error", "error": {...}}`

---

## 🔑 关键设计决策

### 1. 边缘转换架构
**决策**: 在入口/出口处转换格式，内部统一使用 OpenAI 格式处理

**理由**:
- 最小化代码变更
- 复用成熟的 XML 注入/解析管道
- 降低维护成本

### 2. 触发信号机制
**决策**: 使用随机生成的唯一触发信号（如 `<Function_AB1c_Start/>`）

**理由**:
- 避免与模型生成内容冲突
- 每次启动生成新信号，提高安全性

### 3. `<think>` 块处理
**决策**: 在检测工具调用时忽略 `<think>` 块内的内容

**理由**:
- 模型可能在思考过程中提到工具名称
- 避免误判导致解析失败

### 4. 工具调用 ID 格式
**决策**: OpenAI 使用 `call_` 前缀，Anthropic 使用 `toolu_` 前缀

**理由**:
- 符合各自 API 规范
- Claude Code CLI 严格要求 `toolu_` 前缀

### 5. 消息交替强制
**决策**: 向 Anthropic 上游发送请求时，强制 user/assistant 交替

**理由**:
- Anthropic API 严格要求消息交替
- 合并连续相同角色的消息以满足要求

---

## 🎯 当前状态

### ✅ 已完成功能

1. **OpenAI 端点** (`/v1/chat/completions`)
   - 完整的函数调用注入和解析
   - 流式和非流式支持
   - 错误重试机制
   - Token 计数
   - 支持 Anthropic 格式上游

2. **Anthropic 端点** (`/v1/messages`)
   - 完整的 Anthropic Messages API 支持
   - 双向格式转换
   - 流式和非流式支持
   - 支持 Anthropic 格式上游
   - Claude Code CLI 深度适配

3. **格式转换器** (`anthropic_adapter.py`)
   - 请求/响应双向转换
   - 流式 SSE 格式转换
   - 工具调用 ID 重映射
   - 扩展思考块处理
   - 消息交替强制

4. **配置系统**
   - `api_format` 字段支持
   - `anthropic_version` 字段支持
   - Web 管理界面更新

5. **认证系统**
   - 支持 `Authorization: Bearer`
   - 支持 `x-api-key`

### 🔄 运行时行为

**启动时**:
1. 加载 `config.yaml`
2. 验证配置（Pydantic）
3. 构建 `MODEL_TO_SERVICE_MAPPING`
4. 生成全局触发信号 `GLOBAL_TRIGGER_SIGNAL`
5. 启动 FastAPI 服务器

**请求处理**:
1. 认证检查
2. 格式检测（OpenAI 或 Anthropic）
3. 格式转换（如需要）
4. 上游路由
5. 消息预处理
6. FC 提示注入（如有 tools）
7. 上游格式转换（如需要）
8. 发送到上游
9. 响应格式转换（如需要）
10. XML 解析（如有 FC）
11. 响应格式转换（如需要）
12. 返回客户端

---

## 🐛 已知问题与限制

### 当前无已知严重问题

**潜在限制**:
1. 上游模型必须能够理解并遵循 XML 格式指令
2. 某些模型可能在复杂工具调用场景下表现不佳
3. 流式响应中的早期终止依赖于检测 `</function_calls>` 标签

---

## 📊 性能特征

- **延迟**: 增加约 10-50ms（格式转换 + XML 解析）
- **内存**: 流式响应使用缓冲区，非流式响应一次性加载
- **并发**: FastAPI 异步处理，支持高并发
- **Token 计数**: 使用 tiktoken 精确计数

---

## 🔐 安全考虑

1. **API 密钥验证**: 所有端点都需要有效的客户端密钥
2. **上游密钥隔离**: 客户端无法直接访问上游 API 密钥
3. **Key Passthrough 模式**: 可选，允许客户端密钥直接透传到上游
4. **输入验证**: 使用 Pydantic 严格验证所有输入
5. **错误信息**: 不泄露敏感的内部错误细节

---

## 🚀 部署配置

### 环境变量
- `TOOLIFY_CONFIG_PATH`: 配置文件路径（默认: `config.yaml`）

### 配置文件结构
```yaml
server:
  port: 8000
  host: "0.0.0.0"
  timeout: 180

upstream_services:
  - name: "openai"
    base_url: "https://api.openai.com/v1"
    api_key: "sk-..."
    api_format: "openai"  # 或 "anthropic"
    anthropic_version: "2023-06-01"  # 仅 Anthropic 格式需要
    models: [...]
    is_default: true

client_authentication:
  allowed_keys: ["sk-..."]

features:
  enable_function_calling: true
  log_level: "INFO"
  convert_developer_to_system: true
  key_passthrough: false
  model_passthrough: false
  enable_fc_error_retry: false
  fc_error_retry_max_attempts: 3
```

---

## 📝 开发注意事项

### 修改代码时必须同步更新的内容

1. **添加新端点**: 更新本文档的"端点模块"部分
2. **修改核心逻辑**: 更新"核心模块与逻辑"部分
3. **改变数据流**: 更新"请求流程"图
4. **添加新配置**: 更新"部署配置"部分
5. **发现 Bug**: 更新"已知问题与限制"部分

### 代码风格约定

- 使用 Pydantic 进行数据验证
- 使用 async/await 处理 I/O 操作
- 日志使用 emoji 前缀（🔧 调试, 📝 信息, ❌ 错误, ✅ 成功）
- 函数名使用 snake_case
- 类名使用 PascalCase

---

## 🔗 相关文档

- `README.md` / `README_zh.md`: 用户文档
- `CLAUDE.md`: Claude Code 开发指南
- `0_REQUIRE.md`: AI 开发准则
- `0_TODO.md`: 任务清单
- `config.example.yaml`: 配置示例

---

**记住**: 这个文档是项目的"记忆"。每次重大变更后，必须更新它，确保下一个 AI 智能体能够快速理解项目状态。
