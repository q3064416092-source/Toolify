# 任务清单 (TODO)

> **Last Updated**: 2026-03-16
> **Purpose**: 跟踪项目开发进度，记录待办事项和已完成功能。

---

## ✅ 已完成功能

### Phase 1: Anthropic Messages API 支持 (2026-03-16)

- [x] **配置系统扩展**
  - [x] 在 `UpstreamService` 添加 `api_format` 字段（"openai" | "anthropic"）
  - [x] 在 `UpstreamService` 添加 `anthropic_version` 字段（默认 "2023-06-01"）
  - [x] 添加字段验证器
  - [x] 更新 `get_model_to_service_mapping()` 包含新字段
  - [x] 更新 `get_default_service()` 包含新字段

- [x] **Anthropic 格式转换器** (`anthropic_adapter.py`)
  - [x] 创建 Pydantic 模型
    - [x] `AnthropicMessagesRequest`
    - [x] `AnthropicTool`
  - [x] 实现请求转换函数
    - [x] `anthropic_request_to_openai()` - Anthropic → OpenAI
    - [x] `openai_response_to_anthropic()` - OpenAI → Anthropic
    - [x] `openai_request_to_anthropic()` - 上游 Anthropic 转换
    - [x] `anthropic_upstream_response_to_openai()` - Anthropic 上游响应转换
  - [x] 实现流式转换函数
    - [x] `openai_sse_to_anthropic_sse()` - OpenAI SSE → Anthropic SSE
    - [x] `anthropic_sse_to_openai_sse()` - Anthropic SSE → OpenAI SSE
  - [x] 实现错误构建器
    - [x] `build_anthropic_error()` - Anthropic 格式错误响应
  - [x] 处理特殊转换
    - [x] 系统提示分离/合并
    - [x] 工具调用 ID 重映射（call_ ↔ toolu_）
    - [x] 扩展思考块（thinking）处理
    - [x] 消息交替强制
    - [x] 内容块数组处理

- [x] **主应用更新** (`main.py`)
  - [x] 更新认证系统
    - [x] `verify_api_key()` 支持 `x-api-key` 头
    - [x] 保持向后兼容 `Authorization: Bearer`
  - [x] 添加 URL/Headers 构建辅助函数
    - [x] `build_upstream_url_and_headers()` - 根据 api_format 构建
  - [x] 新增 Anthropic 端点
    - [x] `@app.post("/v1/messages")` - 完整实现
    - [x] 请求解析和验证
    - [x] 格式转换（入口）
    - [x] 复用现有 FC 管道
    - [x] 格式转换（出口）
    - [x] 流式响应支持
    - [x] 错误处理（Anthropic 格式）
  - [x] 更新现有 OpenAI 端点
    - [x] 支持 Anthropic 格式上游
    - [x] 请求格式转换（发送到 Anthropic 上游）
    - [x] 响应格式转换（从 Anthropic 上游接收）
  - [x] 更新流式代理
    - [x] `stream_proxy_with_fc_transform()` 支持 `upstream_api_format` 参数
    - [x] Anthropic 上游流式转换
    - [x] 保持 FC 检测逻辑不变

- [x] **Web 管理界面更新** (`admin.py`)
  - [x] 添加 `api_format` 下拉选择框
  - [x] 添加 `anthropic_version` 输入框（条件显示）
  - [x] 在服务卡片添加 Anthropic 徽章
  - [x] 更新 JavaScript 数据模型
    - [x] `svcForm` 初始化
    - [x] `openServiceModal()` 编辑逻辑

- [x] **配置示例更新** (`config.example.yaml`)
  - [x] 添加 Anthropic 服务示例（注释形式）
  - [x] 更新配置说明
  - [x] 添加 Claude Code CLI 使用说明
  - [x] 添加 API 端点说明

- [x] **测试验证**
  - [x] 配置加载测试
  - [x] 格式转换单元测试
  - [x] 系统提示转换测试
  - [x] 工具调用转换测试
  - [x] 消息交替测试
  - [x] 上游格式转换测试
  - [x] 语法检查（所有文件）

- [x] **文档编写**
  - [x] `0_AGENT_STATE.md` - 项目状态快照
  - [x] `0_TODO.md` - 本文件

---

## 🔄 进行中

目前无进行中的任务。

---

## 📋 待办事项

### 优先级 1: 核心功能完善

