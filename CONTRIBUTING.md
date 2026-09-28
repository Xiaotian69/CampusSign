# 贡献指南（Contributing）

欢迎学弟学妹参与 CxSign 的维护。本指南说明如何报告 Bug、补充地点、建议功能与提交 PR。

## 报告 Bug

1. 在 [Issues](https://github.com/Xiaotian69/CampusSign/issues) 新建「Bug 报告」；
2. 描述操作系统、Python 版本、复现步骤与报错信息；
3. **提交前务必遮挡账号、密码、Cookie、Token、学号、个人 IP 等隐私信息**；
4. 截图前请先模糊处理个人与学校账号信息。

## 补充地点

- 地点补充只需要「完整地点名称 + 百度 BD-09 经纬度」，**不需要账号、密码或 Cookie**；
- 坐标来源请注明（例如百度地图拾取坐标系）；若为 WGS-84 / GCJ-02 请先转换。

## 建议功能

- 在 [Issues](https://github.com/Xiaotian69/CampusSign/issues) 新建「功能建议」；
- 说明使用场景与期望行为；
- 请勿建议违反学校或平台规定的功能。

## 提交 PR

1. Fork 本仓库并创建独立分支；
2. 保持改动聚焦，一次 PR 只做一件事；
3. 核心行为不可破坏：运行 `python -m unittest test_desktop test_desktop_ui -v` 确保全部通过；
4. 新增逻辑请补充对应测试；
5. 提交信息清晰（如 `feat: ...` / `fix: ...` / `docs: ...`）。

## 隐私红线

- 不得提交任何真实账号、密码、Cookie、Token、学号、个人 IP；
- 不得提交本地日志或含隐私的截图；
- 本地配置文件（`user.json`、`*.local.json`、`config.json`）已被 `.gitignore` 排除，请勿强制添加。
