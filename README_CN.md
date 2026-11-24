# Lumina Workshop Registry

[English](README.md) · [简体中文](README_CN.md) · [公开目录地址](#公开目录地址) · [提交与更新模块](#提交与更新模块) · [本地校验](#本地校验) · [Workshop SDK](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK)

[Lumina Studio](https://github.com/lumina-layer-studio/Lumina-Layers) 创意工坊模块的公开签名目录。

[`modules/`](modules/) 中的每条记录对应由 [`@lumina/workshop-sdk`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK) 构建并发布在 GitHub Releases 上的不可变模块包。源记录经 CI 校验后编译为确定性 JSON 索引，并在发布前完成 Ed25519 签名。

## 在 Lumina Studio 中的作用

Lumina Studio 通过读取本目录展示可安装的官方与社区创意工坊模块，在安装前核对宿主兼容范围、权限声明与安装包 SHA-256 摘要，并支持后续更新与版本回退。官方模块与社区模块使用同一套打包格式、权限模型和生命周期约定。

## 公开目录地址

| 地址 | 说明 |
| --- | --- |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.json` | 已收录模块与版本的确定性 v1 目录索引 |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.sig` | `registry-v1.json` 的分离式 Ed25519 签名 |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.json` | 维护者已完成 Python 后端源码审核的精确模块版本列表 |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.sig` | `reviews-v1.json` 的分离式 Ed25519 签名 |

`.sig` 文件对完整 JSON 字节（含末尾换行符）签名。Lumina Studio 使用客户端内置的受信任公钥集验证签名；对应的公钥记录保存在 [`keys/`](keys/) 目录中，密钥轮换与应急流程见 [docs/key-rotation.md](docs/key-rotation.md)。

## 提交与更新模块

1. **打包并发布 Release：** 使用 [`Lumina-Workshop-SDK`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK) 开发模块，打包为 `<module-id>-<version>.lumina-workshop`，并在模块仓库发布正式的 GitHub Release（非草稿、非预发布标签）。
2. **编写或追加目录记录：** 按 [`schemas/module-source-v1.schema.json`](schemas/module-source-v1.schema.json) 在 `modules/<module-id>.json` 中填写版本标签、下载链接、字节大小、安装包 `sha256`、`manifestSha256`、兼容范围及权限声明（可选声明[工程快照能力](docs/project-snapshots.md)）。
3. **运行本地校验并向 `main` 提交 Pull Request。**

### 审核与发布流程

- **模块身份绑定与追加式版本记录：** 每个模块 ID 与其登记的 GitHub 仓库绑定，新版本以追加方式记录，已有历史版本保持不变。
- **PR 自动检查：** PR 工作流会两次下载新增 Release 资产以确认字节一致，静态核验安装包内容、清单摘要和 JSON Schema，并连续构建两次候选索引以确认输出完全一致。
- **维护者审核与自动签名：** 权限变更、宿主兼容范围调整或后端声明会直接体现在 PR diff 中。维护者审核合并到 `main` 后，由受保护的发布环境自动完成 Ed25519 签名并部署到 GitHub Pages。
- **Python 后端审核记录（`reviews-v1.json`）：** 对于声明本地 Python 后端（manifest v2）的模块，静态检查负责校验包结构；维护者针对具体版本完成后端代码审阅后，会通过 `backendReview` 字段单独登记并发布到 `reviews-v1.json`。

完整的版本规则、仓库重定向处理、后端审核与版本撤回说明见 [docs/review-policy.md](docs/review-policy.md)。

## 目录结构

```text
modules/    各模块的源记录（<module-id>.json）
schemas/    源记录、registry-v1 与 reviews-v1 的 JSON Schema
keys/       与 Lumina 内置受信公钥集对应的 Ed25519 公钥记录
src/        目录构建器、静态包检查器与 Schema 校验代码
scripts/    源校验、所有权差异检查与构建脚本
docs/       审核规则、密钥轮换与扩展能力说明
tests/      覆盖包检查、Schema 与签名流程的 Pytest 测试集
```

## 本地校验

需要 Python 3.12：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
PYTHONPATH=src .venv/bin/ruff check src scripts tests
PYTHONPATH=src .venv/bin/python -m pytest tests -v
PYTHONPATH=src .venv/bin/python scripts/validate_sources.py
```

## 许可证

本仓库的构建与校验代码采用 [MIT License](LICENSE)。目录所收录的各个创意工坊模块保留其各自的开源许可条款。
