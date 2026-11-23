"""Validate and package the uploadable specialized Agent with Python 3."""

from pathlib import Path
import ast
import re
import subprocess
import sys
import zipfile


REQUIRED_FILES = ("manifest.yaml", "bootstrap.py", "agent_definition.py", "README.md")


def validate_archive(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        names = set(archive.namelist())
        for name in (*REQUIRED_FILES, "form_generation/__init__.py"):
            if name not in names:
                raise ValueError(f"ZIP root is missing {name}")
        for name in names:
            if not name.endswith((".py", ".yaml", ".md")):
                continue
            try:
                text = archive.read(name).decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(f"{name}: ZIP member must contain UTF-8 source text") from error
            if "\x00" in text or text.startswith("%TSD-Header-###%"):
                raise ValueError(f"{name}: ZIP member contains binary content instead of source text")
            if not name.endswith(".py"):
                continue
            try:
                tree = ast.parse(text, filename=name)
            except (SyntaxError, ValueError) as error:
                raise ValueError(f"{name}: invalid Python source in ZIP: {error}") from error
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                parts = list(Path(name).parent.parts)
                if node.level > len(parts) + 1:
                    raise ValueError(f"{name}: relative import escapes the plugin package")
                if node.level > 1:
                    parts = parts[:-(node.level - 1)]
                modules = [node.module] if node.module else [alias.name for alias in node.names]
                if node.module:
                    package_name = "/".join(parts + node.module.split(".")) + "/__init__.py"
                    if package_name in names and not ast.parse(archive.read(package_name)).body:
                        # Empty package initializers expose imported names only through submodules.
                        modules.extend(f"{node.module}.{alias.name}" for alias in node.names if alias.name != "*")
                for module in modules:
                    target = "/".join(parts + module.split("."))
                    if f"{target}.py" not in names and f"{target}/__init__.py" not in names:
                        raise ValueError(f"{name}: missing relative import {target}.py")


def source_files(source):
    files = [source / name for name in REQUIRED_FILES]
    for directory, suffix in (("form_generation", ".py"), ("specs", ".md")):
        files.extend(sorted(
            path for path in (source / directory).rglob(f"*{suffix}")
            if not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(source).parts)
        ))
    return files


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
    files = source_files(source)
    contents = {path.relative_to(source).as_posix(): path.read_text(encoding="utf-8") for path in files}
    for name, text in contents.items():
        if name.endswith(".py"):
            ast.parse(text, filename=name)
    output = root / f"specialized-agent-package-{match.group(1)}.zip"
    temporary = output.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, text in contents.items():
                archive.writestr(name, text.encode("utf-8"))
        validate_archive(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Packaged {len(files)} files: {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
