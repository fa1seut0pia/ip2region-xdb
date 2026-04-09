// location.json 多级查询，输入路径用 / 分隔
// 输入示例:
// 北京市
// 北京市/市辖区
// 北京市/市辖区/东城区
// 北京市/市辖区/东城区/东华门街道
// 北京市/市辖区/东城区/东华门街道/多福巷社区居委会

package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

type Committee struct {
	Label string `json:"label"`
	Name  string `json:"name"`
	Code  string `json:"code"`
}

type Town struct {
	Label      string      `json:"label"`
	Name       string      `json:"name"`
	Code       string      `json:"code"`
	Committees []Committee `json:"committees"`
}

type County struct {
	Label string `json:"label"`
	Name  string `json:"name"`
	Code  string `json:"code"`
	Towns []Town `json:"towns"`
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

func trimZero(s string) string {
	for len(s) > 0 && s[len(s)-1] == '0' {
		s = s[:len(s)-1]
	}
	return s
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("need names")
		return
	}

	parts := strings.Split(os.Args[1], "/")
	for i := range parts {
		parts[i] = strings.TrimSpace(parts[i])
	}

	b, err := os.ReadFile("location.json")
	if err != nil {
		fmt.Println(err)
		return
	}

	var provinces []Province
	if err := json.Unmarshal(b, &provinces); err != nil {
		fmt.Println(err)
		return
	}

	// ① 省
	var p *Province
	for i := range provinces {
		if provinces[i].Name == parts[0] {
			p = &provinces[i]
			break
		}
	}
	if p == nil {
		fmt.Println("not found")
		return
	}
	if len(parts) == 1 {
		fmt.Println(trimZero(p.Code))
		return
	}

	// ② 市
	var c *City
	for i := range p.Cities {
		if p.Cities[i].Name == parts[1] {
			c = &p.Cities[i]
			break
		}
	}
	if c == nil {
		fmt.Println("not found")
		return
	}
	if len(parts) == 2 {
		fmt.Println(trimZero(c.Code))
		return
	}

	// ③ 区县
	var co *County
	for i := range c.Counties {
		if c.Counties[i].Name == parts[2] {
			co = &c.Counties[i]
			break
		}
	}
	if co == nil {
		fmt.Println("not found")
		return
	}
	if len(parts) == 3 {
		fmt.Println(trimZero(co.Code))
		return
	}

	// ④ 乡镇（不去 0）
	var t *Town
	for i := range co.Towns {
		if co.Towns[i].Name == parts[3] {
			t = &co.Towns[i]
			break
		}
	}
	if t == nil {
		fmt.Println("not found")
		return
	}
	if len(parts) == 4 {
		fmt.Println(t.Code)
		return
	}

	// ⑤ 居委会（不去 0）
	for _, cm := range t.Committees {
		if cm.Name == parts[4] {
			fmt.Println(cm.Code)
			return
		}
	}

	fmt.Println("not found")
}
