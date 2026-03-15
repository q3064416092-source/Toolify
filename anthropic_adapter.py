# SPDX-License-Identifier: GPL-3.0-or-later
#
# Toolify: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 FunnyCups (https://github.com/funnycups)
#
# Anthropic Messages API adapter: bidirectional format conversion between
# Anthropic Messages API and OpenAI Chat Completions API.

import json
import uuid
import logging
from typing import List, Dict, Any, Optional, Union, AsyncIterator, AsyncGenerator

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models for Anthropic Messages API
# ---------------------------------------------------------------------------

class AnthropicTool(BaseModel):
    """Anthropic tool definition"""
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]

    class Config:
        extra = "allow"


class AnthropicMessagesRequest(BaseModel):
    """Anthropic Messages API request body"""
    model: str
    messages: List[Dict[str, Any]]
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
    max_tokens: int = Field(default=8192)
    tools: Optional[List[AnthropicTool]] = None
    tool_choice: Optional[Union[Dict[str, Any], str]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

_FINISH_TO_STOP = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
}

_STOP_TO_FINISH = {v: k for k, v in _FINISH_TO_STOP.items()}
_STOP_TO_FINISH["stop_sequence"] = "stop"


def _map_finish_reason_to_stop_reason(finish_reason: Optional[str]) -> str:
    if not finish_reason:
        return "end_turn"
    return _FINISH_TO_STOP.get(finish_reason, "end_turn")


def _map_stop_reason_to_finish_reason(stop_reason: Optional[str]) -> str:
    if not stop_reason:
        return "stop"
    return _STOP_TO_FINISH.get(stop_reason, "stop")


def _gen_msg_id() -> str:
    return f"msg_{uuid.uuid4().hex}"


def _gen_tool_use_id() -> str:
    return f"toolu_{uuid.uuid4().hex[:24]}"


def _remap_tool_call_id_to_anthropic(call_id: str) -> str:
    """Ensure tool call IDs use the Anthropic toolu_ prefix."""
    if call_id and call_id.startswith("call_"):
        return "toolu_" + call_id[5:]
    return call_id


# ---------------------------------------------------------------------------
# 1. Anthropic request  -->  OpenAI internal format
# ---------------------------------------------------------------------------

def anthropic_request_to_openai(request: AnthropicMessagesRequest) -> Dict[str, Any]:
    """Convert an Anthropic Messages API request to OpenAI Chat Completions format.

    Returns a dict suitable for constructing a ChatCompletionRequest.
    """
    openai_messages: List[Dict[str, Any]] = []

    # -- system prompt (separate in Anthropic, inline in OpenAI) --
    if request.system:
        if isinstance(request.system, str):
            openai_messages.append({"role": "system", "content": request.system})
        elif isinstance(request.system, list):
            # list of content blocks, concatenate text
            parts = []
            for block in request.system:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif isinstance(block.get("text"), str):
                        parts.append(block["text"])
            if parts:
                openai_messages.append({"role": "system", "content": "\n".join(parts)})

    # -- convert messages --
    for msg in request.messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if role == "user":
            openai_messages.extend(_convert_anthropic_user_message(content))
        elif role == "assistant":
            openai_messages.append(_convert_anthropic_assistant_message(msg))
        else:
            # pass-through unknown roles
            openai_messages.append(msg)

    # -- build result dict --
    result: Dict[str, Any] = {
        "model": request.model,
        "messages": openai_messages,
        "max_tokens": request.max_tokens,
    }

    if request.stream is not None:
        result["stream"] = request.stream

    if request.temperature is not None:
        result["temperature"] = request.temperature
    if request.top_p is not None:
        result["top_p"] = request.top_p
    if request.stop_sequences:
        result["stop"] = request.stop_sequences

    # -- tools --
    if request.tools:
        result["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.input_schema,
                },
            }
            for t in request.tools
        ]

    # -- tool_choice --
    if request.tool_choice is not None:
        result["tool_choice"] = _convert_anthropic_tool_choice(request.tool_choice)

    # Pass through extra fields that the core pipeline might need (e.g. stream_options)
    raw = request.model_dump(exclude_unset=True)
    for key in ("stream_options",):
        if key in raw:
            result[key] = raw[key]

    return result


