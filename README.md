# ip2region-xdb

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Update XDB](https://github.com/fa1seut0pia/ip2region-xdb/actions/workflows/update-xdb.yml/badge.svg)](https://github.com/fa1seut0pia/ip2region-xdb/actions/workflows/update-xdb.yml)

将 GeoLite2 mmdb 文件转换为 [ip2region](https://github.com/lionsoul2014/ip2region) xdb 源文件格式的转换工具。

> 💡 **直接使用**: 如果你只需要 xdb 文件，可以直接从 [Releases](https://github.com/fa1seut0pia/ip2region-xdb/releases) 下载，无需自行构建。

## ✨ 特性

- 🌍 **多数据源融合** - 整合 GeoLite2、GeoCN 和内网 IP 数据
- 🇨🇳 **中国 IP 优化** - 使用 GeoCN 提供更精确的中国 IP 地理位置
- 🏠 **内网 IP 识别** - 自动识别并标记内网/保留地址
- 🌐 **双栈支持** - 同时支持 IPv4 和 IPv6 地址
- 🏷️ **ASN 中文化** - 将常见 ASN 编号转换为中文运营商名称

## 📦 数据源

| 数据源 | 用途 
|--------|------|
| [内网IP.txt](data/内网IP.txt) | 内网/保留地址 |
| [GeoCN](https://github.com/ljxi/GeoCN) | 中国 IP 数据 |
| [GeoLite2](https://github.com/P3TERX/GeoLite.mmdb) | 非中国 IP 数据 |

## 🚀 快速开始

### 环境要求

- Python 3.10+
- curl（用于下载数据库）

### 安装

```bash
# 克隆仓库
git clone https://github.com/fa1seut0pia/ip2region-xdb.git
cd ip2region-xdb

# 安装依赖
pip install -e .
# 或使用 uv
uv sync
```

### 下载数据库

```bash
# 下载所有 mmdb 数据库文件
./download_mmdb.sh
```

这将下载以下文件到 `data/` 目录：
- `GeoLite2-ASN.mmdb` - ASN 数据库
- `GeoLite2-City.mmdb` - 城市级别地理数据
- `GeoLite2-Country.mmdb` - 国家级别地理数据
- `GeoCN.mmdb` - 中国 IP 详细数据
- `provinces.json` / `cities.json` / `areas.json` - 中国行政区划数据（用于展开 `division_code`）

### 运行转换

```bash
# 使用默认参数转换
python -m ip2region_xdb
```

## 📄 输出格式

转换后生成的源文件格式为：

```
起始IP|结束IP|洲|国家|省份|城市|区县|ISP|网络类型
```

示例：
```
1.0.0.0|1.0.0.255|亚洲|澳大利亚|昆士兰|布里斯班||Cloudflare|AS13335
223.5.5.0|223.5.5.255|亚洲|中国|浙江省|杭州市||阿里云|
10.0.0.0|10.255.255.255|内网IP|内网IP|内网IP|私有网络A类|||
```

输出文件：
- `data/ipv4_source.txt` - IPv4 源文件
- `data/ipv6_source.txt` - IPv6 源文件

## 🏗️ 项目结构

```
ip2region-xdb/
├── src/
│   └── ip2region_xdb/
│       ├── __init__.py
│       ├── __main__.py
│       └── converter.py  # 核心转换器
├── data/
│   └── 内网IP.txt        # 内网/保留地址定义
├── download_mmdb.sh      # 数据库下载脚本
├── pyproject.toml        # 项目配置
├── requirements.txt      # 依赖列表
└── README.md
```

## 🔧 技术细节

### ASN 映射

内置常见 ASN 到中文名称的映射，包括：

- **三大运营商**: 中国电信、中国移动、中国联通
- **云服务商**: 阿里云、腾讯云、华为云、百度云等
- **国际服务商**: Cloudflare、AWS、Google Cloud 等
- **广电/教育**: 教育网、科技网、歌华有线等

### 港澳台处理

港澳台地区自动规范化为：
- 香港 → 中国香港
- 澳门 → 中国澳门
- 台湾 → 中国台湾

## 📋 后续步骤

生成的源文件可用于 [ip2region](https://github.com/lionsoul2014/ip2region) 的 `xdb_maker` 工具生成 xdb 二进制文件：

```bash
# 使用 ip2region 官方 Docker 镜像生成 xdb
docker run --rm -v $(pwd)/data:/app/data lionsoul2014/ip2region-maker:latest \
  gen --src=/app/data/ipv4_source.txt \
      --dst=/app/data/ip2region_v4.xdb \
      --version=ipv4
```

## 🤖 自动化 (GitHub Actions)

本项目配置了 GitHub Actions 自动化工作流：

### 自动更新流程

1. **监听上游 Release** ([trigger-on-upstream.yml](.github/workflows/trigger-on-upstream.yml))
   - 每小时检查 [P3TERX/GeoLite.mmdb](https://github.com/P3TERX/GeoLite.mmdb) 是否有新 release
   - 检测到更新后延迟 10 分钟触发构建（等待上游同步完成）

2. **更新 XDB** ([update-xdb.yml](.github/workflows/update-xdb.yml))
   - 下载最新 mmdb 数据库
   - 转换为 ip2region 源文件格式
   - 使用官方 Docker 镜像生成 xdb 文件
   - 自动创建 Release 并上传文件

### 触发方式

| 触发方式 | 说明 |
|---------|------|
| 上游更新 | 检测到 GeoLite.mmdb 新 release 时自动触发 |

### Release 产物

每次成功构建后会自动发布以下文件：
- `ip2region_v4.xdb` - IPv4 数据库（可直接用于 ip2region）
- `ip2region_v6.xdb` - IPv6 数据库
- `ipv4_source.txt` - IPv4 源数据（可自行定制后重新生成）
- `ipv6_source.txt` - IPv6 源数据

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📜 许可证

本项目采用 MIT 许可证。

## 🙏 致谢

- [lionsoul2014/ip2region](https://github.com/lionsoul2014/ip2region) - IP 地址查询库
- [P3TERX/GeoLite.mmdb](https://github.com/P3TERX/GeoLite.mmdb) - GeoLite2 数据库镜像
- [ljxi/GeoCN](https://github.com/ljxi/GeoCN) - 中国 IP 地理数据库
- [MaxMind](https://www.maxmind.com/) - GeoLite2 数据提供商
