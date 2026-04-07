package main

import (
    "bufio"
    "encoding/json"
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

// 样板字段结构：严格对齐 raw
type Record struct {
    ISP            string
    Net            string
    Province       string
    City           string
    Districts      string
    ProvinceCode   int
    CityCode       int
    DistrictsCode  int
}

// 行政区划 map
var (
    provinceMap  = map[string]int{}
    cityMap      = map[string]int{}
    districtMap  = map[string]int{}
)

// 读取根目录 location.json
func loadLocationJSON() {
    f, err := os.ReadFile("location.json")
    if err != nil {
        log.Printf("location.json not found")
        return
    }

    var raw struct {
        Province map[string]int `json:"province"`
        City     map[string]int `json:"city"`
        District map[string]int `json:"district"`
    }

    if err := json.Unmarshal(f, &raw); err != nil {
        log.Printf("location.json parse error: %v", err)
        return
    }

    provinceMap = raw.Province
    cityMap = raw.City
    districtMap = raw.District
}

// 按样本字段顺序解析：
// startIP|endIP|...|province|city|districts|isp|net
func parseLine(line string) (string, string, Record, bool) {
    parts := strings.Split(strings.TrimSpace(line), "|")
    if len(parts) < 9 {
        return "", "", Record{}, false
    }

    return parts[0], parts[1], Record{
        Province:      parts[4],
        City:          parts[5],
        Districts:     parts[6],
        ISP:           parts[7],
        Net:           parts[8],
        ProvinceCode:  0,
        CityCode:      0,
        DistrictsCode: 0,
    }, true
}

// 输出字段严格等于样板 raw
func toMMDBRecord(r Record) mmdbtype.DataType {
    return mmdbtype.Map{
        "isp":           mmdbtype.String(r.ISP),
        "net":           mmdbtype.String(r.Net),
        "province":      mmdbtype.String(r.Province),
        "city":          mmdbtype.String(r.City),
        "districts":     mmdbtype.String(r.Districts),
        "provinceCode":  mmdbtype.Int32(r.ProvinceCode),
        "cityCode":      mmdbtype.Int32(r.CityCode),
        "districtsCode": mmdbtype.Int32(r.DistrictsCode),
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

        // ---- 最小修改：从 location.json 填 code ----
        if v, ok := provinceMap[record.Province]; ok {
            record.ProvinceCode = v
        }
        if v, ok := cityMap[record.City]; ok {
            record.CityCode = v
        }
        if v, ok := districtMap[record.Districts]; ok {
            record.DistrictsCode = v
        }
        // ----------------------------------------

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

    // 加载行政区划 JSON
    loadLocationJSON()

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
