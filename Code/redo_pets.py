#!/usr/bin/env python3
"""
Redo pet selection:
1. Reset statuses in Notion (source of truth)
2. Update pets.json on gh-pages branch directly (skip full rebuild)
"""
import os
import sys
import json
import requests
import base64

sys.path.append(os.path.dirname(__file__))
from notion_helper import redo_pet_selection

NEWSLETTER_NAME = os.environ["NEWSLETTER_NAME"]
GITHUB_TOKEN    = os.environ["GITHUB_TOKEN"]
GITHUB_OWNER    = "couch2coders"
GITHUB_REPO     = "NewsletterAutomation"
FILE_PATH       = "pets.json"
BRANCH          = "gh-pages"

# 1. Reset in Notion
redo_pet_selection(NEWSLETTER_NAME)
print("✓ Notion statuses reset")

# 2. Fetch current JSON from gh-pages
headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
file_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{FILE_PATH}?ref={BRANCH}"
res = requests.get(file_url, headers=headers)
res.raise_for_status()
file_info = res.json()

content = json.loads(base64.b64decode(file_info["content"]).decode("utf-8"))

# 3. Update statuses for this newsletter back to pending
changed = 0
for item in content:
    if item.get("newsletter_name") == NEWSLETTER_NAME and item.get("status") in ("approved", "rejected", "Approved", "Rejected"):
        item["status"] = "pending"
        changed += 1

print(f"✓ Reset {changed} pets to pending in JSON")

# 4. Commit updated JSON back to gh-pages
updated_content = base64.b64encode(json.dumps(content, indent=2).encode("utf-8")).decode("utf-8")
commit_res = requests.put(
    file_url,
    headers=headers,
    json={
        "message": f"redo: reset {NEWSLETTER_NAME} pets to pending",
        "content": updated_content,
        "sha": file_info["sha"],
        "branch": BRANCH
    }
)
commit_res.raise_for_status()
print("✓ JSON updated on gh-pages")
