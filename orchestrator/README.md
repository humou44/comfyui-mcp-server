## Orchestrator (v0)

Small, deterministic local LLM orchestrator that drives ComfyUI MCP tools for
image generation and iteration (generate -> tweak -> regenerate).

### Scope
- Image-only tools: `generate_image`, `regenerate`, `get_defaults`, `set_defaults`
- Transport: stdio (`server.py --stdio`)
- No inline image bytes by default

### Minimal config
Environment variables (example):
- `OLLAMA_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=qwen2.5:7b-instruct`
- `OLLAMA_TIMEOUT_S=300`
- `MCP_TRANSPORT=streamable-http`
- `MCP_URL=http://127.0.0.1:9000/mcp`
- `MCP_CMD=python server.py --stdio` (only needed for stdio)

### Tool schemas (current server)
Notes:
- `set_defaults` accepts extra keys and does not enforce numeric ranges.
- `return_inline_preview` exists on workflow tools; default is `false`.

#### `get_defaults` (response)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "get_defaults.response",
  "type": "object",
  "required": ["image", "audio", "video"],
  "additionalProperties": false,
  "properties": {
    "image": {
      "type": "object",
      "properties": {
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "steps": {"type": "integer"},
        "cfg": {"type": "number"},
        "sampler_name": {"type": "string"},
        "scheduler": {"type": "string"},
        "denoise": {"type": "number"},
        "model": {"type": "string"},
        "negative_prompt": {"type": "string"}
      },
      "additionalProperties": true
    },
    "audio": {
      "type": "object",
      "properties": {
        "steps": {"type": "integer"},
        "cfg": {"type": "number"},
        "sampler_name": {"type": "string"},
        "scheduler": {"type": "string"},
        "denoise": {"type": "number"},
        "seconds": {"type": "integer"},
        "lyrics_strength": {"type": "number"},
        "model": {"type": "string"}
      },
      "additionalProperties": true
    },
    "video": {
      "type": "object",
      "properties": {
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "steps": {"type": "integer"},
        "cfg": {"type": "number"},
        "sampler_name": {"type": "string"},
        "scheduler": {"type": "string"},
        "denoise": {"type": "number"},
        "negative_prompt": {"type": "string"},
        "duration": {"type": "integer"},
        "fps": {"type": "integer"},
        "model": {"type": "string"}
      },
      "additionalProperties": true
    }
  }
}
```

#### `set_defaults` (request)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "set_defaults.request",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "image": {"type": "object", "additionalProperties": true},
    "audio": {"type": "object", "additionalProperties": true},
    "video": {"type": "object", "additionalProperties": true},
    "persist": {"type": "boolean", "default": false}
  }
}
```

