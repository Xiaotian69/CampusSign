# 第三方组件声明（THIRD_PARTY_NOTICES）

本项目使用以下第三方 Python 库，均按其各自许可证授权。本项目自有代码按 `LICENSE`（MIT）授权；`third_party/course_engine/` 另有非商业许可，见下文。

| 依赖 | 版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| [aiohttp](https://github.com/aio-libs/aiohttp) | 3.14.3 | 异步 HTTP 客户端 | Apache License 2.0 |
| [lxml](https://lxml.de/) | 6.1.3 | HTML/XML 解析 | BSD-3-Clause |
| [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) | 4.15.0 | HTML 解析封装 | MIT License |

课程学习（可选）额外使用，源码运行时通过 `requirements-course.txt` 安装，Windows 发行包已内置：

| 依赖 | 版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| [selenium](https://github.com/SeleniumHQ/selenium) | 4.51.0 | 浏览器自动化与驱动管理 | Apache License 2.0 |
| [openai](https://github.com/openai/openai-python) | 3.37.0 | 调用用户自备 Key 的 DeepSeek 兼容接口 | Apache License 2.0 |
| [colorama](https://github.com/tartley/colorama) | 0.4.6 | 日志着色 | BSD-3-Clause |
| [fonttools](https://github.com/fonttools/fonttools) | 4.67.0 | 题目字体解析 | MIT License |

## 说明

- 上述版本为作者本地验证环境使用的版本，如需更新请先在本机验证签到功能。
- 各依赖的完整许可证文本分别参见其上游仓库的 LICENSE 文件。
- 源码仓库不包含第三方二进制文件；Windows 发行包包含 Python、Tcl/Tk 和运行依赖，相关许可证随包保存在 `licenses/` 及内嵌运行时中。

## Xuexitong_shuake course engine

Copyright (c) 2025 Mortal004. Source: https://github.com/Mortal004/Xuexitong_shuake, commit `563bf27c5cb7a3eb659ed7b27b855d5e5c131c7c`.

Adapted files under `third_party/course_engine/` are subject to the full custom **non-commercial-only** [license](third_party/course_engine/LICENSE), not the root MIT license. Preserve that license and copyright with copies. [Adaptation details](third_party/course_engine/README.md).
