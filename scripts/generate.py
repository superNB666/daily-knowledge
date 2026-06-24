#!/usr/bin/env python3
"""每日知识自动生成脚本 - 由 GitHub Actions 每天调用"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta
import requests

DATA_FILE = "data.json"
INDEX_FILE = "index.html"
API_KEY = os.environ.get("DEEPSEEK_KEY", "")

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")
YESTERDAY = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

CATEGORIES = {
    "work": {"cat": "职场技能", "source": "36氪、人人都是产品经理、哈佛商业评论"},
    "life": {"cat": "生活技巧", "source": "知乎日报、下厨房、国家地理"},
    "science": {"cat": "科普常识", "source": "维基百科、果壳、科学美国人"},
    "health": {"cat": "健康养生", "source": "丁香医生、健康时报、Mayo Clinic"},
    "tool": {"cat": "效率工具", "source": "小众软件、反斗软件、GitHub"}
}

CAT_NAMES = ["职场技能", "生活技巧", "科普常识", "健康养生", "效率工具"]

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    data["last_updated"] = TODAY
    data["today"] = TODAY
    with open(DATA_FILE, "w", encoding="utf-8", ensure_ascii=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def archive_old(data):
    """把昨天的 today 内容归档"""
    if data["today"] in data.get("knowledge", {}):
        old_items = data["knowledge"].get(data["today"], [])
        if old_items:
            data.setdefault("archive", {})[data["today"]] = old_items
        del data["knowledge"][data["today"]]

def get_max_ids(data):
    """从 archive 和 knowledge 中找最大编号"""
    max_ids = {"work": 0, "life": 0, "science": 0, "health": 0, "tool": 0}
    for dk in list(data.get("knowledge", {}).values()) + list(data.get("archive", {}).values()):
        for item in dk:
            iid = item.get("id", "")
            for prefix in max_ids:
                if iid.startswith(prefix + "_"):
                    try:
                        n = int(iid.split("_")[1])
                        max_ids[prefix] = max(max_ids[prefix], n)
                    except:
                        pass
    return max_ids

def call_deepseek(prompt):
    """调用 DeepSeek API 生成内容"""
    if not API_KEY:
        print("ERROR: DEEPSEEK_KEY 未设置")
        sys.exit(1)
    
    resp = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个知识百科助手，生成的内容必须基于真实权威信息，严禁编造。每条知识必须有具体可操作的步骤和明确的来源标注。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        },
        timeout=120
    )
    if resp.status_code != 200:
        print(f"ERROR API: {resp.status_code} {resp.text}")
        sys.exit(1)
    return resp.json()["choices"][0]["message"]["content"]

def build_prompt(max_ids, cat, info):
    prefix, cname, src = cat, info["cat"], info["source"]
    next_id = max_ids[prefix] + 1
    return f"""生成一条关于"{cname}"的知识条目。

要求：
1. 必须基于真实权威信息（参考来源：{src}），严禁编造
2. 标题要精简有力，用一句话概括核心
3. summary 写一句话简介
4. detail 写详细内容，使用 HTML 格式：

格式模板：
<h4>小标题一</h4>
<ul><li><b>加粗关键词：</b>说明文字</li><li><b>关键词：</b>说明文字</li></ul>
<h4>小标题二</h4>
<ul><li>...</li></ul>

5. 操作类内容必须有可复现的具体步骤
6. source 字段填参考来源
7. tags 写2-3个标签

直接输出纯 JSON，不要 markdown 代码块：

{{"id": "{prefix}_{next_id:03d}", "cat": "{cname}", "title": "...", "summary": "...", "detail": "<h4>...</h4><ul>...</ul>", "source": "{src} | ...", "tags": ["标签1","标签2"]}}"""

def parse_json_response(text):
    """从响应中提取 JSON"""
    # 尝试直接解析
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except:
        # 找第一个 { 到最后一个 }
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except:
                pass
    print(f"ERROR: 无法解析JSON响应:\n{text[:500]}")
    sys.exit(1)

def generate_today(data):
    """生成今天的5条知识"""
    max_ids = get_max_ids(data)
    today_items = []
    
    for prefix, info in [("work", CATEGORIES["work"]), ("life", CATEGORIES["life"]),
                         ("science", CATEGORIES["science"]), ("health", CATEGORIES["health"]),
                         ("tool", CATEGORIES["tool"])]:
        prompt = build_prompt(max_ids, prefix, info)
        print(f"  生成 [{info['cat']}]...", end=" ", flush=True)
        text = call_deepseek(prompt)
        item = parse_json_response(text)
        today_items.append(item)
        # 更新最大编号
        max_ids[prefix] = max(max_ids[prefix], int(item["id"].split("_")[1]))
        print(f"✅ {item['title'][:30]}...")
    
    data.setdefault("knowledge", {})[TODAY] = today_items

def update_index(data):
    """更新 index.html 中的内嵌数据"""
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    # 替换 var DATA = {...} 部分
    html = re.sub(
        r'var DATA = \{[\s\S]*?\};',
        'var DATA = ' + json_str + ';',
        html
    )
    
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已更新 index.html（内嵌数据）")

def main():
    print(f"📚 每日知识更新 - {TODAY}")
    
    data = load_data()
    print(f"   当前 today: {data.get('today')}")
    
    # 如果今天已经有内容了，跳过
    if data.get("knowledge", {}).get(TODAY):
        print(f"   今天({TODAY})已有内容，跳过生成")
        # 但仍确保 index.html 是最新的
        update_index(data)
        return
    
    archive_old(data)
    print(f"   归档完成，开始生成新内容...")
    generate_today(data)
    save_data(data)
    update_index(data)
    
    items = data["knowledge"].get(TODAY, [])
    print(f"\n✅ 完成！今日 {len(items)} 条知识")
    for it in items:
        print(f"   [{it['cat']}] {it['title']}")
    print(f"\n📁 data.json 已更新")
    print(f"📁 index.html 已更新")

if __name__ == "__main__":
    main()
