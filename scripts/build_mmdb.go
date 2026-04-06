package main

import (
    "bufio"
    "fmt"
    "log"
    "net"
    "os"
    "path/filepath"
    "strings"

    "github.com/maxmind/mmdbwriter"
    "github.com/maxmind/mmdbwriter/mmdbtype"
)

const (
    dataDir    = "data"
    outputMMDB = "GeoCN.mmdb"

    ipv4Src = "ipv4_source.txt"
    ipv6Src = "ipv6_source.txt"
)

type Record struct {
    Country string
    Region  string
    City    string
    ISP     string
    ASN     string
}

func parseLine(line string) (string, string, Record, bool) {
    parts := strings.Split(strings.TrimSpace(line), "|")
    if len(parts) < 7 {
        return "", "", Record{}, false
    }

    return parts[0], parts[1], Record{
        Country: parts[2],
        Region:  parts[3],
        City:    parts[4],
        ISP:     parts[5],
        ASN:     parts[6],
    }, true
}

func trimSuffix(s string) string {
    s = strings.TrimSuffix(s, "省")
    s = strings.TrimSuffix(s, "市")
    return s
}

func detectType(isp string) string {
    if strings.Contains(isp, "移动") {
        return "移动"
    }
    if strings.Contains(isp, "联通") {
        return "联通"
    }
    if strings.Contains(isp, "电信") {
        return "电信"
    }
    return "宽带"
}

func toMMDBRecord(r Record) mmdbtype.DataType {
    // 构造 regions 数组（省、市、区）
    regions := mmdbtype.Slice{}
    regionsShort := mmdbtype.Slice{}

    // 省
    if r.Region != "" {
        regions = append(regions, mmdbtype.String(r.Region))
        regionsShort = append(regionsShort, mmdbtype.String(trimSuffix(r.Region)))
    }

    // 市
    if r.City != "" {
        regions = append(regions, mmdbtype.String(r.City))
        regionsShort = append(regionsShort, mmdbtype.String(trimSuffix(r.City)))
    }

    // 区（从 ISP 字段中提取不到，保持空或未来扩展）
    // 如果你未来加入 district 字段，这里可以 append

    // type 字段（宽带/移动/联通）
    netType := detectType(r.ISP)

    return mmdbtype.Map{
        "regions":       regions,
        "regions_short": regionsShort,
        "type":          mmdbtype.String(netType),
        "asn":           mmdbtype.String(r.ASN),
        "isp":           mmdbtype.String(r.ISP),
    }
}

func processFile(writer *mmdbwriter.Tree, filePath string) {
    f, err := os.Open(filePath)
    if err != nil {
        log.Printf("skip missing file: %s", filePath)
        return
    }
    defer f.Close()

    scanner := bufio.NewScanner(f)
    for scanner.Scan() {
        start, end, record, ok := parseLine(scanner.Text())
        if !ok {
            continue
        }

        startIP := net.ParseIP(start)
        endIP := net.ParseIP(end)
        if startIP == nil || endIP == nil {
            continue
        }

        writer.InsertRange(startIP, endIP, toMMDBRecord(record))
    }
}

func main() {
    outputPath := filepath.Join(dataDir, outputMMDB)
    fmt.Println("Building MMDB:", outputPath)

    writer, err := mmdbwriter.New(mmdbwriter.Options{
        DatabaseType: "GeoCN",
        Languages:    []string{"zh-CN"},
        Description:  map[string]string{"zh-CN": "GeoCN mmdb"},
    })
    if err != nil {
        log.Fatalf("writer init error: %v", err)
    }

    processFile(writer, filepath.Join(dataDir, ipv4Src))
    processFile(writer, filepath.Join(dataDir, ipv6Src))

    f, err := os.Create(outputPath)
    if err != nil {
        log.Fatalf("file create error: %v", err)
    }
    defer f.Close()

    _, err = writer.WriteTo(f)
    if err != nil {
        log.Fatalf("write mmdb error: %v", err)
    }

    fmt.Println("MMDB build completed:", outputPath)
}
