#!/usr/bin/env python3
"""修改 daily-update.yml 的 cron 定时"""
import re, sys
from datetime import timezone, timedelta

hour = int(sys.argv[1])
minute = int(sys.argv[2])

# 北京转UTC
utc_h = (hour - 8) % 24
cron = f"{minute} {utc_h} * * *"

path = ".github/workflows/daily-update.yml"
with open(path, "r") as f:
    content = f.read()

content = re.sub(
    r"cron: '[^']+'",
    f"cron: '{cron}'",
    content,
    count=1
)

with open(path, "w") as f:
    f.write(content)

print(f"OK: cron={cron} (北京 {hour:02d}:{minute:02d})")