def _convert_anthropic_user_message(content: Any) -> List[Dict[str, Any]]:
    """Convert a single Anthropic user message content to one or more OpenAI messages."""
    if isinstance(content, str):
        return [{"role": "user", "content": content}]

    if not isinstance(content, list):
        return [{"role": "user", "content": str(content) if content else ""}]

    text_parts: List[str] = []
    tool_results: List[Dict[str, Any]] = []
    image_parts: List[Dict[str, Any]] = []

    for block in content:
        if not isinstance(block, dict):
            text_parts.append(str(block))
            continue

        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_result":
            tool_results.append(block)
        elif btype == "image":
            image_parts.append(block)
        else:
            text_parts.append(json.dumps(block))

    messages: List[Dict[str, Any]] = []

    # Emit text/image content as user message
    if text_parts or image_parts:
        if image_parts:
            # multimodal: build content list with text + image_url parts
            content_list: List[Dict[str, Any]] = []
            for t in text_parts:
                if t:
                    content_list.append({"type": "text", "text": t})
            for img in image_parts:
                source = img.get("source", {})
                if source.get("type") == "base64":
                    content_list.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
                        }
                    })
            if content_list:
                messages.append({"role": "user", "content": content_list})
        elif text_parts:
            combined = "\n".join(text_parts)
            if combined:
                messages.append({"role": "user", "content": combined})

    # Emit each tool_result as an OpenAI tool message
    for tr in tool_results:
        tc_content = tr.get("content", "")
        if isinstance(tc_content, list):
            # extract text from sub-blocks
            parts = []
            for sub in tc_content:
                if isinstance(sub, dict) and sub.get("type") == "text":
                    parts.append(sub.get("text", ""))
                elif isinstance(sub, dict):
                    parts.append(json.dumps(sub))
                else:
                    parts.append(str(sub))
            tc_content = "\n".join(parts)

        is_error = tr.get("is_error", False)
        if is_error:
            tc_content = f"[Tool Error] {tc_content}"

        messages.append({
            "role": "tool",
            "tool_call_id": tr.get("tool_use_id", ""),
            "content": tc_content,
        })

    # If nothing was produced, emit an empty user message to maintain structure
    if not messages:
        messages.append({"role": "user", "content": ""})

    return messages


