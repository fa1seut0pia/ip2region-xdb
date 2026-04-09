// 只输入 省、市、区/县、街道/乡镇、社区，名称就可以查询
package main

import (
	"encoding/json"
	"fmt"
	"os"
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
		fmt.Println("need name")
		return
	}
	target := os.Args[1]

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

	// ① 查省（去 0）
	for _, p := range provinces {
		if p.Name == target {
			fmt.Println(trimZero(p.Code))
			return
		}
	}

	// ② 查市（去 0）
	for _, p := range provinces {
		for _, c := range p.Cities {
			if c.Name == target {
				fmt.Println(trimZero(c.Code))
				return
			}
		}
	}

	// ③ 查区县（去 0）
	for _, p := range provinces {
		for _, c := range p.Cities {
			for _, co := range c.Counties {
				if co.Name == target {
					fmt.Println(trimZero(co.Code))
					return
				}
			}
		}
	}

	// ④ 查乡镇（不去 0）
	for _, p := range provinces {
		for _, c := range p.Cities {
			for _, co := range c.Counties {
				for _, t := range co.Towns {
					if t.Name == target {
						fmt.Println(t.Code)
						return
					}
				}
			}
		}
	}

	// ⑤ 查居委会（不去 0）
	for _, p := range provinces {
		for _, c := range p.Cities {
			for _, co := range c.Counties {
				for _, t := range co.Towns {
					for _, cm := range t.Committees {
						if cm.Name == target {
							fmt.Println(cm.Code)
							return
						}
					}
				}
			}
		}
	}

	fmt.Println("not found")
}
