"""Central constants and validated agent runtime configuration."""
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

LLM_PROVIDER = os.getenv("CRISIS_OS_LLM_PROVIDER", "local").lower()
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_DEFAULT = os.getenv("CRISIS_OS_MODEL_DEFAULT", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
MODEL_HEAVY = os.getenv("CRISIS_OS_MODEL_HEAVY", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
PORT = int(os.getenv("CRISIS_OS_PORT", "8081"))


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    provider: str
    model_id: str
    region: str
    timeout_seconds: int
    max_output_tokens: int
    allowed_model_ids: tuple[str, ...]
    allowed_regions: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "region": self.region,
            "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
            "allowed_model_ids": list(self.allowed_model_ids),
            "allowed_regions": list(self.allowed_regions),
        }


def load_runtime_config(path: str | Path | None = None) -> RuntimeConfig:
    config_path = Path(path) if path else Path(__file__).resolve().parents[2] / "config" / "agent-runtime.toml"
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        config = RuntimeConfig(
            provider=data.get("provider", ""),
            model_id=data.get("model_id", ""),
            region=data.get("region", ""),
            timeout_seconds=data.get("timeout_seconds", 0),
            max_output_tokens=data.get("max_output_tokens", 0),
            allowed_model_ids=tuple(data.get("allowed_model_ids", ())),
            allowed_regions=tuple(data.get("allowed_regions", ())),
        )
    except (OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid runtime configuration: {config_path}") from exc
    validate_runtime_config(config)
    return config


def validate_runtime_config(config: RuntimeConfig) -> RuntimeConfig:
    if not isinstance(config.provider, str) or config.provider not in ("bedrock", "local"):
        raise ConfigError(f"unsupported provider: {config.provider}")
    if not isinstance(config.model_id, str) or not config.model_id or config.model_id not in config.allowed_model_ids:
        raise ConfigError(f"model {config.model_id!r} is not allow-listed")
    if not isinstance(config.region, str) or not config.region or config.region not in config.allowed_regions:
        raise ConfigError(f"region {config.region!r} is not allow-listed")
    if (
        not isinstance(config.timeout_seconds, int)
        or isinstance(config.timeout_seconds, bool)
        or not isinstance(config.max_output_tokens, int)
        or isinstance(config.max_output_tokens, bool)
        or config.timeout_seconds <= 0
        or config.max_output_tokens <= 0
    ):
        raise ConfigError("timeout_seconds and max_output_tokens must be positive")
    if (
        not isinstance(config.allowed_model_ids, tuple)
        or not all(isinstance(value, str) and value for value in config.allowed_model_ids)
        or not isinstance(config.allowed_regions, tuple)
        or not all(isinstance(value, str) and value for value in config.allowed_regions)
    ):
        raise ConfigError("allow-lists must contain non-empty strings")
    return config


def agent_runtime() -> dict[str, object]:
    """Return the active runtime metadata without contacting a provider."""
    if LLM_PROVIDER == "local":
        return {
            "provider": "local",
            "model_id": "replay-deterministic-v1",
            "region": AWS_REGION,
        }
    return load_runtime_config().as_dict()
