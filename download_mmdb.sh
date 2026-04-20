#!/usr/bin/env bash
# 下载 GeoLite2 和 GeoCN mmdb 文件

set -e

DATA_DIR="${1:-data}"
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

# 数据库 URL
URLS=(
    # GeoLite2 数据库（非中国 IP）
    "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-ASN.mmdb"
    "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb"
    "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-Country.mmdb"
    # GeoCN 数据库（中国 IP）
    "https://github.com/ljxi/GeoCN/releases/latest/download/GeoCN.mmdb"
)

echo "=============================================="
echo "MMDB 数据库下载器"
echo "=============================================="
echo "数据目录: $(pwd)"
echo ""

for URL in "${URLS[@]}"; do
    FILE_NAME="$(basename "$URL")"
    TEMP_FILE="${FILE_NAME}.download"
    echo "[信息] 下载: $URL"
    rm -f "$TEMP_FILE"
    curl -# -fL --retry 3 --remote-time --output "$TEMP_FILE" "$URL"
    mv -f "$TEMP_FILE" "$FILE_NAME"
done

echo ""
echo "[信息] 下载完成！"
ls -lh *.mmdb 2>/dev/null || echo "[警告] 未找到 mmdb 文件"
