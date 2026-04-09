#!/usr/bin/env python3
"""
Cleanup real estate: delete entries older than 8 weeks from Notion.
"""
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'NewsletterCreation', 'Code'))
# Need to set up the RE DB ID before importing
os.environ.setdefault("NOTION_RE_DB_ID", os.environ.get("NOTION_RE_DB_ID", ""))

sys.path.append(os.path.dirname(__file__))
from Real_Estate_Corner import cleanup_old_re_listings

cleanup_old_re_listings()
print("✓ Real estate cleanup complete")
