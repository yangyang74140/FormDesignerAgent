"""Validate and package the uploadable specialized Agent with Python 3."""

from pathlib import Path
import ast
import re
import subprocess
import sys
import zipfile


def main():
    root = Path(__file__).resolve().parent
    source = root / "specialized-agent-package"
    manifest = (source / "manifest.yaml").read_text(encoding="utf-8")
    match = re.search(r'^version: "([0-9]+\.[0-9]+\.[0-9]+)"$', manifest, re.MULTILINE)
    if not match:
        raise SystemExit("manifest.yaml must declare a semantic version")
    subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(source / "tests"), "-q"],
        cwd=root, check=True,
    )
    files = [source / name for name in ("manifest.yaml", "bootstrap.py", "agent_definition.py", "README.md", "release_config.json")]
    files += sorted((source / "form_generation").glob("*.py"))
    for path in files:
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    output = root / f"specialized-agent-package-{match.group(1)}.zip"
    temporary = output.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(source).as_posix())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise SystemExit("ZIP integrity check failed")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Packaged {len(files)} files: {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