#### `set_defaults` (response)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "set_defaults.response",
  "oneOf": [
    {
      "type": "object",
      "required": ["success", "updated"],
      "properties": {
        "success": {"const": true},
        "updated": {
          "type": "object",
          "properties": {
            "image": {"type": "object"},
            "audio": {"type": "object"},
            "video": {"type": "object"}
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    {
      "type": "object",
      "required": ["success", "errors"],
      "properties": {
        "success": {"const": false},
        "errors": {"type": "array", "items": {"type": "string"}}
      },
      "additionalProperties": false
    }
  ]
}
```

#### `generate_image` (request)
Required: `prompt` only.
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "generate_image.request",
  "type": "object",
  "required": ["prompt"],
  "additionalProperties": false,
  "properties": {
    "prompt": {"type": "string"},
    "negative_prompt": {"type": "string"},
    "seed": {"type": "integer"},
    "width": {"type": "integer"},
    "height": {"type": "integer"},
    "steps": {"type": "integer"},
    "cfg": {"type": "number"},
    "sampler_name": {"type": "string"},
    "scheduler": {"type": "string"},
    "denoise": {"type": "number"},
    "model": {"type": "string"},
    "return_inline_preview": {"type": "boolean", "default": false}
  }
}
```

#### `regenerate` (request)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "regenerate.request",
  "type": "object",
  "required": ["asset_id"],
  "additionalProperties": false,
  "properties": {
    "asset_id": {"type": "string"},
    "seed": {"type": "integer", "description": "None=random; -1=keep original"},
    "return_inline_preview": {"type": "boolean", "default": false},
    "param_overrides": {
      "type": "object",
      "properties": {
        "prompt": {"type": "string"},
        "negative_prompt": {"type": "string"},
        "seed": {"type": "integer"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "steps": {"type": "integer"},
        "cfg": {"type": "number"},
        "sampler_name": {"type": "string"},
        "scheduler": {"type": "string"},
        "denoise": {"type": "number"},
        "model": {"type": "string"},
        "tags": {"type": "string"},
        "lyrics": {"type": "string"},
        "seconds": {"type": "integer"},
        "lyrics_strength": {"type": "number"}
      },
      "additionalProperties": true
    }
  }
}
```

#### `generate_image` / `regenerate` (response)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "generate_image.response",
  "type": "object",
  "required": [
    "asset_id",
    "asset_url",
    "image_url",
    "filename",
    "subfolder",
    "folder_type",
    "workflow_id",
    "prompt_id",
    "mime_type",
    "width",
    "height",
    "bytes_size"
  ],
  "additionalProperties": true,
  "properties": {
    "asset_id": {"type": "string"},
    "asset_url": {"type": "string"},
    "image_url": {"type": "string"},
    "filename": {"type": "string"},
    "subfolder": {"type": "string"},
    "folder_type": {"type": "string"},
    "workflow_id": {"type": "string"},
    "prompt_id": {"type": "string"},
    "mime_type": {"type": "string"},
    "width": {"type": "integer"},
    "height": {"type": "integer"},
    "bytes_size": {"type": "integer"},
    "tool": {"type": "string"},
    "inline_preview_base64": {"type": "string"},
    "inline_preview_mime_type": {"type": "string"},
    "image_base64": {"type": "string"},
    "image_mime_type": {"type": "string"}
  }
}
```

### Canonical tool results (for LLM context)
Keep responses tiny and consistent:
```json
{
  "ok": true,
  "tool": "generate_image",
  "data": {
    "asset_id": "uuid",
    "asset_url": "http://127.0.0.1:8188/view?...",
    "width": 1024,
    "height": 1024,
    "mime_type": "image/webp"
  }
}
```

`set_defaults` canonical example:
```json
{"ok": true, "tool": "set_defaults", "data": {"updated": {"image": {"width": 1024}}}}
```

### State loop (pseudocode)
```
function handle_user_turn(user_text, state):
  if state.defaults_cache is empty:
    raw = mcp_call("get_defaults", {})
    state.defaults_cache = raw
    append_tool_message(state, "get_defaults", raw)

  append_user_message(state, user_text)
  state.tool_calls_this_turn = 0
  state.invalid_tool_retries = 0

  while state.tool_calls_this_turn < MAX_TOOL_CALLS:
    prompt = build_system_prompt(state.defaults_cache) + recent_messages(state)
    model_text = llm_chat(prompt, temperature=0.2, top_p=0.9)

    call = parse_toolcall(model_text)
    if call is None:
      return finalize_text(model_text, state)

    validation = validate_toolcall(call)
    if not validation.ok:
      state.invalid_tool_retries += 1
      if state.invalid_tool_retries > MAX_INVALID_RETRIES:
        return "I couldn't make a valid tool call. What should I change next?"
      append_tool_error_message(state, validation.error)
      continue

    raw_result = execute_tool(call)
    canonical = canonicalize(call.tool, raw_result)

    if call.tool == "set_defaults" and canonical.ok:
      state.defaults_cache = merge_defaults_from_set(raw_result, state.defaults_cache)
    if call.tool in {"generate_image", "regenerate"} and canonical.ok:
      state.last_asset_id = canonical.data.get("asset_id")

    append_tool_message(state, call.tool, canonical)
    state.tool_calls_this_turn += 1

  return "I hit the tool-call limit. Tell me what to adjust next."
```

### Example session
```
user> generate a cinematic portrait
assistant> (toolcall: generate_image)
assistant> Generated. Asset: 1234-uuid. Want it warmer or sharper?
user> warmer lighting, slight contrast boost
assistant> (toolcall: regenerate with param_overrides)
assistant> Done. Asset: 5678-uuid. Any other tweaks?
```

### Basic eval harness
Run the canned tests (MCP + ollama required):
```
python -m orchestrator eval
```
Verbose output:
```
python -m orchestrator eval --verbose
```
Trace output:
```
python -m orchestrator eval --trace
```
Trace levels (JSONL):
```
python -m orchestrator eval --trace-level basic
python -m orchestrator eval --trace-level full
```
Trace to file:
```
python -m orchestrator eval --trace-level basic --trace-out trace.jsonl
```
Chat trace to file:
```
python -m orchestrator chat --trace-out chat-trace.jsonl
```

### Transport selection
Use streamable-http (default):
```
python -m orchestrator eval --mcp-transport streamable-http --mcp-url http://127.0.0.1:9000/mcp
```
Use stdio:
```
python -m orchestrator eval --mcp-transport stdio --mcp-cmd "python server.py --stdio"
```
Increase Ollama timeout if needed:
```
python -m orchestrator eval --ollama-timeout-s 300
```
