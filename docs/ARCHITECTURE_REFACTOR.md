# Architecture Refactor Summary

## Overview

This refactor implements the architectural improvements recommended to make the MCP server a "thin adapter" that leverages ComfyUI's native APIs while providing AI-friendly conveniences.

## Key Changes

### 1. Stable Asset Identity

**Before:** Assets identified by URL (brittle, breaks with hostname changes)
```python
asset_url = "http://localhost:8188/view?filename=..."
```

**After:** Assets identified by `(filename, subfolder, type)` (stable, portable)
```python
filename = "image_12345.png"
subfolder = ""
folder_type = "output"
# URL computed on-the-fly from base_url
```

**Benefits:**
- Works across different ComfyUI instances (localhost, 127.0.0.1, different ports)
- Survives ComfyUI restarts
- No "thor:8188" hostname bugs

### 2. Full Provenance Storage

**Added to AssetRecord:**
- `comfy_history`: Full `/history/{prompt_id}` response snapshot
- `submitted_workflow`: Original workflow JSON submitted to ComfyUI

**Benefits:**
- Free reproducibility (can regenerate with exact parameters)
- Debugging becomes trivial (see exactly what was submitted)
- Enables future `regenerate()` tool

### 3. Direct ComfyUI API Access

**New ComfyUIClient methods:**
- `get_queue()` - Direct passthrough to `/queue`
- `get_history(prompt_id)` - Direct passthrough to `/history`
- `cancel_prompt(prompt_id)` - Cancel jobs

**Benefits:**
- No reimplementing ComfyUI's queue logic
- No sync issues (ComfyUI is source of truth)
- Minimal code surface

### 4. Job Management Tools

**New MCP tools:**
- `get_queue_status()` - Check queue state (async awareness)
- `get_job(prompt_id)` - Poll job completion
- `list_assets(limit, workflow_id)` - Browse generated assets (AI memory)
- `get_asset_metadata(asset_id)` - Get full provenance
- `cancel_job(prompt_id)` - Cancel queued/running jobs

**Benefits:**
- AI agents can check job status without blocking
- Enables browsing work history for iteration
- Full context for regeneration decisions

## Technical Details

### URL Encoding

Special characters in filenames are now properly URL-encoded:
```python
from urllib.parse import quote
encoded_filename = quote(filename, safe='')
```

### Lookup Performance

Asset lookups are O(1) using dict:
```python
_asset_key_to_id: Dict[str, str]  # (filename, subfolder, type) -> asset_id
```

### Error Handling

Improved error handling in `get_job()`:
- Handles missing prompt_ids gracefully
- Distinguishes between "not found" and "error" states
- Provides helpful error messages
- Handles ComfyUI unavailability

## Backward Compatibility

**Note:** This is a breaking change for the internal API, but:
- Old `asset_id` values still work (lookup by ID unchanged)
- Asset URLs are computed on-the-fly, so they still work
- Old assets in registry will naturally expire (24h TTL)
- No migration needed for v1 (fresh start)

## Validation Tests

### Test 1: Asset Identity Stability
```python
# Generate on localhost:8188
result1 = generate_image(prompt="test")
asset_id = result1["asset_id"]

# Change COMFYUI_URL to 127.0.0.1:8188
# Asset should still work
view_image(asset_id=asset_id)  # Should work
```

### Test 2: Queue Status
```python
# Submit long job
result = generate_song(lyrics="long", seconds=120)

# Check queue immediately
queue = get_queue_status()
assert len(queue["queue_running"]) > 0 or len(queue["queue_pending"]) > 0
```

### Test 3: Job Polling
```python
result = generate_image(prompt="test")
prompt_id = result["prompt_id"]

job = get_job(prompt_id)
assert job["status"] in ["completed", "running", "queued", "error", "not_found"]
```

### Test 4: Asset Browsing
```python
# Generate multiple
generate_image(prompt="cat")
generate_image(prompt="dog")

# List them
assets = list_assets(limit=10)
assert len(assets["assets"]) >= 2
assert all("filename" in a for a in assets["assets"])
```

### Test 5: Metadata Provenance
```python
result = generate_image(prompt="sunset", steps=30, cfg=8.0)
metadata = get_asset_metadata(result["asset_id"])

assert metadata["submitted_workflow"] is not None
assert metadata["comfy_history"] is not None
assert metadata["filename"] is not None
```

### Test 6: Cancellation
```python
# Submit long job
result = generate_song(seconds=120, ...)
prompt_id = result["prompt_id"]

# Cancel
cancel_job(prompt_id)

# Verify
queue = get_queue_status()
# Should not appear in queue
```

## Files Changed

- `models/asset.py` - Refactored to use stable identity
- `managers/asset_registry.py` - Updated lookup and registration
- `comfyui_client.py` - Added direct API methods, URL encoding
- `tools/helpers.py` - Updated to use new registration
- `tools/asset.py` - Updated to use computed URLs
- `tools/job.py` - **NEW** - Job management tools
- `server.py` - Register new tools, pass base_url to registry
- `README.md` - Updated documentation

## Performance Considerations

### History Snapshot Size

`comfy_history` can be large for complex workflows. For v1:
- Stored as-is (no compression)
- TTL-based expiration (24h) limits growth
- Future: Consider compression or selective field storage

### Lookup Performance

- Asset by ID: O(1) via `_assets` dict
- Asset by identity: O(1) via `_asset_key_to_id` dict
- List assets: O(n log n) for sorting (n = total assets, typically small)

## Future Enhancements

1. **Regenerate Tool**: Use stored `submitted_workflow` to regenerate with overrides
2. **History Compression**: Compress large history snapshots
3. **Session Filtering**: Filter `list_assets()` by session/user
4. **Rate Limiting**: Prevent spam polling in `get_job()`
5. **SQLite Persistence**: Optional persistent storage (YAGNI for v1)

## Migration Notes

For existing deployments:
- Old assets will naturally expire (24h TTL)
- No manual migration needed
- New assets use stable identity automatically
