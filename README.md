<div align="center">
  <img src="icons/icon.png" alt="椰果启动器 Logo" width="220">
  <h1>椰果启动器</h1>
  <p>《鸣潮》打轴工具：基于 okww 角色逻辑的精简版 Wuwa Pilot，只保留打轴所需的功能。</p>

  [![版本](https://img.shields.io/github/v/release/etg227/wuwa-yg-launcher?include_prereleases&label=%E7%89%88%E6%9C%AC)](https://github.com/etg227/wuwa-yg-launcher/releases)
  [![平台](https://img.shields.io/badge/platform-Windows-blue)](#从源码运行)
  [![许可证](https://img.shields.io/badge/license-AGPL--3.0-green)](LICENSE.txt)
</div>

> [!WARNING]
> 椰果启动器会模拟键盘和鼠标操作，属于第三方自动化工具，可能违反游戏规则并导致账号处罚。请在使用前了解相关规则，并自行承担账号、数据与设备风险。

## 页面

只有六个页面，其余功能全部移除：

| 页面 | 用途 |
| --- | --- |
| 主页 | 连接游戏窗口、选择截图方式并启动 |
| 椰果启动器 | 导入/执行椰果轴，开关自动战斗（角色逻辑） |
| 角色代码 | 查看与自定义各角色的行动逻辑（轴以角色逻辑方式实现） |
| 开发者模式 | 用 Python 自己写轴或做其它更改（开启前需确认具备一定代码能力） |
| 设置 | 游戏快捷键、角色配置等全局设置 |
| 关于 | 版本与项目信息 |

自动战斗使用 okww 的角色脚本：每个角色的出手、切人、冷却与大招判断都由角色代码驱动。

## 下载与安装

前往 [GitHub Releases](https://github.com/etg227/wuwa-yg-launcher/releases) 下载 `wuwa-yg-win32-online-setup.exe` 启动器。

- Release 只上传在线启动器；`Source code` 压缩包不是 Windows 安装包。
- 安装包没有商业代码签名，Windows 可能显示“未知发布者”；请确认文件来自本仓库。

## 从源码运行

```powershell
pip install -r requirements.txt
python main.py
```

需要 Python 3.12。游戏以管理员运行时，本程序也需要以管理员身份运行。支持 16:9 多分辨率，最低 1280×720。调试模式：`python main_debug.py`。

## 开发者模式

在“开发者模式”页启用后，`configs/dev_scripts/` 下的 Python 脚本会在启动时自动执行，可在界面内编辑、保存并重载。脚本在程序进程内执行，请确保自己有一定的 Python 代码能力；出现问题先删除或修正脚本再重启。

## 项目来源与致谢

本项目由 [Wuwa Pilot](https://github.com/etg227/wuwa_pilot) 精简而来，Wuwa Pilot 基于 [ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves) 开发，自动化框架来自 [OK-Script](https://ok-script.com)，椰果启动器兼容 [WWCOMBO](https://nova.fb520.site/) 社区轴格式。

感谢 OK-WW、OK-Script、WWCOMBO 的开发者，以及所有分享社区轴的作者。社区轴内容归各自作者所有，本程序只解析用户主动导入的文件。

## 使用过的开发工具与模型

本项目开发过程中使用了 AI 模型与开发工具进行辅助。

| AI 模型 |
| --- |
| ChatGPT |
| Claude |

## 许可证

本项目沿用 [GNU Affero General Public License v3.0](LICENSE.txt)。分发修改版本或通过网络提供其功能时，请遵守 AGPL-3.0 的相关要求。
