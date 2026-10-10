# 文档站维护

这是 RefractRouter 的中文静态文档站，参考说明型产品文档的三栏布局。
使用 VitePress 1.6.4，导航与构建配置为 TypeScript；正文为 Markdown，主题为 CSS。

线上地址：https://aealab.github.io/RefractRouter/
`base` 固定为 `/RefractRouter/`，适配 GitHub 项目 Pages。

## 更新与构建

```bash
npm ci --prefix website
python3 scripts/build_public_distribution.py
npm run --prefix website build
python3 scripts/validate_docs_site.py
npm run --prefix website preview -- --port 4174
```

安装正文通过 include 复用 `docs/refractagent-local-quickstart.md`，避免维护两套命令。
修改核心或插件版本时，同时更新版本说明、下载链接、README 与安装指南，再构建匹配包。
`website/public/downloads/`、依赖、缓存与 `.vitepress/dist/` 不提交到源码分支。

## 发布

GitHub Pages 使用 `codex/docs-site` 分支根目录。仅发布 `.vitepress/dist/` 中的 HTML、
生成的前端资产、白名单下载包、首次安装草稿及 `.nojekyll`，不能上传整个工作目录。
该分支只承载生成站点，不用于合并运行时源码；源码与安装包匹配关系见下载清单。
构建过程会清除 uv 生成的下载目录忽略规则，发布前必须确认下载包确实进入 Git 树。

首次发布或后续更新前验证页面与下载的 SHA-256，并检查正文、搜索、侧边导航及窄屏布局。
发布后检查线上地址及下载文件。尚待合入的开发预览必须明确标示，不写成已经正式 Release。

## 公开范围

不发布 profile、凭证、会话、私有运行记录、用户界面截图或临时目录。
文档示意图为项目原创 SVG，不包含用户会话。历史实验仅链接已公开报告并保留原结论。
能力说明区分已接通、已验证、实验与未完成；模拟安装不能充当真实模型质量验收。
