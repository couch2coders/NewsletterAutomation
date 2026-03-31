#!/usr/bin/env python3
import os
import sys
import requests

sys.path.append(os.path.dirname(__file__))
from notion_helper import approve_pet_in_notion

APPROVED_URL   = os.environ["APPROVED_URL"]
GITHUB_TOKEN   = os.environ["GITHUB_TOKEN"]
GITHUB_OWNER   = "couch2coders"
GITHUB_REPO    = "NewsletterAutomation"

# Update Notion
approve_pet_in_notion(APPROVED_URL)

# Trigger export to refresh JSON
res = requests.post(
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/deploy_review_app.yml/dispatches",
    headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    },
    json={"ref": "main"}
)
if res.status_code == 204:
    print("✓ Deploy triggered to refresh JSON data")
else:
    print(f"✗ Deploy trigger failed: {res.status_code}")
