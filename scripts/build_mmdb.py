#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import maxminddb.writer
import ipaddress

DATA_DIR = "data"
OUTPUT_FILE = os.path.join(DATA_DIR, "GeoCN.mmdb")

# 输入文件
IPV4_SRC = os.path.join(DATA_DIR, "ipv4_source.txt")
IPV6_SRC = os.path.join(DATA_DIR, "ipv6_source.txt")


def parse_line(line):
    """
    解析一行：
    1.0.1.0|1.0.3.255|中国|福建省|福州市|电信|AS4134
    """
    parts = line.strip().split("|")
    if len(parts) < 7:
        return None

    start_ip = parts[0]
    end_ip = parts[1]

    record = {
        "country": parts[2],
        "region": parts[3],
        "city": parts[4],
        "isp": parts[5],
        "asn": parts[6],
    }

    return start_ip, end_ip, record


def cidr_merge(start_ip, end_ip):
    """
    将起止 IP 转成 CIDR 列表
    """
    start = int(ipaddress.ip_address(start_ip))
    end = int(ipaddress.ip_address(end_ip))

    cidrs = []
    while start <= end:
        max_size = start & -start
        max_len = (end - start) + 1
        size = max_size if max_size <= max_len else max_len
        cidrs.append(ipaddress.ip_network((start, size), strict=False))
        start += size

    return cidrs


def build_mmdb():
    print("Building mmdb:", OUTPUT_FILE)

    writer = maxminddb.writer.Writer(
        OUTPUT_FILE,
        ip_version=6,
        record_size=32,
        database_type="ip2region",
        languages=["zh-CN"],
        description={"zh-CN": "ip2region mmdb"},
    )

    # 处理 IPv4
    if os.path.exists(IPV4_SRC):
        with open(IPV4_SRC, "r", encoding="utf-8") as f:
            for line in f:
                parsed = parse_line(line)
                if not parsed:
                    continue
                start_ip, end_ip, record = parsed
                for cidr in cidr_merge(start_ip, end_ip):
                    writer.insert_network(cidr, record)

    # 处理 IPv6
    if os.path.exists(IPV6_SRC):
        with open(IPV6_SRC, "r", encoding="utf-8") as f:
            for line in f:
                parsed = parse_line(line)
                if not parsed:
                    continue
                start_ip, end_ip, record = parsed
                for cidr in cidr_merge(start_ip, end_ip):
                    writer.insert_network(cidr, record)

    writer.close()
    print("MMDB build completed:", OUTPUT_FILE)


if __name__ == "__main__":
    build_mmdb()