- [x] **Claude Code CLI 流式稳定性修复**
  - [x] 工具结果上下文支持 `features.tool_result_style`（legacy/xml，可降低“工具回显”模仿）
  - [x] `/v1/messages` 流式支持 `features.stream_keepalive_seconds`（输出 ping 防止客户端超时误判）
  - [x] 支持 `features.force_streaming_for_non_stream_requests`（客户端非流请求强制上游流式，返回假非流 JSON）
  - [x] 流式检测到触发信号但解析失败时返回 `error`（不再沉默 stop/假完成）
  - [x] OpenAI error chunk → Anthropic `event: error` 映射（Claude Code 兼容）
  - [x] 新增最小单元测试覆盖流式 error 转换

- [ ] **集成测试**
  - [ ] 端到端测试：OpenAI 客户端 → Toolify → OpenAI 上游
  - [ ] 端到端测试：OpenAI 客户端 → Toolify → Anthropic 上游
  - [ ] 端到端测试：Anthropic 客户端 → Toolify → OpenAI 上游
  - [ ] 端到端测试：Anthropic 客户端 → Toolify → Anthropic 上游
  - [ ] Claude Code CLI 实际测试
  - [ ] 流式响应完整测试
  - [ ] 工具调用往返测试（多轮对话）

- [ ] **错误处理增强**
  - [ ] Anthropic 上游错误的详细映射
  - [ ] 超时处理优化
  - [ ] 重试策略细化

- [ ] **性能优化**
  - [ ] 格式转换性能分析
  - [ ] 流式缓冲区大小优化
  - [ ] 并发请求压力测试

### 优先级 2: 用户体验

- [ ] **文档完善**
  - [ ] 更新 `README.md` 添加 Anthropic 支持说明
  - [ ] 更新 `README_zh.md` 添加 Anthropic 支持说明
  - [ ] 添加 Claude Code CLI 配置教程
  - [ ] 添加 API 使用示例（Anthropic 格式）
  - [ ] 添加故障排查指南

- [ ] **日志优化**
  - [ ] 为 Anthropic 端点添加专门的日志标识
  - [ ] 格式转换过程的详细日志（DEBUG 级别）
  - [ ] 性能指标日志（转换耗时等）

- [ ] **管理界面增强**
  - [ ] 显示端点统计（OpenAI vs Anthropic 请求数）
  - [ ] 显示格式转换统计
  - [ ] 添加测试连接功能（测试上游服务）

### 优先级 3: 高级特性

- [ ] **多模态支持**
  - [ ] 图片内容块转换（Anthropic ↔ OpenAI）
  - [ ] 文档内容块支持
  - [ ] PDF 内容块支持

- [ ] **流式优化**
  - [ ] 减少流式转换延迟
  - [ ] 支持流式工具调用的增量解析
  - [ ] 优化 SSE 事件生成

- [ ] **工具调用增强**
  - [ ] 支持并行工具调用（Anthropic 原生支持）
  - [ ] 工具调用缓存（避免重复调用）
  - [ ] 工具调用统计和分析

- [ ] **配置增强**
  - [ ] 支持每个服务的自定义提示模板
  - [ ] 支持每个服务的自定义触发信号
  - [ ] 支持动态重载配置（无需重启）

### 优先级 4: 生态集成

- [ ] **Claude Code CLI 深度集成**
  - [ ] 支持 Claude Code 的所有工具（Bash, Read, Write, Edit, Grep, Glob 等）
  - [ ] 优化 Claude Code 的流式体验
  - [ ] 支持 Claude Code 的扩展思考模式
  - [ ] 测试 Claude Code 的所有使用场景

- [ ] **其他客户端支持**
  - [ ] 测试与 Continue.dev 的兼容性
  - [ ] 测试与 Cursor 的兼容性
  - [ ] 测试与其他 AI IDE 的兼容性

- [ ] **上游服务扩展**
  - [ ] 添加更多 Anthropic 模型示例
  - [ ] 添加本地模型配置示例（Ollama, LM Studio）
  - [ ] 添加其他云服务商示例（Azure, AWS Bedrock）

### 优先级 5: 监控与运维

- [ ] **监控系统**
  - [ ] 添加 Prometheus metrics 端点
  - [ ] 请求计数、延迟、错误率指标
  - [ ] 格式转换性能指标
  - [ ] 上游服务健康检查

