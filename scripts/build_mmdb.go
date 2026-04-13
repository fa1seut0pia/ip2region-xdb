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

// -------------------- 行政区划结构 --------------------
type County struct {
    Label string `json:"label"`
    Name  string `json:"name"`
    Code  string `json:"code"`
}

type City struct {
    Label    string   `json:"label"`
    Name     string   `json:"name"`
    Code     string   `json:"code"`
    Counties []County `json:"counties"`
}

type Province struct {
    Label  string `json:"label"`
    Name   string `json:"name"`
    Code   string `json:"code"`
    Cities []City `json:"cities"`
}

var provinces []Province

func trimZero(s string) string {
    for len(s) > 0 && s[len(s)-1] == '0' {
        s = s[:len(s)-1]
    }
    return s
}

// -------------------- 三级行政区划查询 --------------------
func findCodes(province, city, district string) (int, int, int) {
    pCode, cCode, dCode := 0, 0, 0

    for _, p := range provinces {
        if p.Name == province {
            pCode = atoi(trimZero(p.Code))

            for _, c := range p.Cities {
                if c.Name == city {
                    cCode = atoi(trimZero(c.Code))

                    for _, d := range c.Counties {
                        if d.Name == district {
                            dCode = atoi(trimZero(d.Code))
                            return pCode, cCode, dCode
                        }
                    }
                }
            }
        }
    }
    return pCode, cCode, dCode
}

func atoi(s string) int {
    n := 0
    for _, c := range s {
        n = n*10 + int(c-'0')
    }
    return n
}

// -------------------- 新增：坐标表 --------------------
var coords []map[string][2]float64

// -------------------- 原有结构体（保持不变） --------------------
type Record struct {
    ISP           string
    Net           string
    Province      string
    City          string
    Districts     string
    ProvinceCode  int
    CityCode      int
    DistrictsCode int

    // 新增字段
    Lat float64
    Lng float64
}

// 按样本字段顺序解析：
// startIP|endIP|...|province|city|districts|isp|net|provinceCode|cityCode|districtsCode
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

// 输出字段严格等于样板
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

        // 新增
        "lat": mmdbtype.Float64(r.Lat),
        "lng": mmdbtype.Float64(r.Lng),
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

        //
        // ----------- 根据省/市/区县查询行政代码 -----------
        //
        p, c, d := findCodes(record.Province, record.City, record.Districts)
        record.ProvinceCode = p
        record.CityCode = c
        record.DistrictsCode = d

        // ----------- 新增：坐标匹配 -----------
        key := record.Province + record.City + record.Districts
        if v, ok := coords[key]; ok {
            record.Lng = v[0]
            record.Lat = v[1]
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
    //
    // ----------- 加载行政区划 JSON -----------
    //
    b, err := os.ReadFile("location.json")
    if err != nil {
        log.Fatalf("load location.json error: %v", err)
    }
    if err := json.Unmarshal(b, &provinces); err != nil {
        log.Fatalf("parse location.json error: %v", err)
    }

    // ----------- 加载 coords.json -----------
    cb, err := os.ReadFile("coords.json")
    if err != nil {
        log.Fatalf("load coords.json error: %v", err)
    }
    if err := json.Unmarshal(cb, &coords); err != nil {
        log.Fatalf("parse coords.json error: %v", err)
    }

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
