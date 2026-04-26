#!/usr/bin/env python3
"""
GeoLite2 mmdb 转 ip2region xdb 源文件转换器

数据源优先级：
1. 内网IP.txt - 内网/保留地址（最高优先级）
2. GeoCN.mmdb - 中国 IP 数据
3. GeoLite2-City/Country/ASN.mmdb - 非中国 IP 数据
"""

import ipaddress
import os
import sys
import json
import bisect
from datetime import datetime
from functools import lru_cache
from typing import Iterator

import maxminddb


class Log:
    """简单的日志封装，支持时间打印。"""

    @staticmethod
    def _now() -> str:
        """获取当前时间字符串。"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def info(msg: str) -> None:
        """输出信息日志。"""
        print(f"[{Log._now()}] [信息] {msg}", flush=True)

    @staticmethod
    def warn(msg: str) -> None:
        """输出警告日志。"""
        print(f"[{Log._now()}] [警告] {msg}", flush=True)

    @staticmethod
    def error(msg: str) -> None:
        """输出错误日志。"""
        print(f"[{Log._now()}] [错误] {msg}", flush=True)


class IPRecord:
    """
    表示一个 IP 范围记录，包含地理和网络信息。
    使用 __slots__ 减少内存占用，提高访问速度。
    """
    __slots__ = ('start_ip', 'end_ip', 'continent', 'country', 'province',
                 'city', 'districts', 'isp', 'net', 'priority')

    def __init__(self, start_ip: int, end_ip: int, continent: str = "",
                 country: str = "", province: str = "", city: str = "",
                 districts: str = "", isp: str = "", net: str = "",
                 priority: int = 0):
        self.start_ip = start_ip
        self.end_ip = end_ip
        self.continent = continent
        self.country = country
        self.province = province
        self.city = city
        self.districts = districts
        self.isp = isp
        self.net = net
        self.priority = priority

    @staticmethod
    def _int_to_ipv4_str(ip_int: int) -> str:
        """快速将整数转换为 IPv4 字符串（比 ipaddress 模块更快）。"""
        return f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"

    def to_line(self, is_ipv6: bool = False) -> str:
        """将记录转换为 ip2region 源文件格式的一行。"""
        if is_ipv6:
            start = str(ipaddress.IPv6Address(self.start_ip))
            end = str(ipaddress.IPv6Address(self.end_ip))
        else:
            # 使用快速转换方法
            start = self._int_to_ipv4_str(self.start_ip)
            end = self._int_to_ipv4_str(self.end_ip)

        return f"{start}|{end}|{self.continent}|{self.country}|{self.province}|{self.city}|{self.districts}|{self.isp}|{self.net}"

    def same_data(self, other: 'IPRecord') -> bool:
        """检查两条记录的数据是否相同（不含 IP 范围）。"""
        return (
            self.continent == other.continent and
            self.country == other.country and
            self.province == other.province and
            self.city == other.city and
            self.districts == other.districts and
            self.isp == other.isp and
            self.net == other.net
        )

    def merge_with(self, other: 'IPRecord') -> bool:
        """
        尝试与另一条记录合并（如果它们相邻且数据相同）。
        合并成功返回 True。
        """
        if self.end_ip + 1 == other.start_ip and self.same_data(other):
            self.end_ip = other.end_ip
            return True
        return False


class MMDBConverter:
    """GeoLite2/GeoCN mmdb 文件转 ip2region 源文件格式的转换器。"""

    # 优先级常量
    PRIORITY_GEOLITE = 1      # GeoLite2 数据（非中国）
    PRIORITY_GEOCN = 2        # GeoCN 数据（中国）
    PRIORITY_INTERNAL = 10    # 内网 IP（最高优先级）

    # ASN 映射表 - 将常见 ASN 编号转为中文名称
    ASN_MAP = {
        # 有线电视/广电
        9812: "东方有线",
        9389: "中国长城",
        17962: "天威视讯",
        17429: "歌华有线",
        24139: "华数",
        58461: "鹏博士",
        # 科研/教育
        7497: "科技网",
        4538: "教育网",
        9801: "中关村",
        24151: "CNNIC",
        # 中国移动
        38019: "中国移动", 139080: "中国移动", 9808: "中国移动", 24400: "中国移动",
        134810: "中国移动", 24547: "中国移动", 56040: "中国移动", 56041: "中国移动",
        56042: "中国移动", 56044: "中国移动", 132525: "中国移动", 56046: "中国移动",
        56047: "中国移动", 56048: "中国移动", 59257: "中国移动", 24444: "中国移动",
        24445: "中国移动", 137872: "中国移动", 9231: "中国移动", 58453: "中国移动",
        # 中国电信
        4134: "中国电信", 4812: "中国电信", 23724: "中国电信", 136188: "中国电信",
        137693: "中国电信", 17638: "中国电信", 140553: "中国电信", 4847: "中国电信",
        140061: "中国电信", 136195: "中国电信", 17799: "中国电信", 139018: "中国电信",
        134764: "中国电信", 4809: "中国电信CN2",
        # 中国联通
        4837: "中国联通", 4808: "中国联通", 134542: "中国联通", 134543: "中国联通",
        17621: "中国联通", 17623: "中国联通", 9929: "中国联通精品网",
        # 国内云服务商
        59019: "金山云",
        135377: "优刻云",
        45062: "网易云",
        37963: "阿里云", 45102: "阿里云国际",
        45090: "腾讯云", 132203: "腾讯云国际",
        55967: "百度云", 38365: "百度云",
        58519: "华为云", 55990: "华为云", 136907: "华为云",
        131072: "京东云",
        138950: "火山引擎",
        63646: "七牛云",
        141679: "天翼云",
        # 港澳台
        4609: "澳門電訊",
        9269: "香港宽频",
        4515: "香港电讯",
        9304: "香港有线宽频",
        3462: "中华电信",
        17709: "亚太电信",
        # 国际云服务商
        13335: "Cloudflare",
        55960: "亚马逊云", 14618: "亚马逊云", 16509: "亚马逊云",
        15169: "谷歌云", 396982: "谷歌云", 36492: "谷歌云",
        8075: "微软云",
        14061: "DigitalOcean",
        63949: "Linode",
        20940: "Akamai",
    }

    # 港澳台地区名称映射
    HMT_REGIONS = {"香港", "澳门", "台湾"}

    # IPv4-mapped IPv6 地址范围 (::ffff:0.0.0.0/96)
    # Go 的 net.ParseIP().To4() 会把这些地址转回 4 字节 IPv4，
    # 导致 ip2region maker 在构建 IPv6 xdb 时报 "invalid ip segment(IPv6 expected)"
    _IPV4_MAPPED_V6_START = 0xFFFF00000000          # ::ffff:0.0.0.0
    _IPV4_MAPPED_V6_END = 0xFFFFFFFFFFFF            # ::ffff:255.255.255.255

    def __init__(self, city_path: str, country_path: str, asn_path: str,
                 geocn_path: str = None, internal_ip_path: str = None,
                 data_dir: str = "data", division_data_dir: str | None = None):
        self.city_path = city_path
        self.country_path = country_path
        self.asn_path = asn_path
        self.geocn_path = geocn_path
        self.internal_ip_path = internal_ip_path
        self.data_dir = data_dir
        self.division_data_dir = division_data_dir or os.path.dirname(geocn_path or "") or "data"

        # 确保数据目录存在
        os.makedirs(data_dir, exist_ok=True)

    @lru_cache(maxsize=1024)
    def _normalize_country_name(self, country: str) -> str:
        """
        规范化国家/地区名称。
        将港澳台地区转换为"中国香港"、"中国澳门"、"中国台湾"格式。
        使用 lru_cache 缓存结果。
        """
        if country in self.HMT_REGIONS:
            return sys.intern(f"中国{country}")
        return country

    def _parse_city_record(self, data: dict) -> dict:
        """解析城市数据库记录。内联字典访问，避免 _get_safe_value 开销。"""
        if not data:
            return {"continent": "", "country": "", "province": "", "city": "", "districts": ""}

        # 洲 - 优先使用中文名（内联访问嵌套字典）
        continent_d = data.get("continent")
        continent = ""
        if continent_d:
            names = continent_d.get("names")
            if names:
                continent = names.get("zh-CN") or names.get("en") or ""

        # 国家 - 优先使用中文名，并处理港澳台
        country_d = data.get("country")
        country = ""
        if country_d:
            names = country_d.get("names")
            if names:
                country = names.get("zh-CN") or names.get("en") or ""
        if country:
            country = self._normalize_country_name(country)

        # 省份/州 - 来自 subdivisions[0]
        province = ""
        districts = ""
        subdivisions = data.get("subdivisions")
        if subdivisions:
            sub0 = subdivisions[0]
            names = sub0.get("names") if isinstance(sub0, dict) else None
            if names:
                province = names.get("zh-CN") or names.get("en") or ""
            # 区县 - 来自 subdivisions[1]（如果存在）
            if len(subdivisions) > 1:
                sub1 = subdivisions[1]
                names = sub1.get("names") if isinstance(sub1, dict) else None
                if names:
                    districts = names.get("zh-CN") or names.get("en") or ""

        # 城市 - 优先使用中文名
        city_d = data.get("city")
        city = ""
        if city_d:
            names = city_d.get("names")
            if names:
                city = names.get("zh-CN") or names.get("en") or ""

        return {
            "continent": sys.intern(continent) if continent else "",
            "country": country,
            "province": sys.intern(province) if province else "",
            "city": sys.intern(city) if city else "",
            "districts": sys.intern(districts) if districts else ""
        }

    def _parse_country_record(self, data: dict) -> tuple[str, str]:
        """解析国家数据库记录。返回 (continent, country) 元组。"""
        if not data:
            return ("", "")

        # 洲 - 优先使用中文名
        continent_d = data.get("continent")
        continent = ""
        if continent_d:
            names = continent_d.get("names")
            if names:
                continent = names.get("zh-CN") or names.get("en") or ""

        # 国家 - 优先使用中文名，并处理港澳台
        country_d = data.get("country")
        country = ""
        if country_d:
            names = country_d.get("names")
            if names:
                country = names.get("zh-CN") or names.get("en") or ""
        if country:
            country = self._normalize_country_name(country)

        return (
            sys.intern(continent) if continent else "",
            country
        )

    # ASN 字符串缓存，避免重复创建 "AS{number}" 字符串
    _asn_str_cache: dict = {}

    def _get_asn_str(self, asn: int) -> str:
        """获取 ASN 字符串，使用缓存避免重复创建。"""
        if asn not in self._asn_str_cache:
            self._asn_str_cache[asn] = sys.intern(f"AS{asn}")
        return self._asn_str_cache[asn]

    def _parse_asn_record(self, data: dict) -> tuple[str, str]:
        """解析 ASN 数据库记录。返回 (isp, net) 元组。"""
        if not data:
            return ("", "")

        # 获取 ASN 编号
        asn = data.get("autonomous_system_number")
        if not asn:
            return ("", "")

        # ISP - 优先使用 ASN 映射表中的中文名称
        isp = self.ASN_MAP.get(asn)
        if not isp:
            # 回退到原始组织名称
            org = data.get("autonomous_system_organization")
            isp = str(org) if org is not None else ""

        return (isp, self._get_asn_str(asn))

    # GeoCN 固定值缓存
    _GEOCN_CONTINENT = sys.intern("亚洲")
    _GEOCN_COUNTRY = sys.intern("中国")
    _SPECIAL_CITY_NAMES = frozenset({"市辖区", "县", "自治区直辖县级行政区划"})
    _division_name_cache: dict[str, tuple[dict[str, str], dict[str, str], dict[str, str]]] = {}
    _missing_division_data_dirs: set[str] = set()
    _division_alias_cache: dict[str, tuple[dict[str, str], dict[str, str]]] = {}

    @classmethod
    def _load_division_file(cls, path: str) -> dict[str, str]:
        with open(path, "r", encoding="utf-8") as f:
            return {
                item["code"]: sys.intern(item["name"])
                for item in json.load(f)
            }

    def _load_division_names(self) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        """懒加载中国行政区划名称映射。"""
        data_dir = os.path.abspath(self.division_data_dir)
        cached = self._division_name_cache.get(data_dir)
        if cached is not None:
            return cached

        provinces_path = os.path.join(data_dir, "provinces.json")
        cities_path = os.path.join(data_dir, "cities.json")
        areas_path = os.path.join(data_dir, "areas.json")
        required_paths = (provinces_path, cities_path, areas_path)

        if not all(os.path.exists(path) for path in required_paths):
            if data_dir not in self._missing_division_data_dirs:
                missing = ", ".join(path for path in required_paths if not os.path.exists(path))
                Log.warn(f"区域数据文件缺失，division_code 将无法展开: {missing}")
                self._missing_division_data_dirs.add(data_dir)
            empty = ({}, {}, {})
            self._division_name_cache[data_dir] = empty
            return empty

        loaded = (
            self._load_division_file(provinces_path),
            self._load_division_file(cities_path),
            self._load_division_file(areas_path),
        )
        self._division_name_cache[data_dir] = loaded
        return loaded

    def _load_division_aliases(self) -> tuple[dict[str, str], dict[str, str]]:
        """懒加载行政区划简称→全称映射（用于 GeoLite2 短名规范化）。"""
        data_dir = os.path.abspath(self.division_data_dir)
        cached = self._division_alias_cache.get(data_dir)
        if cached is not None:
            return cached

        provinces, cities, _ = self._load_division_names()

        # 去掉末尾"省/市/自治区/特别行政区/壮族/回族/维吾尔"等后缀 → 全称
        _SUFFIXES = ("省", "市", "自治区", "特别行政区")

        def _build_alias(name_map: dict[str, str]) -> dict[str, str]:
            alias = {}
            for name in name_map.values():
                short = name
                for s in _SUFFIXES:
                    if short.endswith(s):
                        short = short[:-len(s)]
                        break
                if short != name:
                    alias[short] = name
            return alias

        result = (_build_alias(provinces), _build_alias(cities))
        self._division_alias_cache[data_dir] = result
        return result

    def _normalize_to_full_name(self, province: str, city: str) -> tuple[str, str]:
        """将 GeoLite2 的短省/市名规范化为带后缀的全称。"""
        if not province and not city:
            return ("", "")
        province_alias, city_alias = self._load_division_aliases()
        province = province_alias.get(province, province)
        city = city_alias.get(city, city)
        return (province, city)

    @lru_cache(maxsize=4096)
    def _resolve_division_code(self, division_code: int | str | None) -> tuple[str, str, str]:
        """将 6 位行政区划码解析为省/市/区县名称。"""
        if division_code is None:
            return ("", "", "")

        code = f"{int(division_code):06d}" if isinstance(division_code, int) else str(division_code).strip()
        if not code.isdigit():
            return ("", "", "")
        code = code.zfill(6)

        province_names, city_names, area_names = self._load_division_names()
        province = province_names.get(code[:2], "")
        city = city_names.get(code[:4], "")
        districts = area_names.get(code, "")

        if city in self._SPECIAL_CITY_NAMES:
            city = province

        if code.endswith("0000"):
            city = ""
            districts = ""
        elif code.endswith("00"):
            districts = ""

        return (province, city, districts)

    def _parse_geocn_record(self, data: dict) -> dict:
        """
        解析 GeoCN 数据库记录。

        GeoCN 字段：
        - isp: 运营商（如：中国移动）
        - type: 网络类型（如：宽带）
        - province: 省份（如：四川省）
        - city: 城市（如：成都市）
        - districts: 区县（如：武侯区）
        """
        if not data:
            return {
                "continent": self._GEOCN_CONTINENT,
                "country": self._GEOCN_COUNTRY,
                "province": "", "city": "", "districts": "", "isp": "", "net": ""
            }

        # 直接访问字典，避免函数调用开销
        get = data.get
        province = str(get("province", "") or "")
        city = str(get("city", "") or "")
        districts = str(get("districts", "") or "")

        if not (province or city or districts):
            province, city, districts = self._resolve_division_code(get("division_code"))

        return {
            "continent": self._GEOCN_CONTINENT,
            "country": self._GEOCN_COUNTRY,
            "province": sys.intern(province) if province else "",
            "city": sys.intern(city) if city else "",
            "districts": sys.intern(districts) if districts else "",
            "isp": sys.intern(str(get("isp", "") or "")),
            "net": sys.intern(str(get("type", "") or ""))
        }

    @staticmethod
    def _is_ipv4_mapped_v6(start_ip: int, end_ip: int) -> bool:
        """
        判断 IP 范围是否落在 IPv4-mapped IPv6 地址空间 (::ffff:0.0.0.0/96)。
        只要范围与该区间有交集即视为 IPv4-mapped。
        """
        return (start_ip <= MMDBConverter._IPV4_MAPPED_V6_END and
                end_ip >= MMDBConverter._IPV4_MAPPED_V6_START)

    @staticmethod
    def _network_to_int_range(network) -> tuple[int, int]:
        """
        直接从 ipaddress network 对象提取整数范围，避免 str() → parse 的往返开销。
        """
        start = int(network.network_address)
        # broadcast_address 内部需要计算 hostmask，直接用位运算更快
        prefix = network.prefixlen
        if network.version == 4:
            mask = (1 << (32 - prefix)) - 1
        else:
            mask = (1 << (128 - prefix)) - 1
        return start, start | mask

    def _ip_to_int(self, ip_str: str, is_ipv6: bool) -> int:
        """将 IP 地址字符串转换为整数。"""
        if is_ipv6:
            return int(ipaddress.IPv6Address(ip_str))
        else:
            return int(ipaddress.IPv4Address(ip_str))

    def _is_china_ip(self, data: dict) -> bool:
        """判断是否为中国 IP（基于 GeoLite2 数据）。优化版本，减少函数调用。"""
        if not data:
            return False

        # 直接访问嵌套字典，避免 _get_safe_value 的开销
        country = data.get("country")
        if country and country.get("iso_code") == "CN":
            return True

        # 也检查 registered_country
        reg_country = data.get("registered_country")
        return bool(reg_country and reg_country.get("iso_code") == "CN")

    def _load_internal_ips(self, is_ipv6: bool) -> list[IPRecord]:
        """
        加载内网 IP 数据。

        内网IP.txt 格式：start|end|continent_code|country_code|province|city
        - continent_code/country_code 通常为 '0'
        - province 通常为 '内网IP'
        - city 可能是 '内网IP' 或特定 ISP 名称（如 '本机地址'）
        """
        records = []

        if not self.internal_ip_path or not os.path.exists(self.internal_ip_path):
            return records

        Log.info(f"读取内网 IP 文件: {self.internal_ip_path}")

        with open(self.internal_ip_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split('|')
                if len(parts) < 2:
                    continue

                start_ip_str = parts[0]
                end_ip_str = parts[1]

                # 判断是否为当前 IP 版本
                is_v6 = ':' in start_ip_str
                if is_v6 != is_ipv6:
                    continue

                try:
                    start_ip = self._ip_to_int(start_ip_str, is_ipv6)
                    end_ip = self._ip_to_int(end_ip_str, is_ipv6)
                except ValueError:
                    Log.warn(f"无效的 IP 地址: {line}")
                    continue

                # 跳过 IPv4-mapped IPv6 地址
                if is_ipv6 and self._is_ipv4_mapped_v6(start_ip, end_ip):
                    continue

                # 解析字段（格式：start|end|continent_code|country_code|province|city）
                continent_code = parts[2] if len(parts) > 2 else "0"
                country_code = parts[3] if len(parts) > 3 else "0"
                province = parts[4] if len(parts) > 4 else ""
                city = parts[5] if len(parts) > 5 else ""

                # 智能解析：
                # - 如果 continent/country 是 '0'，使用 '内网IP' 标识
                # - 如果 city 不是 '内网IP'，可能是 ISP 信息
                continent = "内网IP" if continent_code == "0" else continent_code
                country = "内网IP" if country_code == "0" else country_code

                # 如果 city 字段不是 '内网IP'，则认为它是 ISP 信息
                isp = city if city and city != "内网IP" else ""

                record = IPRecord(
                    start_ip=start_ip,
                    end_ip=end_ip,
                    continent=continent,
                    country=country,
                    province=province,
                    city=city,
                    districts="",
                    isp=isp,
                    net="",
                    priority=self.PRIORITY_INTERNAL
                )
                records.append(record)

        Log.info(f"内网 IP: {len(records)} 条记录")
        return records

    @staticmethod
    def _normalize_city_name(city: str) -> str:
        """规范化城市名称，去除后缀用于比对"""
        return city.replace('市', '').replace('省', '').strip()

    @staticmethod
    def _lookup_city_by_ip(ranges: list[tuple[int, int, dict]], starts: list[int], ip_int: int) -> dict | None:
        """按 IP 整数在有序区间中查找城市记录。"""
        idx = bisect.bisect_right(starts, ip_int) - 1
        if idx < 0:
            return None
        start_ip, end_ip, parsed = ranges[idx]
        if start_ip <= ip_int <= end_ip:
            return parsed
        return None

    def _load_all_mmdb_records(self) -> tuple[dict, dict]:
        """
        一次性加载所有 MMDB 数据库，同时分离 IPv4 和 IPv6 记录。
        返回 (ipv4_records, ipv6_records) 两个字典。

        这样每个数据库只读取一次，而不是 IPv4/IPv6 各读一次。
        """
        # 分别存储 IPv4 和 IPv6 的记录
        # key: (start_ip, end_ip), value: IPRecord
        ipv4_geocn = []
        ipv6_geocn = []
        ipv4_geolite: dict[tuple[int, int], IPRecord] = {}
        ipv6_geolite: dict[tuple[int, int], IPRecord] = {}

        # 预取常量到局部变量
        _net_range = self._network_to_int_range
        _V4MAPPED_START = self._IPV4_MAPPED_V6_START
        _V4MAPPED_END = self._IPV4_MAPPED_V6_END
        _PRIO_GEOCN = self.PRIORITY_GEOCN
        _PRIO_GEOLITE = self.PRIORITY_GEOLITE

        # 2. 加载城市数据库（一次读取，分离 IPv4/IPv6，同时建立中国城市索引用于冲突检测）
        Log.info(f"读取城市数据库: {self.city_path}")
        v4_count, v6_count, china_skipped, v4_mapped_skipped = 0, 0, 0, 0
        _is_china = self._is_china_ip

        # 中国城市段索引：(start_ip, end_ip, parsed_city)
        china_city_ranges_v4: list[tuple[int, int, dict]] = []
        china_city_ranges_v6: list[tuple[int, int, dict]] = []

        with maxminddb.open_database(self.city_path) as reader:
            for network, data in reader:
                is_v6 = network.version == 6
                start_ip, end_ip = _net_range(network)

                # 跳过 IPv4-mapped IPv6 地址
                if is_v6 and start_ip <= _V4MAPPED_END and end_ip >= _V4MAPPED_START:
                    v4_mapped_skipped += 1
                    continue

                parsed = self._parse_city_record(data)

                if _is_china(data):
                    # 中国 IP 只用于和 GeoCN 做冲突检测索引，不进入 GeoLite 输出
                    if is_v6:
                        china_city_ranges_v6.append((start_ip, end_ip, parsed))
                    else:
                        china_city_ranges_v4.append((start_ip, end_ip, parsed))
                    china_skipped += 1
                    continue

                key = (start_ip, end_ip)
                target_dict = ipv6_geolite if is_v6 else ipv4_geolite

                if key not in target_dict:
                    target_dict[key] = IPRecord(
                        start_ip=start_ip,
                        end_ip=end_ip,
                        **parsed,
                        priority=_PRIO_GEOLITE
                    )
                else:
                    record = target_dict[key]
                    if parsed["continent"] and not record.continent:
                        record.continent = parsed["continent"]
                    if parsed["country"] and not record.country:
                        record.country = parsed["country"]
                    if parsed["province"] and not record.province:
                        record.province = parsed["province"]
                    if parsed["city"] and not record.city:
                        record.city = parsed["city"]
                    if parsed["districts"] and not record.districts:
                        record.districts = parsed["districts"]

                if is_v6:
                    v6_count += 1
                else:
                    v4_count += 1

        china_city_ranges_v4.sort(key=lambda x: x[0])
        china_city_ranges_v6.sort(key=lambda x: x[0])
        china_city_starts_v4 = [item[0] for item in china_city_ranges_v4]
        china_city_starts_v6 = [item[0] for item in china_city_ranges_v6]

        Log.info(f"城市数据库: IPv4 {v4_count} 条, IPv6 {v6_count} 条（跳过中国 IP: {china_skipped}, IPv4-mapped: {v4_mapped_skipped}）")

        # 1. 加载 GeoCN 数据库（一次读取，分离 IPv4/IPv6，并做冲突检测）
        if self.geocn_path and os.path.exists(self.geocn_path):
            Log.info(f"读取 GeoCN 数据库: {self.geocn_path}")
            v4_count, v6_count, v4_mapped_skipped, conflicts = 0, 0, 0, 0

            with maxminddb.open_database(self.geocn_path) as reader:
                for network, data in reader:
                    is_v6 = network.version == 6
                    start_ip, end_ip = _net_range(network)

                    # 跳过 IPv4-mapped IPv6 地址
                    if is_v6 and start_ip <= _V4MAPPED_END and end_ip >= _V4MAPPED_START:
                        v4_mapped_skipped += 1
                        continue

                    parsed = self._parse_geocn_record(data)

                    # 冲突检测：按 GeoCN 网段首地址在中国城市索引中查找 GeoLite2 城市
                    if is_v6:
                        geolite_data = self._lookup_city_by_ip(china_city_ranges_v6, china_city_starts_v6, start_ip)
                    else:
                        geolite_data = self._lookup_city_by_ip(china_city_ranges_v4, china_city_starts_v4, start_ip)

                    if geolite_data:
                        geocn_city = self._normalize_city_name(parsed['city'])
                        geolite_city = self._normalize_city_name(geolite_data['city'])

                        # 城市冲突：以 GeoLite2 为准，丢弃 GeoCN 的区县，但保留 ISP/类型
                        if geocn_city and geolite_city and geocn_city != geolite_city:
                            conflicts += 1
                            full_province, full_city = self._normalize_to_full_name(
                                geolite_data['province'], geolite_data['city'])
                            parsed['province'] = full_province
                            parsed['city'] = full_city
                            parsed['districts'] = ''

                    record = IPRecord(
                        start_ip=start_ip,
                        end_ip=end_ip,
                        **parsed,
                        priority=_PRIO_GEOCN
                    )

                    if is_v6:
                        ipv6_geocn.append(record)
                        v6_count += 1
                    else:
                        ipv4_geocn.append(record)
                        v4_count += 1

            Log.info(f"GeoCN 数据库: IPv4 {v4_count} 条, IPv6 {v6_count} 条（跳过 IPv4-mapped: {v4_mapped_skipped}，城市冲突: {conflicts}）")

        # 3. 加载国家数据库（一次读取，分离 IPv4/IPv6）
        Log.info(f"读取国家数据库: {self.country_path}")
        v4_count, v6_count, china_skipped, v4_mapped_skipped = 0, 0, 0, 0

        with maxminddb.open_database(self.country_path) as reader:
            for network, data in reader:
                if _is_china(data):
                    china_skipped += 1
                    continue

                is_v6 = network.version == 6
                start_ip, end_ip = _net_range(network)

                # 跳过 IPv4-mapped IPv6 地址
                if is_v6 and start_ip <= _V4MAPPED_END and end_ip >= _V4MAPPED_START:
                    v4_mapped_skipped += 1
                    continue

                continent, country = self._parse_country_record(data)

                key = (start_ip, end_ip)
                target_dict = ipv6_geolite if is_v6 else ipv4_geolite

                if key not in target_dict:
                    target_dict[key] = IPRecord(
                        start_ip=start_ip,
                        end_ip=end_ip,
                        continent=continent,
                        country=country,
                        priority=_PRIO_GEOLITE
                    )
                else:
                    record = target_dict[key]
                    if continent and not record.continent:
                        record.continent = continent
                    if country and not record.country:
                        record.country = country

                if is_v6:
                    v6_count += 1
                else:
                    v4_count += 1

        Log.info(f"国家数据库: IPv4 {v4_count} 条, IPv6 {v6_count} 条（跳过中国 IP: {china_skipped}, IPv4-mapped: {v4_mapped_skipped}）")

        # 4. 加载 ASN 数据库（一次读取，分离 IPv4/IPv6）
        Log.info(f"读取 ASN 数据库: {self.asn_path}")
        v4_count, v6_count, v4_mapped_skipped = 0, 0, 0

        with maxminddb.open_database(self.asn_path) as reader:
            for network, data in reader:
                is_v6 = network.version == 6
                start_ip, end_ip = _net_range(network)

                # 跳过 IPv4-mapped IPv6 地址
                if is_v6 and start_ip <= _V4MAPPED_END and end_ip >= _V4MAPPED_START:
                    v4_mapped_skipped += 1
                    continue

                isp, net = self._parse_asn_record(data)

                key = (start_ip, end_ip)
                target_dict = ipv6_geolite if is_v6 else ipv4_geolite

                if key not in target_dict:
                    target_dict[key] = IPRecord(
                        start_ip=start_ip,
                        end_ip=end_ip,
                        isp=isp,
                        net=net,
                        priority=_PRIO_GEOLITE
                    )
                else:
                    record = target_dict[key]
                    if isp and not record.isp:
                        record.isp = isp
                    if net and not record.net:
                        record.net = net

                if is_v6:
                    v6_count += 1
                else:
                    v4_count += 1

        Log.info(f"ASN 数据库: IPv4 {v4_count} 条, IPv6 {v6_count} 条（跳过 IPv4-mapped: {v4_mapped_skipped}）")

        # 返回结果
        return {
            "geocn": ipv4_geocn,
            "geolite": list(ipv4_geolite.values())
        }, {
            "geocn": ipv6_geocn,
            "geolite": list(ipv6_geolite.values())
        }

    def _collect_records_from_cache(self, mmdb_cache: dict, is_ipv6: bool) -> list[IPRecord]:
        """从缓存的 MMDB 数据中收集记录。"""
        all_records = []

        Log.info(f"正在处理 {'IPv6' if is_ipv6 else 'IPv4'} 记录...")

        # 1. 加载内网 IP（最高优先级）
        internal_records = self._load_internal_ips(is_ipv6)
        all_records.extend(internal_records)

        # 2. 从缓存加载 GeoCN 数据（中国 IP）
        all_records.extend(mmdb_cache["geocn"])

        # 3. 从缓存加载 GeoLite2 数据（非中国 IP）
        all_records.extend(mmdb_cache["geolite"])

        # 按起始 IP 排序
        all_records.sort(key=lambda r: (r.start_ip, r.end_ip))

        Log.info(f"总记录数: {len(all_records)}")
        return all_records

    def _normalize_ranges(self, records: list[IPRecord], is_ipv6: bool) -> list[IPRecord]:
        """
        规范化 IP 范围，确保没有重叠或间隙。
        高优先级记录会覆盖低优先级记录。

        热点优化：
        - 增量维护 top_priority，避免每次 max(active_priorities)
        - state_dirty 标志 + tuple 缓存：仅在 top 组合成变化时重新合成
        - 用 tuple 直接与 last_norm 字段比对，跳过"先造候选 IPRecord 再 same_data"
        - Gap 区段用 last_norm.end_ip 延伸覆盖，省去一次 IPRecord 构造
        """
        if not records:
            return []

        Log.info("正在规范化 IP 范围...")

        # 半开区间 [start, end+1) 的扫描线：共享端点处的优先级切换不会丢失边界 IP。
        # 事件元组 (ip, event_type, -priority, index, record)，event_type: 0=add, 1=remove。
        events = []
        events_append = events.append
        for i, record in enumerate(records):
            events_append((record.start_ip, 0, -record.priority, i, record))
            events_append((record.end_ip + 1, 1, -record.priority, i, record))

        events.sort()

        # 按优先级分组的活跃记录。只有最高优先级组参与合成，因此增量维护 top_priority。
        active_by_priority: dict[int, dict[int, IPRecord]] = {}
        top_priority: int | None = None

        # 缓存 top 组合成出的状态 tuple：(continent, country, province, city, districts, isp, net, priority)
        top_state: tuple | None = None
        state_dirty = False

        normalized: list[IPRecord] = []
        normalized_append = normalized.append
        last_ip: int | None = None

        total_events = len(events)
        progress_step = total_events // 10 or 1
        next_progress = progress_step

        idx = 0
        while idx < total_events:
            ip = events[idx][0]

            if idx >= next_progress:
                Log.info(f"规范化进度: {idx * 100 // total_events}%")
                next_progress += progress_step

            # 在处理当前事件前，输出上一个稳定区间 [last_ip, ip - 1]。
            if last_ip is not None and ip > last_ip and top_priority is not None:
                if state_dirty:
                    continent = country = province = city = districts = isp = net = ""
                    for rec in active_by_priority[top_priority].values():
                        if rec.continent and not continent:
                            continent = rec.continent
                        if rec.country and not country:
                            country = rec.country
                        if rec.province and not province:
                            province = rec.province
                        if rec.city and not city:
                            city = rec.city
                        if rec.districts and not districts:
                            districts = rec.districts
                        if rec.isp and not isp:
                            isp = rec.isp
                        if rec.net and not net:
                            net = rec.net
                    top_state = (continent, country, province, city,
                                 districts, isp, net, top_priority)
                    state_dirty = False

                interval_end = ip - 1

                if normalized:
                    last_norm = normalized[-1]
                    prev_end_next = last_norm.end_ip + 1
                    # Gap 段的数据沿用 last_norm，直接把它延伸到本段起点前，省一次构造。
                    if prev_end_next < last_ip:
                        last_norm.end_ip = last_ip - 1
                        prev_end_next = last_ip
                    if (prev_end_next == last_ip
                            and last_norm.continent == top_state[0]
                            and last_norm.country == top_state[1]
                            and last_norm.province == top_state[2]
                            and last_norm.city == top_state[3]
                            and last_norm.districts == top_state[4]
                            and last_norm.isp == top_state[5]
                            and last_norm.net == top_state[6]):
                        last_norm.end_ip = interval_end
                    else:
                        normalized_append(IPRecord(last_ip, interval_end, *top_state))
                else:
                    normalized_append(IPRecord(last_ip, interval_end, *top_state))

            while idx < total_events and events[idx][0] == ip:
                event = events[idx]
                event_type = event[1]
                priority = -event[2]
                record_idx = event[3]
                record = event[4]
                if event_type == 0:  # add
                    group = active_by_priority.get(priority)
                    if group is None:
                        active_by_priority[priority] = {record_idx: record}
                        if top_priority is None or priority > top_priority:
                            top_priority = priority
                            state_dirty = True
                    else:
                        group[record_idx] = record
                        if priority == top_priority:
                            state_dirty = True
                else:  # remove
                    group = active_by_priority.get(priority)
                    if group is not None:
                        group.pop(record_idx, None)
                        if not group:
                            del active_by_priority[priority]
                            if priority == top_priority:
                                top_priority = max(active_by_priority) if active_by_priority else None
                                state_dirty = True
                        elif priority == top_priority:
                            state_dirty = True
                idx += 1

            last_ip = ip

        Log.info(f"规范化后: {len(normalized)} 条记录")
        return normalized

    def _convert_with_cache(self, mmdb_cache: dict, is_ipv6: bool) -> str:
        """
        使用缓存的 MMDB 数据进行转换。
        返回输出文件路径。
        """
        version = "ipv6" if is_ipv6 else "ipv4"
        output_file = os.path.join(self.data_dir, f"{version}_source.txt")

        print(f"\n{'='*60}", flush=True)
        Log.info(f"开始转换 {version.upper()}")
        print(f"{'='*60}", flush=True)

        # 从缓存收集记录
        records = self._collect_records_from_cache(mmdb_cache, is_ipv6)

        if not records:
            Log.warn(f"未找到 {version} 记录！")
            return output_file

        # 规范化范围
        records = self._normalize_ranges(records, is_ipv6)

        # 写入文件 - 使用批量写入优化性能
        Log.info(f"正在写入 {output_file}...")
        total = len(records)

        # 批量生成所有行
        Log.info("生成输出内容...")
        lines = [record.to_line(is_ipv6) for record in records]

        # 一次性写入文件
        Log.info("写入文件...")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            if lines:  # 确保文件以换行符结尾
                f.write('\n')

        Log.info(f"转换完成: {total} 条记录已写入 {output_file}")
        return output_file

    def convert_all(self, ipv4: bool = True, ipv6: bool = True) -> tuple[str, str]:
        """
        一次性加载所有数据库，然后分别转换 IPv4 和 IPv6。
        每个数据库只读取一次，大幅提升性能。

        返回 (ipv4_output_file, ipv6_output_file)
        """
        Log.info("一次性加载所有 MMDB 数据库...")
        ipv4_cache, ipv6_cache = self._load_all_mmdb_records()

        ipv4_output = None
        ipv6_output = None

        if ipv4:
            ipv4_output = self._convert_with_cache(ipv4_cache, is_ipv6=False)

        if ipv6:
            ipv6_output = self._convert_with_cache(ipv6_cache, is_ipv6=True)

        return ipv4_output, ipv6_output


def main():
    """主入口函数。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="将 GeoLite2/GeoCN mmdb 文件转换为 ip2region 源文件格式"
    )
    parser.add_argument(
        "--city", "-c",
        default="data/GeoLite2-City.mmdb",
        help="GeoLite2-City.mmdb 文件路径"
    )
    parser.add_argument(
        "--country", "-C",
        default="data/GeoLite2-Country.mmdb",
        help="GeoLite2-Country.mmdb 文件路径"
    )
    parser.add_argument(

        "--asn", "-a",
        default="data/GeoLite2-ASN.mmdb",
        help="GeoLite2-ASN.mmdb 文件路径"
    )
    parser.add_argument(
        "--geocn", "-g",
        default="data/GeoCN.mmdb",
        help="GeoCN.mmdb 文件路径（中国 IP 数据）"
    )
    parser.add_argument(
        "--division-data-dir",
        default=None,
        help="区域数据目录路径，目录下需包含 provinces.json、cities.json、areas.json；默认使用 GeoCN.mmdb 所在目录"
    )
    parser.add_argument(
        "--internal", "-i",
        default="data/内网IP.txt",
        help="内网 IP 文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        default="data",
        help="源文件输出目录"
    )
    parser.add_argument(
        "--ipv4-only",
        action="store_true",
        help="仅处理 IPv4 地址"
    )
    parser.add_argument(
        "--ipv6-only",
        action="store_true",
        help="仅处理 IPv6 地址"
    )

    args = parser.parse_args()

    # 验证必需的输入文件
    for path, name in [(args.city, "城市"), (args.country, "国家"), (args.asn, "ASN")]:
        if not os.path.exists(path):
            Log.error(f"{name}数据库未找到: {path}")
            sys.exit(1)

    # 可选文件检查
    if args.geocn and not os.path.exists(args.geocn):
        Log.warn(f"GeoCN 数据库未找到: {args.geocn}，将仅使用 GeoLite2 数据")
        args.geocn = None

    if args.internal and not os.path.exists(args.internal):
        Log.warn(f"内网 IP 文件未找到: {args.internal}")
        args.internal = None

    converter = MMDBConverter(
        city_path=args.city,
        country_path=args.country,
        asn_path=args.asn,
        geocn_path=args.geocn,
        internal_ip_path=args.internal,
        data_dir=args.output,
        division_data_dir=args.division_data_dir
    )

    # 使用一次性加载方式处理（每个数据库只读取一次）
    process_ipv4 = not args.ipv6_only
    process_ipv6 = not args.ipv4_only

    converter.convert_all(ipv4=process_ipv4, ipv6=process_ipv6)

    Log.info("所有转换已完成！")


if __name__ == "__main__":
    try:
        main()
    except maxminddb.errors.InvalidDatabaseError as exc:
        Log.error(f"MMDB 数据库无效或已损坏: {exc}")
        Log.error("请删除 data/*.mmdb 后重新下载。旧的断点续传文件可能会把不同版本的数据库拼接在一起。")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n")
        Log.info("用户中断，程序退出")
        sys.exit(0)
