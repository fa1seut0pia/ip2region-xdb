package main

import (
	"bufio"
	"bytes"
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

func compareIP(a, b net.IP) int {
	return bytes.Compare(a.To16(), b.To16())
}

func lastIP(n *net.IPNet) net.IP {
	ip := n.IP.To16()
	mask := n.Mask
	broadcast := make(net.IP, len(ip))
	for i := range ip {
		broadcast[i] = ip[i] | ^mask[i]
	}
	return broadcast
}

func nextIP(n *net.IPNet) net.IP {
	ip := lastIP(n)
	for i := len(ip) - 1; i >= 0; i-- {
		ip[i]++
		if ip[i] != 0 {
			break
		}
	}
	return ip
}

func maxCIDR(startIP, endIP net.IP) int {
	ip := startIP
	maxPrefix := 32
	if ip.To4() == nil {
		maxPrefix = 128
	}

	for prefix := maxPrefix; prefix >= 0; prefix-- {
		_, network, err := net.ParseCIDR(fmt.Sprintf("%s/%d", ip.String(), prefix))
		if err != nil || network == nil {
			continue
		}
		if compareIP(lastIP(network), endIP) <= 0 {
			return prefix
		}
	}
	return maxPrefix
}

func cidrRange(startIP, endIP net.IP) []net.IPNet {
	var cidrs []net.IPNet
	for ip := startIP; compareIP(ip, endIP) <= 0; {
		maxSize := maxCIDR(ip, endIP)
		_, network, err := net.ParseCIDR(fmt.Sprintf("%s/%d", ip.String(), maxSize))
		if err != nil || network == nil {
			break
		}
		cidrs = append(cidrs, *network)
		ip = nextIP(network)
	}
	return cidrs
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

		cidrs := cidrRange(startIP, endIP)
		for _, cidr := range cidrs {
			err := writer.Insert(&cidr, toMMDBRecord(record))
			if err != nil {
				log.Printf("insert error: %v", err)
			}
		}
	}
}

func main() {
	outputPath := filepath.Join(dataDir, outputMMDB)
	fmt.Println("Building MMDB:", outputPath)

	writer, err := mmdbwriter.New(
		mmdbwriter.Options{
			DatabaseType: "GeoCN",
			Languages:    []string{"zh-CN"},
			Description:  map[string]string{"zh-CN": "GeoCN mmdb"},
		},
	)
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
