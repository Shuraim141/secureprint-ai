#!/usr/bin/env python3
"""Create .env from .env.example with freshly generated secrets (standard library only).

Usage: python scripts/init_env.py [--force]
"""
import base64
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_env_text(example_text: str) -> str:
    generated = {
        "JWT_SECRET": secrets.token_urlsafe(48),
        "MASTER_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
    }
    lines = []
    for line in example_text.splitlines():
        key = line.split("=", 1)[0].strip()
        lines.append(f"{key}={generated[key]}" if key in generated and "=" in line else line)
    return "\n".join(lines) + "\n"


def main() -> int:
    target = ROOT / ".env"
    if target.exists() and "--force" not in sys.argv:
        print(f"{target} already exists. Use --force to overwrite (this invalidates old tokens "
              "and makes previously encrypted files undecryptable).")
        return 1
    target.write_text(build_env_text((ROOT / ".env.example").read_text()), encoding="utf-8")
    target.chmod(0o600)
    print(f"Created {target} with new JWT_SECRET and MASTER_KEY (file mode 600).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
