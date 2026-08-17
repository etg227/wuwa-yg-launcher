import re
from pathlib import Path


def project_version(config_path: str | Path = "config.py") -> str:
    """Read the application version without importing runtime dependencies."""
    content = Path(config_path).read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"{config_path} 中缺少 version")
    value = match.group(1).removeprefix("v")
    return "0.0.0.dev0" if value == "dev" else value


def runtime_requirements(requirements_path: str | Path = "requirements.in") -> list[str]:
    """Read direct dependencies from the canonical input file."""
    return [
        line.strip()
        for line in Path(requirements_path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
