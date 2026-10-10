"""零网络、零模型调用：检查文档 HTML、站内链接及下载包完整性。"""
from __future__ import annotations

from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import tarfile
import tomllib
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "website/.vitepress/dist"
BASE = "/RefractRouter/"


class Page(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.heading_count = 0
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "h1":
            self.heading_count += 1
        for key in ("href", "src"):
            if values.get(key):
                self.links.append(values[key])


def main() -> None:
    pages = {path: Page(path.read_text()) for path in DIST.rglob("*.html")}
    errors: list[str] = []
    for path, page in pages.items():
        html = path.read_text()
        if path.name != "404.html" and not page.heading_count:
            errors.append(f"正文缺少标题：{path.relative_to(DIST)}")
        if "/Users/chun-hsianglee" in html or "sk-or-v1-" in html or "apikey_" in html:
            errors.append(f"页面疑似包含私有路径或凭证：{path.relative_to(DIST)}")
        for value in page.links:
            url = urlsplit(value)
            if url.scheme in {"mailto", "tel", "data"}:
                continue
            if url.netloc and url.netloc != "aealab.github.io":
                continue
            target_path = unquote(url.path)
            if target_path.startswith(BASE):
                target = DIST / target_path.removeprefix(BASE)
            elif not target_path.startswith("/") and not url.netloc:
                target = path.parent / target_path if target_path else path
            else:
                continue
            if target.is_dir():
                target = target / "index.html"
            if not target.exists() and not target.suffix:
                target = target.with_suffix(".html")
            if not target.is_file():
                errors.append(f"链接不存在：{path.relative_to(DIST)} → {value}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                errors.append(f"锚点不存在：{path.relative_to(DIST)} → {value}")
    core = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    plugin = json.loads((ROOT / "validation/dsh/plugin/package.json").read_text())["version"]
    downloads = DIST / "downloads"
    assert not (downloads / ".gitignore").exists(), "下载目录不能携带忽略全部文件的构建规则"
    manifest = json.loads((downloads / "build-manifest.json").read_text())
    assert (manifest["coreVersion"], manifest["pluginVersion"]) == (core, plugin), "下载版本不匹配"
    for item in manifest["artifacts"]:
        path = downloads / item["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], "下载文件校验失败"
        assert path.stat().st_size == item["bytes"], "下载长度不匹配"
    with tarfile.open(downloads / f"dsh-refractrouter-validation-{plugin}.tgz") as archive:
        names = archive.getnames()
        assert "package/dist/entry.js" in names and "package/dist/client.js" in names
        package = json.load(archive.extractfile("package/package.json"))
        assert package["version"] == plugin and package["main"] == "dist/entry.js"
        assert not any("node_modules" in name or "/.env" in name for name in names)
    with zipfile.ZipFile(downloads / f"refractrouter-install-{core}.zip") as archive:
        checks = archive.read("SHA256SUMS.txt").decode().splitlines()
        for line in checks:
            expected, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected
        assert len(checks) == 2
    with zipfile.ZipFile(downloads / f"refractrouter-source-{core}.zip") as archive:
        required = ("pyproject.toml", "src/refractrouter/automatic_review.py",
                    "validation/dsh/plugin/src/entry.ts", "validation/dsh/plugin/scripts/build-client.mjs",
                    "data/model-profiles-v2.json", "README.md")
        for item in required:
            assert f"RefractRouter/{item}" in archive.namelist(), f"源码缺少 {item}"
    for relative in ("README.md", "docs/refractagent-local-quickstart.md", "validation/dsh/plugin/README.md"):
        text = (ROOT / relative).read_text()
        assert core in text and plugin in text, f"版本说明不一致：{relative}"
    source_count = len(list((ROOT / "website/content").rglob("*.md")))
    assert len(pages) >= source_count, "页面数量不足"
    assert not errors, "\n".join(sorted(set(errors)))
    print(json.dumps({"中文文档页": source_count, "HTML页": len(pages), "站内链接": "通过",
                      "分发包及SHA256": "通过", "版本": {"核心": core, "插件": plugin},
                      "模型调用": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
