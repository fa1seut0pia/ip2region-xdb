package main

import (
	"bufio"
	"fmt"
	"log"
	"net"
	"os"
	"path/filepath"
	"strings"

	"github.com/sftfjugg/mmdbwriter"
	"github.com/sftfjugg/mmdbwriter/mmdbtype"
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

func toMMDBRecord(r Record) mmdbtype.DataType {
	return mmdbtype.Map{
		"country": mmdbtype.String(r.Country),
		"region":  mmdbtype.String(r.Region),
		"city":    mmdbtype.String(r.City),
		"isp":     mmdbtype.String(r.ISP),
		"asn":     mmdbtype.String(r.ASN),
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

	writer := mmdbwriter.New(
		"GeoCN",
		[]string{"zh-CN"},
		map[string]string{"zh-CN": "GeoCN mmdb"},
	)

	processFile(writer, filepath.Join(dataDir, ipv4Src))
	processFile(writer, filepath.Join(dataDir, ipv6Src))

	f, err := os.Create(outputPath)
	if err != nil {
		log.Fatalf("file create error: %v", err)
	}
	defer f.Close()

	err = writer.WriteTo(f)
	if err != nil {
		log.Fatalf("write mmdb error: %v", err)
	}

	fmt.Println("MMDB build completed:", outputPath)
}
