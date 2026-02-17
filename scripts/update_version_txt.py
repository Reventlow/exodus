#!/usr/bin/env python3
"""
Update version.txt with the next version number.

Increments the patch version by 1 (e.g., 0.1.0 -> 0.1.1).
"""

from pathlib import Path


def main():
    version_file = Path(__file__).parent.parent / "version.txt"

    if not version_file.exists():
        version_file.write_text("0.1.0\n")
        print("Created version.txt with version 0.1.0")
        return

    current_version = version_file.read_text().strip()

    try:
        parts = current_version.split(".")
        if len(parts) == 3:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            new_version = f"{major}.{minor}.{patch + 1}"
        else:
            new_version = f"{float(current_version) + 0.01:.2f}"
    except ValueError:
        new_version = "0.1.0"

    version_file.write_text(f"{new_version}\n")
    print(f"Updated version.txt: {current_version} -> {new_version}")


if __name__ == "__main__":
    main()
