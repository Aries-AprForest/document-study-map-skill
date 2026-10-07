# Document Study Map Skill

把 Word（`.docx`）或 PowerPoint（`.pptx`）学习笔记整理成可离线打开的交互思维导图网站。网站保留源文件的**加粗**和<u>下划线</u>重点、嵌入图片，提供章节切换、搜索、重点筛选、翻卡自测和浏览器本地进度。

仓库只包含通用 Skill、脚本和虚构示例，**不包含任何个人笔记或生成的网站**。

## 安装 Skill

将整个 `document-study-map-skill` 文件夹放入 Codex 的个人 `skills` 目录（Windows 示例：`C:\Users\<用户名>\.codex\skills\document-study-map-skill`），或放进项目的 `.agents/skills/` 中。重启或刷新 Codex 后，在请求中写 `$document-study-map`，并提供 Word/PPT 文件及想要整理的章节。

例如：

> 使用 `$document-study-map`，把这份 PPT 的第 2–4 章做成可离线打开的交互思维导图网站。加粗和下划线是重点，保留图表，保存为一个 HTML 文件。

Skill 会先读取文件、整理知识树，再生成网站并检查交互。`map.json` 中的知识树需要根据实际笔记人工核对；脚本只承担重复、确定性的提取与构建工作。

## 手动运行示例

需要 Python 3.10 或更新版本；提取和构建不依赖第三方 Python 包。

```bash
python scripts/extract_ooxml.py path/to/notes.docx --out work/source.json --assets work/images
# 阅读 work/source.json，参照 references/map-schema.md 编写 work/map.json
python scripts/build_site.py work/source.json work/map.json --out outputs/study-map.html
```

对 PPTX 使用同一提取命令。示例数据可直接试运行：

```bash
python scripts/build_site.py examples/source.json examples/map.json --out work/example.html
```

`work/`、`outputs/` 和用户源文件不会提交到 GitHub。发布前请确认没有将私人笔记、生成网页或提取出的图片加入仓库。

## 发布到 GitHub

1. 在 GitHub 新建**公开**仓库，建议命名为 `document-study-map-skill`；创建时不要勾选自动添加 README、`.gitignore` 或许可证，因为本文件夹已经包含这些文件。
2. 在本文件夹中运行下列命令。目标仓库已按 GitHub 用户名 `Aries-AprForest` 填好：

   ```bash
   git init
   git add .
   git commit -m "Add document study map skill"
   git branch -M main
   git remote add origin https://github.com/Aries-AprForest/document-study-map-skill.git
   git push -u origin main
   ```

3. 如果尚未登录 GitHub，`git push` 会提示你完成身份验证。也可以先解压发布包，再在仓库页面使用 **Add file → Upload files** 上传解压后的文件和子目录；不要把 ZIP 文件本身当作仓库内容上传。
4. 在 GitHub 仓库主页检查 `SKILL.md`、`scripts/`、`assets/`、`references/` 和 `examples/` 是否完整，并确认没有个人笔记。

本仓库采用 MIT 许可证。发布前可按你的偏好更换许可证。
