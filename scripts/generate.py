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

CATEGORIES = [
    ("work", "职场技能", "36氪、人人都是产品经理、哈佛商业评论"),
    ("life", "生活技巧", "知乎日报、下厨房、国家地理"),
    ("science", "科普常识", "维基百科、果壳、科学美国人"),
    ("health", "健康养生", "丁香医生、健康时报、Mayo Clinic"),
    ("tool", "效率工具", "小众软件、反斗软件、GitHub")
]

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    data["last_updated"] = TODAY
    data["today"] = TODAY
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def archive_old(data):
    if data.get("today") and data["today"] in data.get("knowledge", {}):
        old_items = data["knowledge"].get(data["today"], [])
        if old_items:
            data.setdefault("archive", {})[data["today"]] = old_items
        del data["knowledge"][data["today"]]

def get_max_ids(data):
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
    global API_KEY
    if not API_KEY:
        print("ERROR: DEEPSEEK_KEY 未设置")
        # Try to read from config.py if exists (for local testing)
        if os.path.exists("config.py"):
            try:
                exec(open("config.py").read())
                API_KEY = globals().get("DEEPSEEK_KEY", "")
            except: pass
        if not API_KEY:
            sys.exit(1)
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
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
            "max_tokens": 2500
        },
        timeout=90
    )
    if resp.status_code != 200:
        print(f"ERROR API: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    return resp.json()["choices"][0]["message"]["content"]

def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    # Try direct parse first
    try:
        return json.loads(text)
    except:
        pass
    # Try find { ... }
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group())
        except:
            pass
    print(f"ERROR: 无法解析JSON:\n{text[:300]}")
    sys.exit(1)

def build_prompt(prefix, cname, src, next_id):
    return f"""请生成一条关于"{cname}"的知识条目，基于真实权威信息（参考来源：{src}），严禁编造。

直接输出以下JSON格式（不要markdown代码块）：
{{"id": "{prefix}_{next_id:03d}", "cat": "{cname}", "title": "精简标题", "summary": "一句话简介", "detail": "<h4>小标题</h4><ul><li><b>步骤：</b>详细说明</li></ul>", "source": "具体来源", "tags": ["标签1","标签2"]}}

要求：
- title用一句话说清楚核心
- summary用一句话简介
- detail用HTML格式（h4标题+ul/li列表+b加粗），操作类必须有可复现的具体步骤
- source必须标注具体来源
- tags写2-3个标签"""

def generate_today(data):
    max_ids = get_max_ids(data)
    today_items = []
    for prefix, cname, src in CATEGORIES:
        next_id = max_ids[prefix] + 1
        prompt = build_prompt(prefix, cname, src, next_id)
        print(f"  生成 [{cname}]...", end=" ", flush=True)
        text = call_deepseek(prompt)
        item = parse_json(text)
        today_items.append(item)
        max_ids[prefix] = max(max_ids[prefix], int(re.search(r'(\d+)', item["id"]).group(1)))
        print(f"✅ {item['title'][:30]}")
    data.setdefault("knowledge", {})[TODAY] = today_items

def update_index(data):
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        html = f.read()
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    html = re.sub(r'var DATA = \{[\s\S]*?\};', 'var DATA = ' + json_str + ';', html)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print("  已更新 index.html")

def main():
    print(f"📚 每日知识更新 - {TODAY}")
    data = load_data()
    print(f"   当前 today: {data.get('today')}")
    if data.get("knowledge", {}).get(TODAY):
        print(f"   今天({TODAY})已有内容，跳过生成")
        update_index(data)
        return
    archive_old(data)
    print(f"   归档完成，开始生成...")
    generate_today(data)
    save_data(data)
    update_index(data)
    items = data["knowledge"].get(TODAY, [])
    print(f"\n✅ 完成！今日 {len(items)} 条知识")
    for it in items:
        print(f"   [{it['cat']}] {it['title']}")

if __name__ == "__main__":
    main()
