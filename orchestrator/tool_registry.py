"""Tool allowlist and argument validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


ALLOWED_TOOLS = {
    "get_defaults",
    "set_defaults",
    "generate_image",
    "regenerate",
}

IMAGE_DEFAULT_KEYS = {
    "width",
    "height",
    "steps",
    "cfg",
    "sampler_name",
    "scheduler",
    "denoise",
    "model",
    "negative_prompt",
}

REGENERATE_OVERRIDE_KEYS = {
    "prompt",
    "negative_prompt",
    "width",
    "height",
    "steps",
    "cfg",
    "sampler_name",
    "scheduler",
    "denoise",
    "model",
    "tags",
    "lyrics",
    "seconds",
    "lyrics_strength",
}

GENERATE_KEYS = IMAGE_DEFAULT_KEYS | {"prompt", "seed", "return_inline_preview"}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: Optional[str] = None


def _expect_type(name: str, value: Any, expected: Iterable[type]) -> Optional[str]:
    if not isinstance(value, tuple(expected)):
        return f"'{name}' must be {', '.join(t.__name__ for t in expected)}"
    return None


def validate_toolcall(tool: str, args: Dict[str, Any]) -> ValidationResult:
    if tool not in ALLOWED_TOOLS:
        return ValidationResult(False, f"Tool '{tool}' is not allowed")

    if tool == "get_defaults":
        if args:
            return ValidationResult(False, "get_defaults takes no arguments")
        return ValidationResult(True)

    if tool == "set_defaults":
        allowed_keys = {"image", "audio", "video", "persist"}
        unknown = set(args.keys()) - allowed_keys
        if unknown:
            return ValidationResult(False, f"Unknown keys for set_defaults: {sorted(unknown)}")
        if "persist" in args:
            err = _expect_type("persist", args["persist"], [bool])
            if err:
                return ValidationResult(False, err)
        for namespace in ("image", "audio", "video"):
            if namespace in args:
                if not isinstance(args[namespace], dict):
                    return ValidationResult(False, f"'{namespace}' must be an object")
                if namespace == "image":
                    unknown_keys = set(args[namespace].keys()) - IMAGE_DEFAULT_KEYS
                    if unknown_keys:
                        return ValidationResult(False, f"Unknown image defaults: {sorted(unknown_keys)}")
        return ValidationResult(True)

    if tool == "generate_image":
        unknown = set(args.keys()) - GENERATE_KEYS
        if unknown:
            return ValidationResult(False, f"Unknown keys for generate_image: {sorted(unknown)}")
        if "prompt" not in args:
            return ValidationResult(False, "generate_image requires 'prompt'")
        err = _expect_type("prompt", args["prompt"], [str])
        if err:
            return ValidationResult(False, err)
        for key in ("width", "height", "steps", "seed"):
            if key in args:
                err = _expect_type(key, args[key], [int])
                if err:
                    return ValidationResult(False, err)
        for key in ("cfg", "denoise"):
            if key in args:
                err = _expect_type(key, args[key], [int, float])
                if err:
                    return ValidationResult(False, err)
        for key in ("negative_prompt", "sampler_name", "scheduler", "model"):
            if key in args:
                err = _expect_type(key, args[key], [str])
                if err:
                    return ValidationResult(False, err)
        if "return_inline_preview" in args:
            err = _expect_type("return_inline_preview", args["return_inline_preview"], [bool])
            if err:
                return ValidationResult(False, err)
        return ValidationResult(True)

    if tool == "regenerate":
        allowed = {"asset_id", "seed", "return_inline_preview", "param_overrides"}
        unknown = set(args.keys()) - allowed
        if unknown:
            return ValidationResult(False, f"Unknown keys for regenerate: {sorted(unknown)}")
        if "asset_id" not in args:
            return ValidationResult(False, "regenerate requires 'asset_id'")
        err = _expect_type("asset_id", args["asset_id"], [str])
        if err:
            return ValidationResult(False, err)
        if "seed" in args:
            err = _expect_type("seed", args["seed"], [int])
            if err:
                return ValidationResult(False, err)
        if "return_inline_preview" in args:
            err = _expect_type("return_inline_preview", args["return_inline_preview"], [bool])
            if err:
                return ValidationResult(False, err)
        if "param_overrides" in args:
            if not isinstance(args["param_overrides"], dict):
                return ValidationResult(False, "'param_overrides' must be an object")
            unknown_keys = set(args["param_overrides"].keys()) - REGENERATE_OVERRIDE_KEYS
            if unknown_keys:
                return ValidationResult(False, f"Unknown param_overrides: {sorted(unknown_keys)}")
            overrides = args["param_overrides"]
            for key in ("width", "height", "steps", "seconds"):
                if key in overrides:
                    err = _expect_type(key, overrides[key], [int])
                    if err:
                        return ValidationResult(False, err)
            for key in ("cfg", "denoise", "lyrics_strength"):
                if key in overrides:
                    err = _expect_type(key, overrides[key], [int, float])
                    if err:
                        return ValidationResult(False, err)
            for key in ("prompt", "negative_prompt", "sampler_name", "scheduler", "model", "tags", "lyrics"):
                if key in overrides:
                    err = _expect_type(key, overrides[key], [str])
                    if err:
                        return ValidationResult(False, err)
        return ValidationResult(True)

    return ValidationResult(False, f"Unhandled tool: {tool}")

