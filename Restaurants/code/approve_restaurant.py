#!/usr/bin/env python3
import os
import sys
import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'Code'))
from notion_helper import approve_restaurant_in_notion

APPROVED_PLACE_ID = os.environ["APPROVED_PLACE_ID"]
GITHUB_TOKEN      = os.environ["GITHUB_TOKEN"]
GITHUB_OWNER      = "couch2coders"
GITHUB_REPO       = "NewsletterAutomation"

# Update Notion
approve_restaurant_in_notion(APPROVED_PLACE_ID)

# Trigger deploy to refresh JSON
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
