# Lumina Workshop Registry

[English](README.md) · [简体中文](README_CN.md) · [公开目录地址](#公开目录地址) · [提交与更新模块](#提交与更新模块) · [本地校验](#本地校验) · [Workshop SDK](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK)

[Lumina Studio](https://github.com/lumina-layer-studio/Lumina-Layers) 创意工坊模块的公开签名目录。

Lumina Studio 通过本目录浏览基于 [`@lumina/workshop-sdk`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK) 构建的官方与社区模块，在安装前核对兼容版本、权限声明和安装包 SHA-256 摘要，并管理更新与回退。

## 公开目录地址

| 地址 | 说明 |
| --- | --- |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.json` | 已收录模块与版本的 v1 目录索引 |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/registry-v1.sig` | `registry-v1.json` 的分离式 Ed25519 签名 |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.json` | 维护者已完成 Python 后端源码审阅的精确模块版本列表 |
| `https://lumina-layer-studio.github.io/Lumina-Workshop-Registry/reviews-v1.sig` | `reviews-v1.json` 的分离式 Ed25519 签名 |

Lumina Studio 使用内置受信公钥集验证 `.sig` 签名；对应公钥记录位于 [`keys/`](keys/)（密钥轮换说明见 [docs/key-rotation.md](docs/key-rotation.md)）。

## 提交与更新模块

1. **打包并发布 Release：** 使用 [`Lumina-Workshop-SDK`](https://github.com/lumina-layer-studio/Lumina-Workshop-SDK) 打包 `<module-id>-<version>.lumina-workshop`，在模块仓库发布正式 GitHub Release（非草稿、非预发布标签）。
2. **编写或追加记录：** 按 [`schemas/module-source-v1.schema.json`](schemas/module-source-v1.schema.json) 在 `modules/<module-id>.json` 中填写版本标签、下载链接、字节大小、`sha256`、`manifestSha256`、兼容范围及权限声明（可选声明[工程快照能力](docs/project-snapshots.md)）。
3. **运行本地校验并向 `main` 提交 Pull Request。**

### 审核与发布流程

- 每个模块 ID 与登记的 GitHub 仓库绑定，新版本以追加方式记录，不改写既有版本。
- PR 工作流自动校验 JSON Schema、Release 摘要和包结构，权限或兼容范围变化会直接体现在 PR diff 中。
- 维护者审核合并到 `main` 后，工作流自动签名并发布更新。包含 Python 后端（manifest v2）的模块在完成具体版本源码审阅后，会通过 `backendReview` 记录到 `reviews-v1.json`。

详细规则见 [docs/review-policy.md](docs/review-policy.md)。

## 目录结构

```text
modules/    各模块源记录（<module-id>.json）
schemas/    源记录、registry-v1 与 reviews-v1 的 JSON Schema
keys/       Ed25519 公钥记录
src/        目录构建、包检查与校验代码
scripts/    校验与构建入口脚本
docs/       审核规则、密钥轮换与扩展说明
tests/      Pytest 测试集
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

本仓库工具代码采用 [MIT License](LICENSE)。目录收录的创意工坊模块保留各自许可。