def _convert_anthropic_assistant_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a single Anthropic assistant message to OpenAI format."""
    content = msg.get("content")

    if isinstance(content, str):
        result: Dict[str, Any] = {"role": "assistant", "content": content}
        # preserve extra fields
        for k, v in msg.items():
            if k not in ("role", "content"):
                result[k] = v
        return result

    if not isinstance(content, list):
        return {"role": "assistant", "content": str(content) if content else None}

    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    reasoning_parts: List[str] = []

    for block in content:
        if not isinstance(block, dict):
            text_parts.append(str(block))
            continue

        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", _gen_tool_use_id()),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
            })
        elif btype == "thinking":
            reasoning_parts.append(block.get("thinking", ""))

    result = {"role": "assistant"}
    combined_text = "\n".join(text_parts).strip() if text_parts else None
    result["content"] = combined_text if combined_text else None

    if tool_calls:
        result["tool_calls"] = tool_calls
    if reasoning_parts:
        result["reasoning_content"] = "\n".join(reasoning_parts)

    return result


def _convert_anthropic_tool_choice(tc: Any) -> Any:
    """Convert Anthropic tool_choice to OpenAI tool_choice."""
    if isinstance(tc, str):
        # Anthropic string values: "auto", "any", "none"
        if tc == "any":
            return "required"
        return tc  # "auto", "none" map directly

    if isinstance(tc, dict):
        tc_type = tc.get("type", "")
        if tc_type == "auto":
            return "auto"
        if tc_type == "any":
            return "required"
        if tc_type == "none":
            return "none"
        if tc_type == "tool":
            return {
                "type": "function",
                "function": {"name": tc.get("name", "")},
            }
    return "auto"


# ---------------------------------------------------------------------------
# 2. OpenAI response  -->  Anthropic response (for /v1/messages egress)
# ---------------------------------------------------------------------------

def openai_response_to_anthropic(
    openai_resp: Dict[str, Any],
    original_model: str,
    input_tokens: int = 0,
) -> Dict[str, Any]:
    """Convert an OpenAI Chat Completions response to Anthropic Messages format."""
    choice = {}
    if openai_resp.get("choices"):
        choice = openai_resp["choices"][0]

    message = choice.get("message", {})
    finish_reason = choice.get("finish_reason")

    content_blocks: List[Dict[str, Any]] = []

    # thinking / reasoning
    reasoning = message.get("reasoning_content")
    if reasoning:
        content_blocks.append({
            "type": "thinking",
            "thinking": reasoning,
            "signature": "",
        })

    # text content
    text = message.get("content")
    if text:
        content_blocks.append({"type": "text", "text": text})

    # tool calls
    tool_calls = message.get("tool_calls", [])
    for tc in tool_calls:
        func = tc.get("function", {})
        try:
            args = json.loads(func.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            args = {}

        content_blocks.append({
            "type": "tool_use",
            "id": _remap_tool_call_id_to_anthropic(tc.get("id", _gen_tool_use_id())),
            "name": func.get("name", ""),
            "input": args,
        })

    # Ensure at least one content block
    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    # usage
    usage = openai_resp.get("usage", {})
    anthropic_usage = {
        "input_tokens": usage.get("prompt_tokens", input_tokens),
        "output_tokens": usage.get("completion_tokens", 0),
    }

    return {
        "id": _gen_msg_id(),
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": original_model,
        "stop_reason": _map_finish_reason_to_stop_reason(finish_reason),
        "stop_sequence": None,
        "usage": anthropic_usage,
    }


# ---------------------------------------------------------------------------
# 3. OpenAI internal  -->  Anthropic upstream request
# ---------------------------------------------------------------------------

def openai_request_to_anthropic(
    openai_body: Dict[str, Any],
    api_key: str,
    anthropic_version: str = "2023-06-01",
    extra_request_fields: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Convert internal OpenAI-format request to Anthropic Messages API format.

    Returns (body_dict, headers_dict).
    """
    messages = openai_body.get("messages", [])

    # Extract system messages
    system_parts: List[str] = []
    non_system_messages: List[Dict[str, Any]] = []

    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        system_parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        system_parts.append(item)
            elif isinstance(content, str):
                system_parts.append(content)
        else:
            non_system_messages.append(msg)

    # Convert non-system messages to Anthropic format with strict alternation
    anthropic_messages = _openai_messages_to_anthropic_messages(non_system_messages)

    body: Dict[str, Any] = {
        "model": openai_body.get("model", ""),
        "messages": anthropic_messages,
        "max_tokens": openai_body.get("max_tokens") or 4096,
    }

    if system_parts:
        body["system"] = "\n\n".join(system_parts)

    if openai_body.get("stream") is not None:
        body["stream"] = openai_body["stream"]
    if openai_body.get("temperature") is not None:
        body["temperature"] = openai_body["temperature"]
    if openai_body.get("top_p") is not None:
        body["top_p"] = openai_body["top_p"]

    stop = openai_body.get("stop")
    if stop:
        body["stop_sequences"] = stop if isinstance(stop, list) else [stop]

    # Pass through extra fields from original Anthropic request (e.g. thinking config)
    if extra_request_fields:
        for key in ("thinking", "metadata", "top_k"):
            if key in extra_request_fields:
                body[key] = extra_request_fields[key]

    headers = {
        "x-api-key": api_key,
        "anthropic-version": anthropic_version,
        "content-type": "application/json",
    }
    if openai_body.get("stream"):
        headers["accept"] = "text/event-stream"

    return body, headers


