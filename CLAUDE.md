# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Toolify is a middleware proxy that injects OpenAI-compatible function calling capabilities into LLMs that don't natively support it. It acts as an intermediary between client applications and upstream LLM APIs, injecting prompts and parsing tool calls from model responses.

## Development Commands

### Running the Application

**Python (Development):**
```bash
python main.py
```

**Docker Compose (Production):**
```bash
docker-compose up -d
```

### Configuration

Copy the example configuration before running:
```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` to configure upstream services, API keys, and features.

### Dependencies

Install Python dependencies:
```bash
pip install -r requirements.txt
```

Required packages: fastapi, uvicorn, httpx, pydantic, pyyaml, tiktoken

## Architecture

### Core Components

**main.py** - FastAPI application with three main responsibilities:
1. **Request Interception**: Intercepts `/v1/chat/completions` requests from clients
2. **Prompt Injection**: Injects system prompts instructing LLMs how to output function calls using XML format with a unique trigger signal
3. **Response Parsing**: Parses upstream responses for trigger signals and XML-formatted tool calls, transforms them into OpenAI `tool_calls` format

**config_loader.py** - Configuration management using Pydantic models:
- Validates YAML configuration structure
- Provides model-to-service routing mappings
- Handles model aliases (format: `alias:real_model_name`)
- Ensures exactly one default service exists

**admin.py** - Web-based admin interface:
- FastAPI router with HTML/JavaScript UI
- Manages upstream services, client keys, and feature toggles
- Reads/writes directly to `config.yaml`

### Key Architecture Patterns

**Model Routing**: Requests are routed to upstream services based on the model name. The system maintains a `MODEL_TO_SERVICE_MAPPING` dictionary built from config. If a model isn't found, the default service is used.

**Trigger Signal**: A random, unique trigger signal (e.g., `<Function_AB1c_Start/>`) is generated at startup to identify function call blocks in model responses. This prevents false positives from model-generated content.

**Tool Call Parsing**: Uses XML parsing (xml.etree.ElementTree) to extract function calls from model responses. The format is:
```
<trigger_signal/>
<function_calls>
  <function_call>
    <tool>tool_name</tool>
    <args_json><![CDATA[{"param": "value"}]]></args_json>
  </function_call>
</function_calls>
```

**Token Counting**: Uses tiktoken library with model-specific encodings. Supports o200k_base (newer models), cl100k_base (GPT-4/3.5), and prefix-based model detection.

**Streaming Support**: Handles both streaming and non-streaming responses. For streaming, buffers chunks to detect trigger signals and parse tool calls on the fly.

**Error Retry**: Optional feature (`enable_fc_error_retry`) that automatically retries when function call parsing fails, sending error details back to the model for correction.

### Configuration Structure

The config uses a three-tier validation system:
1. YAML parsing (PyYAML)
2. Pydantic model validation (ServerConfig, UpstreamService, ClientAuthConfig, FeaturesConfig)
3. Cross-field validation (e.g., ensuring default service exists, no duplicate models)

**Model Passthrough Mode**: When `model_passthrough: true`, all requests route to the 'openai' service regardless of model name.

**Key Passthrough Mode**: When `key_passthrough: true`, client API keys are forwarded to upstream instead of using configured keys.

## Important Implementation Details

### Message Role Conversion

The `convert_developer_to_system` feature (default: true) converts `developer` role messages to `system` role for compatibility with LLMs that don't support the developer role.

### Tool Result Context Enhancement

When tool results are provided (role=`tool`), Toolify builds an index from conversation history to include tool name and arguments alongside execution results. This provides better context to upstream models.

### JSON Schema Validation

Toolify includes a custom JSON Schema validator (`_validate_value_against_schema`) that validates tool arguments against declared schemas. Supports:
- Basic types, properties, required fields
- Arrays with items validation
- Enums, const values
- Combinators (anyOf, oneOf, allOf)
- String patterns, min/max length

### Admin Interface

The admin interface is a single-page application embedded in `admin.py` using Alpine.js. It provides:
- Dashboard with service/model/key statistics
- CRUD operations for upstream services
- Client key management with generation
- Feature toggles and configuration
- All changes write directly to `config.yaml`

## Testing Considerations

When testing function calling:
- Ensure the trigger signal appears exactly once on its own line
- Verify XML structure is well-formed
- Check that tool names match declared tools
- Validate arguments against JSON schemas
- Test with multiple tool calls in a single response
- Test streaming vs non-streaming responses

## Security Notes

- Client authentication uses API keys in `allowed_keys` list
- Admin interface requires valid client key for authentication
- API keys should never be committed to version control
- Use environment variable `TOOLIFY_CONFIG_PATH` to specify config location
