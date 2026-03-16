import asyncio
import json
import unittest

from anthropic_adapter import openai_sse_to_anthropic_sse


async def _collect_asyncgen(gen):
    out = []
    async for item in gen:
        out.append(item)
    return out


class TestOpenAISSEToAnthropicSSE(unittest.IsolatedAsyncioTestCase):
    async def test_converts_openai_error_chunk_to_anthropic_error_event(self):
        async def openai_stream():
            payload = {
                "error": {
                    "message": "Streaming tool call parsing failed",
                    "type": "tool_call_parse_error",
                    "code": "toolify_fc_parse_error",
                    "details": {"diagnosis": "Missing <function_calls> tag"},
                }
            }
            yield f"data: {json.dumps(payload)}\n\n".encode("utf-8")

        events = await _collect_asyncgen(openai_sse_to_anthropic_sse(openai_stream(), "test-model", input_tokens=1))
        self.assertGreaterEqual(len(events), 1)
        first = events[0].decode("utf-8", errors="ignore")
        self.assertIn("event: error", first)
        self.assertIn("\"type\": \"error\"", first)
        self.assertIn("Streaming tool call parsing failed", first)

        # Should terminate immediately on error (no trailing message_stop, etc.)
        combined = b"".join(events).decode("utf-8", errors="ignore")
        self.assertNotIn("event: message_stop", combined)

    async def test_emits_message_start_for_normal_text_stream(self):
        async def openai_stream():
            # Minimal OpenAI streaming chunks.
            yield b"data: " + json.dumps({
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "model": "test-model",
                "choices": [{"index": 0, "delta": {"content": "hi"}, "finish_reason": None}],
            }).encode("utf-8") + b"\n\n"
            yield b"data: " + json.dumps({
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "model": "test-model",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }).encode("utf-8") + b"\n\n"
            yield b"data: [DONE]\n\n"

        events = await _collect_asyncgen(openai_sse_to_anthropic_sse(openai_stream(), "test-model", input_tokens=0))
        combined = b"".join(events).decode("utf-8", errors="ignore")
        self.assertIn("event: message_start", combined)
        self.assertIn("event: message_stop", combined)

