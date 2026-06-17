#!/usr/bin/env python3
"""
Generate a cryptographically secure INTERNAL_API_KEY for the Goals Service.

Usage:
    python scripts/generate_keys.py
"""

import secrets
import string

def generate_key(length: int = 64) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


if __name__ == "__main__":
    key = generate_key(64)
    print(f"\n✅  INTERNAL_API_KEY={key}")
    print("\nAdd this to your .env file and to the Auth Service .env under the same key name.\n")
