#!/usr/bin/env python3
import os
import sys
sys.path.append(os.path.dirname(__file__))
from notion_helper import approve_pet_in_notion

APPROVED_URL = os.environ["APPROVED_URL"]
approve_pet_in_notion(APPROVED_URL)
