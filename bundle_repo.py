"""Bundle the repository's text sources into a single knowledge-base file.

File selection comes from `git ls-files`, not a filesystem walk, so the bundle
contains exactly what is committed: no `.pixi/` environment, no gitignored
operational config, no local logs. Repository plumbing that git does track,
such as `.github/`, is filtered out separately via EXCLUDE_PREFIXES.
"""

import subprocess
import sys
from pathlib import Path

VALID_EXTENSIONS = {'.py', '.sh', '.md', '.txt', '.yaml', '.yml', '.json', '.R'}

# Tracked paths under these prefixes are repository plumbing, not source
# material for the knowledge base.
EXCLUDE_PREFIXES = ('.github/',)

OUTPUT_NAME = "bcl_conversion_knowledge_base.txt"


def repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True,
    )
    return Path(result.stdout.strip())


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True, capture_output=True, text=True,
    )
    return sorted(name for name in result.stdout.split("\0") if name)


def main() -> int:
    root = repo_root()
    output_file = root / OUTPUT_NAME

    failures = 0
    written = 0

    with output_file.open("w", encoding="utf-8") as out:
        for name in tracked_files(root):
            if name.startswith(EXCLUDE_PREFIXES):
                continue
            file_path = root / name
            if file_path.suffix not in VALID_EXTENSIONS or file_path == output_file:
                continue
            if not file_path.exists():
                # Tracked in the index but absent from the working tree
                # (e.g. a staged deletion). Not a bundling error.
                print(f"skipping missing file: {name}", file=sys.stderr)
                continue

            try:
                contents = file_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"error reading {name}: {e}", file=sys.stderr)
                failures += 1
                continue

            out.write(f"\n\n{'=' * 80}\n")
            out.write(f"FILE: {name}\n")
            out.write(f"{'=' * 80}\n\n")
            out.write(contents)
            written += 1

    print(f"bundled {written} files into {output_file.name}", file=sys.stderr)

    if failures:
        print(f"{failures} file(s) could not be read", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
