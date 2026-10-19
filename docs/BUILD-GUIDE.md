# Pan4dex 构建指南 —— 已迁移

构建文档已重组到 **[`docs/build/`](file:///c:/workspace/Pan4dex/docs/build/README.md)**，本页仅作重定向保留（历史链接不失效）。

## 从这里开始
👉 **[docs/build/README.md](build/README.md)** —— 总入口 + 决策树 + 唯一 Dockerfile 说明。

## 四种场景去哪看
| 场景 | 文档 |
|---|---|
| Windows 版 · 本机编 | [build/build-windows.md](build/build-windows.md) · W1 |
| Windows 版 · 从 Linux 经 SSH 到 Windows 远程编 | [build/build-windows.md](build/build-windows.md) · W2 |
| Linux 版 · 裸 Linux + Docker | [build/build-linux.md](build/build-linux.md) · L1 |
| Linux 版 · Windows + WSL2 + Docker | [build/build-linux.md](build/build-linux.md) · L2 |
| 退役的多机编排 / 断链脚本归档 | [build/legacy-multimachine.md](build/legacy-multimachine.md) |

## 统一入口脚本
`scripts/build.py`（薄编排，复用唯一 Dockerfile）：
```bash
python scripts/build.py linux    --dry-run
python scripts/build.py windows  --dry-run
python scripts/build.py windows --remote U@WIN --remote-path 'C:\workspace\Pan4dex' --dry-run
```

## 仍然有效的相邻文档
- `docs/development-guide.md` §5：开发环境构建
- `packaging/Dockerfile-linux`：生效的 Linux 构建镜像定义（`FROM` 通用基座 `packaging/Dockerfile-qt6-builder`）。基座可共享给其他 Qt6 项目，见 [build/qt6-builder-base.md](build/qt6-builder-base.md)。原 `docker/` 目录（`Dockerfile`/`entrypoint.sh`/`build.sh`/`README.md`）已移除，其废弃来龙去脉见 [build/legacy-multimachine.md](build/legacy-multimachine.md)；现行 Docker 构建见 [build/build-linux.md](build/build-linux.md)
- `docs/linux-gap.md`、`docs/gotchas.md`：Linux 已知差异与坑位清单

> 本页原有的“脚本入口分类表”“win54/win55/gti/230 多机编排”已迁入 [build/legacy-multimachine.md](build/legacy-multimachine.md)。
