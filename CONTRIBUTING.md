# 椰果启动器贡献指南

感谢你愿意改进椰果启动器。提交代码前请先搜索现有 Issue，确认没有重复工作；较大的功能或行为变更建议先开 Issue 说明目标和范围。

## 开发环境

推荐使用 Windows 10/11 和 Python 3.12：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

运行全部测试：

```powershell
.\run_tests.ps1
```

运行关键错误检查（CI 也会执行，只查语法错误和未定义名称，不做风格检查）：

```powershell
ruff check .
```

## 依赖更新

运行时依赖的直接来源维护在 `requirements.in`，`requirements.txt` 是由 pip-tools 生成的锁定文件。更新依赖时先修改 `requirements.in`，再重新生成锁定文件，不要手工编辑 `requirements.txt`：

```powershell
python -m piptools compile requirements.in
```

`setup.py` 也从 `requirements.in` 读取直接依赖，不要在其中维护第二份依赖列表。应用版本以 `config.py` 为唯一来源；开发分支保持 `dev`，发布工作流会写入 tag。

CI 使用 coverage 生成覆盖率报告。覆盖率用于发现本次修改缺少的测试分支，暂不设置全项目百分比门槛，以免上游快照中的既有未覆盖代码阻塞维护。

本仓库不使用 Git LFS：LFS 免费带宽配额按所有人的克隆下载计费，对社区分发的仓库是长期负担。CI 会运行 `python scripts/check_large_files.py`，拒绝超过 25 MiB 的新文件进入 Git 仓库；`assets/echo_model/echo.onnx` 是唯一的存量豁免，不要继续增加。需要分发新的大文件（例如模型权重）时，只能上传到 GitHub Release 资产，由程序在首次使用时下载并校验；不要提交到主仓库或更新仓库。

## 发布验收

发布前按 [发布验收清单](docs/RELEASE_CHECKLIST.md) 完成自动检查和实机测试。没有完成真实游戏验收时，不要仅凭单元测试结果创建正式版 tag。

## 提交要求

- 每个提交只处理一个清晰主题，不混入日志、缓存、截图或个人配置。
- 涉及识别、输入、任务流程或界面的修改，需要说明验证环境和结果。
- 新增功能应补充测试；修复问题应尽可能补充能复现旧行为的回归测试。
- 用户可见文案优先维护简体中文，并同步必要的翻译键。
- 提交前确认程序可以启动，并运行与改动相关的测试。

## Pull Request

PR 中请说明修改目的、实现范围、测试结果和已知限制。界面或识别结果发生变化时，请附截图或短录屏。提交代码即表示你同意按本项目的 AGPL-3.0 许可证发布贡献。
