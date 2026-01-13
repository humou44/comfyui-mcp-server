# API Reference

Complete technical reference for ComfyUI MCP Server tools, parameters, and behavior.

## Table of Contents

- [Generation Tools](#generation-tools)
- [Viewing Tools](#viewing-tools)
- [Configuration Tools](#configuration-tools)
- [Workflow Tools](#workflow-tools)
- [Parameters](#parameters)
- [Error Handling](#error-handling)
- [Limits and Constraints](#limits-and-constraints)

## Generation Tools

### generate_image

Generate images using Stable Diffusion workflows.

**Signature:**
```python
generate_image(
    prompt: str,
    seed: int | None = None,
    width: int | None = None,
    height: int | None = None,
    model: str | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    sampler_name: str | None = None,
    scheduler: str | None = None,
    denoise: float | None = None,
    negative_prompt: str | None = None,
    return_inline_preview: bool = False
) -> dict
```

**Required Parameters:**
- `prompt` (str): Text description of the image to generate

**Optional Parameters:**
- `seed` (int): Random seed. Auto-generated if not provided.
- `width` (int): Image width in pixels. Default: 512
- `height` (int): Image height in pixels. Default: 512
- `model` (str): Checkpoint model name. Default: "v1-5-pruned-emaonly.ckpt"
- `steps` (int): Number of sampling steps. Default: 20
- `cfg` (float): Classifier-free guidance scale. Default: 8.0
- `sampler_name` (str): Sampling method. Default: "euler"
- `scheduler` (str): Scheduler type. Default: "normal"
- `denoise` (float): Denoising strength (0.0-1.0). Default: 1.0
- `negative_prompt` (str): Negative prompt. Default: "text, watermark"
- `return_inline_preview` (bool): Include thumbnail in response. Default: False

**Returns:**
```json
{
  "asset_id": "uuid-string",
  "asset_url": "http://localhost:8188/view?filename=...",
  "image_url": "http://localhost:8188/view?filename=...",
  "filename": "ComfyUI_00265_.png",
  "subfolder": "",
  "folder_type": "output",
  "workflow_id": "generate_image",
  "prompt_id": "uuid-string",
  "tool": "generate_image",
  "mime_type": "image/png",
  "width": 512,
  "height": 512,
  "bytes_size": 497648,
  "inline_preview_base64": "data:image/webp;base64,..."  // if return_inline_preview=true
}
```

**Examples:**
```python
# Minimal call
result = generate_image(prompt="a cat")

# Full parameters
result = generate_image(
    prompt="cyberpunk cityscape",
    width=1024,
    height=768,
    model="sd_xl_base_1.0.safetensors",
    steps=30,
    cfg=7.5,
    sampler_name="dpmpp_2m",
    negative_prompt="blurry, low quality"
)
```

### generate_song

Generate audio using AceStep workflows.

**Signature:**
```python
generate_song(
    tags: str,
    lyrics: str,
    seed: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    seconds: int | None = None,
    lyrics_strength: float | None = None
) -> dict
```

**Required Parameters:**
- `tags` (str): Comma-separated descriptive tags (e.g., "electronic, ambient")
- `lyrics` (str): Full lyric text

**Optional Parameters:**
- `seed` (int): Random seed. Auto-generated if not provided.
- `steps` (int): Number of sampling steps. Default: 50
- `cfg` (float): Classifier-free guidance scale. Default: 5.0
- `seconds` (int): Audio duration in seconds. Default: 60
- `lyrics_strength` (float): Lyrics influence (0.0-1.0). Default: 0.99

**Returns:**
```json
{
  "asset_id": "uuid-string",
  "asset_url": "http://localhost:8188/view?filename=...",
  "filename": "ComfyUI_00001_.mp3",
  "subfolder": "",
  "folder_type": "output",
  "workflow_id": "generate_song",
  "prompt_id": "uuid-string",
  "tool": "generate_song",
  "mime_type": "audio/mpeg",
  "bytes_size": 1234567
}
```

## Viewing Tools

### view_image

View generated images inline in chat (thumbnail preview only).

**Signature:**
```python
view_image(
    asset_id: str,
    mode: str = "thumb",
    max_dim: int | None = None,
    max_b64_chars: int | None = None
) -> dict | FastMCPImage
```

**Parameters:**
- `asset_id` (str): Asset ID returned from generation tools
- `mode` (str): Display mode - `"thumb"` (default) or `"metadata"`
- `max_dim` (int): Maximum dimension in pixels. Default: 512
- `max_b64_chars` (int): Maximum base64 character count. Default: 100000

**Returns:**

**Mode: "thumb"** (default):
- Returns `FastMCPImage` object for inline display
- WebP format, automatically downscaled and optimized
- Size constrained to fit within `max_b64_chars` limit

**Mode: "metadata"**:
```json
{
  "asset_id": "uuid-string",
  "asset_url": "http://localhost:8188/view?filename=...",
  "mime_type": "image/png",
  "width": 512,
  "height": 512,
  "bytes_size": 497648,
  "workflow_id": "generate_image",
  "created_at": "2024-01-01T12:00:00",
  "expires_at": "2024-01-02T12:00:00"
}
```

**Supported Types:**
- Images only: PNG, JPEG, WebP, GIF
- Audio/video assets return error: use `asset_url` directly

**Error Responses:**
```json
{
  "error": "Asset not found or expired"
}
```

```json
{
  "error": "Asset type 'audio/mpeg' not supported for inline viewing. Supported types: image/png, image/jpeg, image/webp, image/gif"
}
```

**Examples:**
```python
# Generate and view
result = generate_image(prompt="a cat")
view_image(asset_id=result["asset_id"])

# Get metadata only
metadata = view_image(asset_id=result["asset_id"], mode="metadata")
```

## Configuration Tools

### list_models

List all available checkpoint models in ComfyUI.

**Signature:**
```python
list_models() -> dict
```

**Returns:**
```json
{
  "models": [
    "v1-5-pruned-emaonly.ckpt",
    "sd_xl_base_1.0.safetensors",
    ...
  ],
  "count": 7,
  "default": "v1-5-pruned-emaonly.ckpt"
}
```

### get_defaults

Get current effective defaults for image, audio, and video generation.

**Signature:**
```python
get_defaults() -> dict
```

**Returns:**
```json
{
  "image": {
    "width": 512,
    "height": 512,
    "model": "v1-5-pruned-emaonly.ckpt",
    "steps": 20,
    "cfg": 8.0,
    "sampler_name": "euler",
    "scheduler": "normal",
    "denoise": 1.0,
    "negative_prompt": "text, watermark"
  },
  "audio": {
    "steps": 50,
    "cfg": 5.0,
    "model": "ace_step_v1_3.5b.safetensors",
    "seconds": 60,
    "lyrics_strength": 0.99
  },
  "video": {
    "width": 1280,
    "height": 720,
    "steps": 20,
    "cfg": 8.0,
    "model": "wan2.2_vae.safetensors",
    "duration": 5,
    "fps": 16
  }
}
```

### set_defaults

Set runtime defaults for image, audio, and/or video generation.

**Signature:**
```python
set_defaults(
    image: dict | None = None,
    audio: dict | None = None,
    video: dict | None = None,
    persist: bool = False
) -> dict
```

**Parameters:**
- `image` (dict): Default values for image generation
- `audio` (dict): Default values for audio generation
- `video` (dict): Default values for video generation
- `persist` (bool): If True, write to config file. Default: False

**Returns:**
```json
{
  "success": true,
  "updated": {
    "image": {"success": true, "updated": {...}},
    "audio": {"success": true, "updated": {...}}
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "errors": [
    "Model 'invalid_model.ckpt' not found. Available models: ..."
  ]
}
```

**Examples:**
```python
# Set ephemeral defaults
set_defaults(
    image={"width": 1024, "height": 1024},
    audio={"seconds": 30}
)

# Persist to config file
set_defaults(
    image={"model": "sd_xl_base_1.0.safetensors"},
    persist=True
)
```

## Workflow Tools

### list_workflows

List all available workflows in the workflow directory.

**Signature:**
```python
list_workflows() -> dict
```

**Returns:**
```json
{
  "workflows": [
    {
      "id": "generate_image",
      "name": "Generate Image",
      "description": "Execute the 'generate_image' workflow.",
      "available_inputs": {
        "prompt": {"type": "str", "required": true, "description": "..."},
        "width": {"type": "int", "required": false, "description": "..."}
      },
      "defaults": {},
      "updated_at": null,
      "hash": null
    }
  ],
  "count": 2,
  "workflow_dir": "/path/to/workflows"
}
```

### run_workflow

Run any saved ComfyUI workflow with constrained parameter overrides.

**Signature:**
```python
run_workflow(
    workflow_id: str,
    overrides: dict | None = None,
    options: dict | None = None,
    return_inline_preview: bool = False
) -> dict
```

**Parameters:**
- `workflow_id` (str): Workflow ID (filename stem, e.g., "generate_image")
- `overrides` (dict): Parameter overrides
- `options` (dict): Reserved for future use
- `return_inline_preview` (bool): Include thumbnail. Default: False

**Returns:**
```json
{
  "asset_id": "uuid-string",
  "asset_url": "http://localhost:8188/view?filename=...",
  "workflow_id": "generate_image",
  "prompt_id": "..."
}
```

**Error Response:**
```json
{
  "error": "Workflow 'invalid_workflow' not found"
}
```

**Examples:**
```python
# Run workflow with overrides
run_workflow(
    workflow_id="generate_image",
    overrides={
        "prompt": "a cat",
        "width": 1024,
        "model": "sd_xl_base_1.0.safetensors"
    }
)
```

## Parameters

### Type System

Parameters are typed and automatically coerced:

- **String parameters**: `str` (default if no type specified)
- **Integer parameters**: `PARAM_INT_*` → `int`
- **Float parameters**: `PARAM_FLOAT_*` → `float`
- **Boolean parameters**: `PARAM_BOOL_*` → `bool`

**Type Coercion:**
- JSON-RPC may pass numbers as strings: `"512"` → `512` (int)
- Automatic conversion handles both string and numeric inputs

### Required vs Optional

**Required Parameters:**
- `prompt` (for image workflows)
- `tags` and `lyrics` (for audio workflows)

**Optional Parameters:**
- All others have defaults or are auto-generated (e.g., `seed`)

### Default Precedence

1. **Per-call values** (highest priority)
2. **Runtime defaults** (`set_defaults` tool)
3. **Config file** (`~/.config/comfy-mcp/config.json`)
4. **Environment variables** (`COMFY_MCP_DEFAULT_*`)
5. **Hardcoded defaults** (lowest priority)

## Error Handling

### Error Response Format

All tools return errors in consistent format:

```json
{
  "error": "Error message describing what went wrong"
}
```

### Common Errors

**Asset Not Found:**
```json
{
  "error": "Asset not found or expired"
}
```

**Invalid Workflow:**
```json
{
  "error": "Workflow 'invalid_workflow' not found"
}
```

**Invalid Model:**
```json
{
  "success": false,
  "errors": ["Model 'invalid.ckpt' not found. Available models: ..."]
}
```

**Unsupported Asset Type:**
```json
{
  "error": "Asset type 'audio/mpeg' not supported for inline viewing. Supported types: image/png, image/jpeg, image/webp, image/gif"
}
```

## Limits and Constraints

### Image Viewing

- **Maximum dimension**: 512px (default, configurable via `max_dim`)
- **Base64 budget**: 100KB (default, configurable via `max_b64_chars`)
- **Supported formats**: PNG, JPEG, WebP, GIF only
- **Automatic optimization**: Images are downscaled and re-encoded as WebP

### Asset Expiration

- **Default TTL**: 24 hours
- **Configurable**: `COMFY_MCP_ASSET_TTL_HOURS` environment variable
- **Automatic cleanup**: Expired assets are removed from registry

### Workflow Constraints

- **Path traversal protection**: Workflow IDs are sanitized
- **Directory restriction**: Only workflows in `workflows/` directory
- **Parameter validation**: Overrides constrained to declared parameters

### ComfyUI Integration

- **Polling interval**: 1 second
- **Maximum attempts**: 30 (configurable)
- **Timeout**: 30 seconds per request
