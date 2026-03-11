"""Resolve ${VAR_NAME} placeholders in config values from environment."""
import os
import re
from dotenv import load_dotenv
from src.utils.exceptions import ConfigError

load_dotenv()

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


def get_env(var_name: str) -> str:
    """Get a required environment variable.

    Reads from os.environ (already populated by python-dotenv).
    Use this for secrets that live exclusively in .env and are NOT
    duplicated in config.yaml.

    Args:
        var_name: Name of the environment variable.

    Returns:
        The variable value.

    Raises:
        ConfigError: If the variable is not set.
    """
    val = os.environ.get(var_name)
    if val is None:
        raise ConfigError(
            f"Environment variable '{var_name}' is not set. "
            f"Add it to .env or export it.",
            key=var_name,
        )
    return val


def resolve_env_vars(value):
    """Recursively resolve ${VAR} placeholders in a config structure.

    Args:
        value: A string, dict, list, or primitive from parsed YAML.

    Returns:
        The same structure with all ${VAR} references replaced.

    Raises:
        ValueError: If a referenced env var is not set.
    """
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                raise ConfigError(
                    f"Environment variable '{var_name}' is not set. "
                    f"Add it to .env or export it.",
                    key=var_name,
                )
            return env_val
        return _ENV_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    return value