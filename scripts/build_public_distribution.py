"""构建可公开下载的开发预览；只收集源码白名单，不包含运行记录或用户配置。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(rb"sk-or-v1-[a-f0-9]{64}"),
    re.compile(rb"apikey_[a-f0-9]{32}_[a-f0-9]{64}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{80,}-----END"),
)
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".mjs", ".json", ".md", ".yml", ".yaml", ".toml", ".css", ".html", ".svg", ".txt"}


def run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"构建失败：{args[0]}\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
    return result.stdout


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_bytes(path: Path) -> bytes:
    if path.is_symlink():
        target = path.resolve()
        try:
            relative = target.relative_to(ROOT)
        except ValueError as error:
            raise ValueError(f"不发布仓库外符号链接：{path.relative_to(ROOT)}") from error
        if relative.parts[0] not in {"src", "validation", "tests", "data"}:
            raise ValueError(f"符号链接不属于源码白名单：{path.relative_to(ROOT)}")
    data = path.read_bytes()
    if path.suffix in TEXT_SUFFIXES or path.name == "README.md":
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise ValueError(f"疑似凭证，停止发布：{path.relative_to(ROOT)}")
    return data


def source_files() -> list[Path]:
    tracked = run("git", "ls-files", "-z").split("\0")
    roots = ("src/", "tests/", "data/", "experiments/", "docs/", "validation/", "scripts/")
    files = {ROOT / item for item in tracked if item and item.startswith(roots)
             and Path(item).suffix in TEXT_SUFFIXES}
    # 本预览包含已验收、尚未提交的实现；不扫描 evidence、profile 或依赖目录。
    for folder in ("src/refractrouter", "tests", "validation/dsh/plugin/src", "website/content", "website/.vitepress"):
        files.update(path for path in (ROOT / folder).rglob("*") if path.is_file()
                     and path.suffix in TEXT_SUFFIXES
                     and not {"node_modules", "__pycache__", "cache", "dist"}.intersection(path.parts))
    files.update((ROOT / "docs").glob("*.md"))
    files.update((ROOT / "website/public").glob("*.svg"))
    files.update((ROOT / "website/public/examples").glob("*.json"))
    for item in ("README.md", "LICENSE", ".gitignore", "pyproject.toml", "uv.lock",
                 "website/package.json", "website/package-lock.json", "website/README.md",
                 "scripts/build_public_distribution.py", "scripts/validate_docs_site.py"):
        path = ROOT / item
        if path.is_file():
            files.add(path)
    forbidden = {".git", ".refractagent", ".env", "node_modules", "dist", ".test-dist", "__pycache__", "reports"}
    return sorted(path for path in files if path.is_file() and not forbidden.intersection(path.relative_to(ROOT).parts))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "website/public/downloads")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    core = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    plugin = json.loads((ROOT / "validation/dsh/plugin/package.json").read_text())["version"]
    run("uv", "build", "--wheel", "--out-dir", str(out))
    # uv 在产物目录写入 '*'；不能把它带入独立 Pages 分支后忽略全部下载。
    generated_ignore = out / ".gitignore"
    if generated_ignore.is_file() and generated_ignore.read_text().strip() == "*":
        generated_ignore.unlink()
    run("npm", "pack", "./validation/dsh/plugin", "--pack-destination", str(out))
    wheel = out / f"refractrouter-{core}-py3-none-any.whl"
    tgz = out / f"dsh-refractrouter-validation-{plugin}.tgz"
    if not wheel.is_file() or not tgz.is_file():
        raise RuntimeError("构建产物的名称或版本与配置不符")
    # 检查 wheel 中的代码与说明，避免凭证进入二进制分发。
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if any(pattern.search(archive.read(name)) for pattern in SECRET_PATTERNS):
                raise ValueError(f"wheel 疑似包含凭证：{name}")
    source = out / f"refractrouter-source-{core}.zip"
    paths = source_files()
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.writestr(f"RefractRouter/{path.relative_to(ROOT).as_posix()}", checked_bytes(path))
    bundle = out / f"refractrouter-install-{core}.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (wheel, tgz):
            archive.write(path, path.name)
        archive.writestr("README.md", checked_bytes(ROOT / "README.md"))
        archive.writestr("INSTALLATION.md", checked_bytes(ROOT / "docs/refractagent-local-quickstart.md"))
        archive.writestr("SHA256SUMS.txt", "".join(f"{digest(path)}  {path.name}\n" for path in (wheel, tgz)))
    artifacts = (wheel, tgz, source, bundle)
    (out / "SHA256SUMS.txt").write_text("".join(f"{digest(path)}  {path.name}\n" for path in artifacts))
    source_changes = run("git", "status", "--porcelain", "--",
                         *(str(path.relative_to(ROOT)) for path in paths))
    manifest = {
        "schemaVersion": "refractrouter-public-downloads-v1", "channel": "开发预览",
        "builtAt": datetime.now(timezone.utc).isoformat(), "coreVersion": core, "pluginVersion": plugin,
        "dshVersion": "0.1.5-rc.3", "baseCommit": run("git", "rev-parse", "HEAD").strip(),
        "includesWorkingTreeChanges": bool(source_changes),
        "sourceFiles": len(paths), "modelCalls": 0,
        "scope": "核心、插件、构建源码和说明；不包含用户配置、密钥、会话或运行产物",
        "artifacts": [{"file": path.name, "bytes": path.stat().st_size, "sha256": digest(path)} for path in artifacts],
    }
    (out / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