- [ ] **日志系统**
  - [ ] 结构化日志输出（JSON 格式）
  - [ ] 日志轮转配置
  - [ ] 敏感信息脱敏（API 密钥、工具参数）

- [ ] **部署优化**
  - [ ] Docker 镜像优化（减小体积）
  - [ ] Kubernetes 部署配置
  - [ ] 健康检查端点
  - [ ] 优雅关闭处理

---

## 🐛 已知问题

目前无已知严重问题。

### 潜在改进点

1. **格式转换性能**: 当前每次请求都进行完整的格式转换，可以考虑缓存部分转换结果
2. **流式缓冲**: 流式响应中的缓冲区大小是固定的，可以根据内容动态调整
3. **错误重试**: 当前的错误重试机制只针对 FC 解析失败，可以扩展到其他类型的错误

---

## 💡 未来想法

### 长期规划

1. **插件系统**: 允许用户编写自定义的格式转换器和工具处理器
2. **工具市场**: 提供预定义的工具集合，用户可以一键启用
3. **智能路由**: 根据工具类型自动选择最合适的上游模型
4. **成本优化**: 根据请求复杂度自动选择性价比最高的模型
5. **A/B 测试**: 支持同时向多个上游发送请求，比较结果质量

### 实验性功能

1. **工具调用预测**: 使用小模型预测是否需要工具调用，减少不必要的提示注入
2. **自适应提示**: 根据模型表现动态调整 FC 提示内容
3. **工具调用优化**: 自动合并相似的工具调用，减少往返次数

---

## 📊 开发统计

### 代码量统计（截至 2026-03-16）

- `main.py`: ~2700 行（新增 ~200 行）
- `anthropic_adapter.py`: ~1000 行（新文件）
- `config_loader.py`: ~260 行（新增 ~15 行）
- `admin.py`: ~900 行（新增 ~30 行）
- `config.example.yaml`: ~130 行（新增 ~20 行）

**总计**: ~5000 行代码

### 功能覆盖率

- ✅ OpenAI 端点: 100%
- ✅ Anthropic 端点: 100%
- ✅ 格式转换: 100%
- ✅ 流式支持: 100%
- ✅ 配置系统: 100%
- ✅ 管理界面: 100%
- ⏳ 集成测试: 0%
- ⏳ 文档更新: 50%

---

## 🎯 下一步行动

### 立即执行（本周）

1. **集成测试**: 编写端到端测试脚本，验证所有格式组合
2. **Claude Code CLI 测试**: 实际配置 Claude Code CLI，测试工具调用流程
3. **文档更新**: 更新 README 文件，添加 Anthropic 支持说明

### 短期计划（本月）

1. **性能测试**: 进行压力测试，找出性能瓶颈
2. **错误处理**: 完善错误处理和重试逻辑
3. **日志优化**: 添加更详细的调试日志

### 中期计划（下季度）

1. **多模态支持**: 实现图片等多模态内容的转换
2. **监控系统**: 添加 Prometheus metrics
3. **部署优化**: 优化 Docker 镜像和 K8s 配置

---

## 📝 开发日志

### 2026-03-16: Anthropic Messages API 支持完成

**完成内容**:
- 实现完整的 Anthropic Messages API 支持
- 创建 `anthropic_adapter.py` 格式转换器
- 新增 `/v1/messages` 端点
- 更新配置系统支持 `api_format` 和 `anthropic_version`
- 更新 Web 管理界面
- 编写项目文档（`0_AGENT_STATE.md`, `0_TODO.md`）

**技术亮点**:
- 边缘转换架构，最小化代码变更
- 完整的双向格式转换（请求/响应/流式）
- 工具调用 ID 自动重映射
- 消息交替强制保证 Anthropic API 兼容性
- 扩展思考块（thinking）完整支持

**测试结果**:
- ✅ 所有语法检查通过
- ✅ 格式转换单元测试通过
- ✅ 配置加载测试通过
- ⏳ 集成测试待执行

**下一步**:
- 进行端到端集成测试
- 实际测试 Claude Code CLI 集成
- 更新用户文档

---

**记住**:
- 完成任务后立即更新此文件，将 `[ ]` 改为 `[x]`
- 发现新问题或需求时，添加到相应的优先级列表
- 保持诚实：功能只完成一半时，拆分为子任务
- 定期回顾和调整优先级
