# 第三方组件声明（THIRD_PARTY_NOTICES）

本项目使用以下第三方 Python 库，均按其各自许可证授权。本项目的代码本身按 `LICENSE`（MIT）授权。

| 依赖 | 版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| [aiohttp](https://github.com/aio-libs/aiohttp) | 3.14.3 | 异步 HTTP 客户端 | Apache License 2.0 |
| [lxml](https://lxml.de/) | 6.1.3 | HTML/XML 解析 | BSD-3-Clause |
| [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) | 4.15.0 | HTML 解析封装 | MIT License |

## 说明

- 上述版本为作者本地验证环境使用的版本，如需更新请先在本机验证签到功能。
- 各依赖的完整许可证文本分别参见其上游仓库的 LICENSE 文件。
- 源码仓库不包含第三方二进制文件；Windows 发行包包含 Python、Tcl/Tk 和运行依赖，相关许可证随包保存在 `licenses/` 及内嵌运行时中。
