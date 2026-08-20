<div align="center">
  <img src="icons/icon.png" alt="椰果启动器 Logo" width="220">
  <h1>椰果启动器</h1>
  <p>面向《鸣潮》固定阵容与角色战斗轴的自动化工具。</p>

  [![版本](https://img.shields.io/github/v/release/etg227/wuwa-yg-launcher?include_prereleases&label=%E7%89%88%E6%9C%AC)](https://github.com/etg227/wuwa-yg-launcher/releases)
  [![平台](https://img.shields.io/badge/platform-Windows-blue)](#从源码运行)
  [![许可证](https://img.shields.io/badge/license-AGPL--3.0-green)](LICENSE.txt)
</div>

> [!WARNING]
> 椰果启动器会模拟键盘和鼠标操作，属于第三方自动化工具，可能违反游戏规则并导致账号处罚。请在使用前了解相关规则，并自行承担账号、数据与设备风险。

## 项目定位

椰果启动器基于 OKWW 的角色识别、战斗状态判断、技能状态判断与自动切人等基础能力开发，重点面向固定阵容的角色战斗逻辑和内置轴。

当前项目不提供外部轴文件导入或通用时间线播放器。轴直接写在角色代码与队伍轴逻辑中，由自动战斗框架根据当前角色、技能状态、协奏、变奏和队伍顺序执行。

这种实现方式的重点不是简单地按预设时间播放按键，而是让每个轴节点和实际角色状态结合，方便针对快速切人、技能衔接、变奏入场和特定队伍循环继续优化。

## 主要功能

- 自动识别当前队伍与角色位置。
- 使用 OKWW 角色逻辑执行普通战斗。
- 为指定三人队伍提供内置固定轴。
- 根据角色和轴节点控制出场顺序、技能、普攻、重击、声骸与共鸣解放。
- 支持角色配置，例如特定武器或角色玩法开关。
- 提供“角色代码”页面查看和修改角色行动逻辑。
- 提供开发者模式，在程序进程内加载自定义 Python 脚本。

## 内置轴

内置轴会在识别到对应队伍后，由自动战斗直接驱动，不需要额外导入文件。

目前仓库包含的队伍轴包括：

- 爱弥斯 / 达妮娅 / 千咲
- 秧秧 / 千咲 / 穗穗

具体动作与切人逻辑以 `src/char/` 下对应角色文件和队伍轴文件为准。

## 页面

项目界面只保留与打轴和调试直接相关的页面：

| 页面 | 用途 |
| --- | --- |
| 主页 | 连接游戏窗口、选择截图方式并启动 |
| 椰果启动器 | 查看内置轴、调整轴相关角色配置、开关自动战斗 |
| 角色代码 | 查看与自定义角色行动逻辑和队伍轴逻辑 |
| 开发者模式 | 编写、保存和重载自定义 Python 脚本 |
| 设置 | 调整游戏快捷键、角色配置和基础参数 |
| 关于 | 查看版本、项目说明和风险提示 |

## 自动战斗与内置轴

自动战斗使用 OKWW 的角色脚本作为基础。普通情况下，每个角色根据技能可用状态、冷却、协奏、Forte、变奏和角色定位决定行动。

对于已经实现专用队伍轴的阵容，角色会先检查当前队伍轴状态，再执行这一节点规定的动作，并把下一次切人优先级交给轴中指定的角色。

因此内置轴的结构大致是：

```text
识别队伍
  ↓
读取当前轴阶段和节点
  ↓
确认当前角色是否为该节点角色
  ↓
执行节点动作
  ↓
推进轴节点
  ↓
切到下一位指定角色
  ↓
继续循环
```

需要针对极限轴调整时，应优先修改对应队伍轴文件中的动作节点和输入间隔，而不是重新引入独立的外部时间线播放器。

## 下载与安装

前往 [GitHub Releases](https://github.com/etg227/wuwa-yg-launcher/releases) 下载 `wuwa-yg-win32-online-setup.exe`。

- Release 页面提供 Windows 在线安装程序。
- GitHub 自动生成的 `Source code` 压缩包不是 Windows 安装包。
- 安装包没有商业代码签名，Windows 可能显示“未知发布者”；请确认文件来自本仓库。

## 从源码运行

需要 Python 3.12。

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py
```

调试角色逻辑或内置轴时建议运行：

```powershell
py -3.12 main_debug.py
```

如果游戏以管理员权限运行，本程序也需要以管理员权限启动，否则键鼠输入可能无法正常发送到游戏窗口。

当前支持 16:9 分辨率，最低 1280×720。

## 开发者模式

启用“开发者模式”后，`configs/dev_scripts/` 下的 Python 脚本会在启动时自动执行，也可以在界面中编辑、保存并重载。

开发者脚本直接运行在程序进程内，因此错误脚本可能导致程序启动或运行异常。遇到问题时可先删除或修正对应脚本后重新启动。

## 代码结构

与角色战斗和固定轴最相关的目录：

```text
src/char/                角色自身战斗逻辑与队伍轴
src/combat/              战斗检测
src/task/AutoCombatTask.py
src/task/BaseCombatTask.py
src/gui/AxisControlTab.py
```

其中：

- `BaseCombatTask` 提供队伍读取、当前角色判断、技能/协奏状态和全局切人能力。
- `AutoCombatTask` 负责战斗期间持续调用当前角色的 `perform()`。
- `src/char/` 中的角色类决定具体技能与输出逻辑。
- 队伍专用轴通过共享状态控制当前阶段、节点和下一位角色。

## 项目来源与致谢

本项目基于 [OK-WW / ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves) 开发，底层自动化框架来自 [OK-Script](https://ok-script.com)。

感谢 OK-WW 与 OK-Script 的开发者提供基础框架、角色逻辑和自动化能力。

## 使用过的开发工具与模型

本项目开发过程中使用了 AI 模型与开发工具进行辅助。

| AI 模型 |
| --- |
| ChatGPT |
| Claude |

## 许可证

本项目沿用 [GNU Affero General Public License v3.0](LICENSE.txt)。分发修改版本或通过网络提供其功能时，请遵守 AGPL-3.0 的相关要求。