def _openai_messages_to_anthropic_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert OpenAI messages to Anthropic format with strict user/assistant alternation."""
    raw_msgs: List[Dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")

        if role == "tool":
            # tool result → user message with tool_result block
            tc_content = content if isinstance(content, str) else str(content or "")
            raw_msgs.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": tc_content,
                }],
            })

        elif role == "assistant":
            blocks: List[Dict[str, Any]] = []

            # reasoning_content
            reasoning = msg.get("reasoning_content")
            if reasoning:
                blocks.append({"type": "thinking", "thinking": reasoning, "signature": ""})

            # text content
            if isinstance(content, str) and content:
                blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        blocks.append(item)

            # tool_calls
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                func = tc.get("function", {})
                try:
                    args = json.loads(func.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": _remap_tool_call_id_to_anthropic(tc.get("id", _gen_tool_use_id())),
                    "name": func.get("name", ""),
                    "input": args,
                })

            if blocks:
                raw_msgs.append({"role": "assistant", "content": blocks})
            else:
                raw_msgs.append({"role": "assistant", "content": [{"type": "text", "text": ""}]})

        elif role == "user":
            if isinstance(content, str):
                raw_msgs.append({"role": "user", "content": content})
            elif isinstance(content, list):
                raw_msgs.append({"role": "user", "content": content})
            else:
                raw_msgs.append({"role": "user", "content": str(content or "")})

        else:
            # unknown role, treat as user
            raw_msgs.append({"role": "user", "content": str(content or "")})

    # Enforce strict alternation: merge consecutive same-role messages
    merged: List[Dict[str, Any]] = []
    for msg in raw_msgs:
        if merged and merged[-1]["role"] == msg["role"]:
            _merge_anthropic_messages(merged[-1], msg)
        else:
            merged.append(msg)

    # Anthropic requires first message to be user
    if merged and merged[0]["role"] != "user":
        merged.insert(0, {"role": "user", "content": ""})

    return merged


def _merge_anthropic_messages(target: Dict[str, Any], source: Dict[str, Any]):
    """Merge source message content into target message (same role)."""
    t_content = target.get("content")
    s_content = source.get("content")

    # Normalize to lists
    if isinstance(t_content, str):
        t_content = [{"type": "text", "text": t_content}] if t_content else []
    elif not isinstance(t_content, list):
        t_content = []

    if isinstance(s_content, str):
        s_content = [{"type": "text", "text": s_content}] if s_content else []
    elif not isinstance(s_content, list):
        s_content = []

    target["content"] = t_content + s_content


# ---------------------------------------------------------------------------
# 4. Anthropic upstream response  -->  OpenAI internal format
# ---------------------------------------------------------------------------

def anthropic_upstream_response_to_openai(
    anthropic_resp: Dict[str, Any],
    model: str,
) -> Dict[str, Any]:
    """Convert an Anthropic Messages API response to OpenAI Chat Completions format."""
    content_blocks = anthropic_resp.get("content", [])

    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    reasoning_parts: List[str] = []

    for block in content_blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id", _gen_tool_use_id()),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
            })
        elif btype == "thinking":
            reasoning_parts.append(block.get("thinking", ""))

    message: Dict[str, Any] = {"role": "assistant"}
    combined_text = "\n".join(text_parts) if text_parts else None
    message["content"] = combined_text

    if tool_calls:
        message["tool_calls"] = tool_calls
    if reasoning_parts:
        message["reasoning_content"] = "\n".join(reasoning_parts)

    stop_reason = anthropic_resp.get("stop_reason")
    usage = anthropic_resp.get("usage", {})

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": _map_stop_reason_to_finish_reason(stop_reason),
        }],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


# ---------------------------------------------------------------------------
# 5. Streaming: OpenAI SSE  -->  Anthropic SSE
# ---------------------------------------------------------------------------

async def openai_sse_to_anthropic_sse(
    openai_stream: AsyncIterator[bytes],
    model: str,
    input_tokens: int = 0,
) -> AsyncGenerator[bytes, None]:
    """Convert OpenAI SSE stream to Anthropic SSE event stream.

    Yields bytes in the format: ``event: <type>\\ndata: <json>\\n\\n``
    """
    msg_id = _gen_msg_id()
    emitted_start = False
    block_index = -1
    current_block_type: Optional[str] = None
    total_output_tokens = 0
    last_stop_reason = "end_turn"

    def _event(event_type: str, data: dict) -> bytes:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode("utf-8")

    def _emit_message_start() -> bytes:
        return _event("message_start", {
            "type": "message_start",
            "message": {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": input_tokens, "output_tokens": 0},
            },
        })

    def _emit_block_start(idx: int, block: dict) -> bytes:
        return _event("content_block_start", {
            "type": "content_block_start",
            "index": idx,
            "content_block": block,
        })

    def _emit_block_delta(idx: int, delta: dict) -> bytes:
        return _event("content_block_delta", {
            "type": "content_block_delta",
            "index": idx,
            "delta": delta,
        })

    def _emit_block_stop(idx: int) -> bytes:
        return _event("content_block_stop", {
            "type": "content_block_stop",
            "index": idx,
        })

    async for raw_chunk in openai_stream:
        # raw_chunk may contain multiple SSE lines
        for line in raw_chunk.decode("utf-8", errors="ignore").split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue

            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue

            # Skip internal metadata chunks
            if chunk.get("object") == "chat.completion.chunk.internal":
                continue

            choices = chunk.get("choices", [])
            if not choices:
                # might be a usage-only chunk
                if chunk.get("usage"):
                    total_output_tokens = chunk["usage"].get("completion_tokens", total_output_tokens)
                continue

            delta = choices[0].get("delta", {})
            finish_reason = choices[0].get("finish_reason")

            # Emit message_start on first real data
            if not emitted_start:
                emitted_start = True
                yield _emit_message_start()

            # -- reasoning_content (thinking block) --
            reasoning = delta.get("reasoning_content")
            if reasoning:
                if current_block_type != "thinking":
                    if current_block_type is not None:
                        yield _emit_block_stop(block_index)
                    block_index += 1
                    current_block_type = "thinking"
                    yield _emit_block_start(block_index, {
                        "type": "thinking",
                        "thinking": "",
                    })
                yield _emit_block_delta(block_index, {
                    "type": "thinking_delta",
                    "thinking": reasoning,
                })

            # -- text content --
            content = delta.get("content")
            if content:
                if current_block_type != "text":
                    if current_block_type is not None:
                        yield _emit_block_stop(block_index)
                    block_index += 1
                    current_block_type = "text"
                    yield _emit_block_start(block_index, {"type": "text", "text": ""})
                yield _emit_block_delta(block_index, {
                    "type": "text_delta",
                    "text": content,
                })

            # -- tool_calls --
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tc_id = tc.get("id")
                    tc_name = func.get("name")
                    tc_args = func.get("arguments", "")

                    # New tool_use block when id or name present
                    if tc_id or tc_name:
                        if current_block_type is not None:
                            yield _emit_block_stop(block_index)
                        block_index += 1
                        current_block_type = "tool_use"
                        yield _emit_block_start(block_index, {
                            "type": "tool_use",
                            "id": _remap_tool_call_id_to_anthropic(tc_id or _gen_tool_use_id()),
                            "name": tc_name or "",
                            "input": {},
                        })

                    if tc_args:
                        yield _emit_block_delta(block_index, {
                            "type": "input_json_delta",
                            "partial_json": tc_args,
                        })

            # -- finish_reason --
            if finish_reason:
                last_stop_reason = _map_finish_reason_to_stop_reason(finish_reason)

            # -- usage in chunk --
            chunk_usage = choices[0].get("usage") or chunk.get("usage")
            if chunk_usage:
                total_output_tokens = chunk_usage.get("completion_tokens", total_output_tokens)

    # Close any open block
    if emitted_start:
        if current_block_type is not None:
            yield _emit_block_stop(block_index)
    else:
        # No data came through; emit minimal response
        yield _emit_message_start()
        block_index = 0
        yield _emit_block_start(0, {"type": "text", "text": ""})
        yield _emit_block_stop(0)

    # message_delta + message_stop
    yield _event("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": last_stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": total_output_tokens},
    })
    yield _event("message_stop", {"type": "message_stop"})


# ---------------------------------------------------------------------------
# 6. Streaming: Anthropic upstream SSE  -->  OpenAI SSE
# ---------------------------------------------------------------------------

async def anthropic_sse_to_openai_sse(
    response_lines: AsyncIterator[str],
    model: str,
) -> AsyncGenerator[bytes, None]:
    """Convert Anthropic SSE events from upstream to OpenAI SSE format.

    ``response_lines`` should yield individual lines from the upstream response.
    """
    current_event_type: Optional[str] = None
    chat_id = f"chatcmpl-{uuid.uuid4().hex}"
    # track tool_use block index for streaming tool call deltas
    tool_block_indices: Dict[int, int] = {}  # anthropic block index -> openai tool index
    tool_index_counter = 0

    def _oai_chunk(delta: dict, finish_reason: Optional[str] = None) -> bytes:
        payload = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
        }
        return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

    async for line in response_lines:
        line = line.strip()
        if line.startswith("event:"):
            current_event_type = line[len("event:"):].strip()
            continue
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue

        event_type = current_event_type or data.get("type", "")
        current_event_type = None  # reset

        if event_type == "message_start":
            # Emit initial role chunk
            yield _oai_chunk({"role": "assistant", "content": ""})

        elif event_type == "content_block_start":
            block = data.get("content_block", {})
            if block.get("type") == "tool_use":
                idx = data.get("index", 0)
                tool_block_indices[idx] = tool_index_counter
                yield _oai_chunk({"tool_calls": [{
                    "index": tool_index_counter,
                    "id": block.get("id", _gen_tool_use_id()),
                    "type": "function",
                    "function": {"name": block.get("name", ""), "arguments": ""},
                }]})
                tool_index_counter += 1

        elif event_type == "content_block_delta":
            delta_obj = data.get("delta", {})
            dtype = delta_obj.get("type", "")

            if dtype == "text_delta":
                yield _oai_chunk({"content": delta_obj.get("text", "")})
            elif dtype == "thinking_delta":
                yield _oai_chunk({"reasoning_content": delta_obj.get("thinking", "")})
            elif dtype == "input_json_delta":
                idx = data.get("index", 0)
                oai_idx = tool_block_indices.get(idx, 0)
                yield _oai_chunk({"tool_calls": [{
                    "index": oai_idx,
                    "function": {"arguments": delta_obj.get("partial_json", "")},
                }]})

        elif event_type == "message_delta":
            delta_obj = data.get("delta", {})
            stop_reason = delta_obj.get("stop_reason")
            finish_reason = _map_stop_reason_to_finish_reason(stop_reason)
            yield _oai_chunk({}, finish_reason=finish_reason)

        elif event_type == "message_stop":
            yield b"data: [DONE]\n\n"

        elif event_type == "ping":
            pass  # keepalive, ignore

        elif event_type == "error":
            error_info = data.get("error", data)
            error_chunk = {"error": {"message": str(error_info), "type": "upstream_error"}}
            yield f"data: {json.dumps(error_chunk)}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# 7. Anthropic error response builder
# ---------------------------------------------------------------------------

def build_anthropic_error(
    error_type: str,
    message: str,
    status_code: int = 400,
) -> Dict[str, Any]:
    """Build an Anthropic-format error response body."""
    return {
        "type": "error",
        "error": {
            "type": error_type,
            "message": message,
        },
    }
