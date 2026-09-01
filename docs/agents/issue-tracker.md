# Issue tracker: 本地 Markdown

本仓库的 spec（PRD）与 issue 以 markdown 文件形式存放在 `.scratch/` 下。

> 注：仓库公开发布到 GitHub 后，可切换为 GitHub Issues（用 `gh` CLI）。届时重跑
> setup 技能或直接改写本文件，并把 `.scratch/` 内的有效内容迁移过去。

## 约定

- 一个 feature 一个目录：`.scratch/<feature-slug>/`
- spec 是 `.scratch/<feature-slug>/spec.md`
- 实现 issue 一票一文件：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 起编号——禁止合并成一个大票文件
- triage 状态记录在每个 issue 文件顶部的 `Status:` 行（本仓库未安装 triage 技能，仅使用 `ready-for-agent` 等必要状态字符串）
- 评论与会话历史追加到文件底部 `## Comments` 标题下

## 当技能说"publish to the issue tracker"

在 `.scratch/<feature-slug>/` 下新建文件（目录不存在则先建）。

## 当技能说"fetch the relevant ticket"

读取对应路径的文件。用户通常会直接给出路径或编号。
