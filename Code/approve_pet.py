import os
import json
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS_JSON"]
GSHEET_ID               = os.environ["GSHEET_ID"]
APPROVED_URL            = os.environ["APPROVED_URL"]
BEEHIIV_API_KEY         = os.environ["BEEHIIV_API_KEY"]
BEEHIIV_PUB_ID          = os.environ["BEEHIIV_PUBLICATION_ID"]
BEEHIIV_TEMPLATE_ID     = "742a1712-66f9-4d9d-8fbf-af02abfb7bdd"
GSHEET_TAB              = "Pets"

creds = Credentials.from_service_account_info(
    json.loads(GOOGLE_CREDENTIALS_JSON),
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
sheets_service = build("sheets", "v4", credentials=creds)

# Read all rows
result = sheets_service.spreadsheets().values().get(
    spreadsheetId=GSHEET_ID,
    range=f"{GSHEET_TAB}!A:M"
).execute()
rows = result.get("values", [])

# Find pending rows and update status
updates = []
approved_row = None

for i, row in enumerate(rows[1:], start=2):
    if len(row) < 11:
        continue
    url    = row[0]
    status = row[10]
    if status == "pending":
        new_status = "approved" if url == APPROVED_URL else "rejected"
        updates.append({
            "range": f"{GSHEET_TAB}!K{i}",
            "values": [[new_status]]
        })
        print(f"{new_status}: {url}")
        if new_status == "approved":
            approved_row = row

if updates:
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=GSHEET_ID,
        body={"valueInputOption": "RAW", "data": updates}
    ).execute()
    print(f"Updated {len(updates)} rows")

# Push approved pet to Beehiiv
if approved_row:
    pet_name        = approved_row[1]
    shelter_name    = approved_row[2]
    blurb           = approved_row[3]
    shelter_address = approved_row[4]
    shelter_phone   = approved_row[5]
    shelter_email   = approved_row[6]
    shelter_hours   = approved_row[7]
    photo_url       = approved_row[8] if len(approved_row) > 8 else ""
    source_url      = approved_row[0]
   
    # Load template from repo
    from pathlib import Path
    
    template_path = Path(__file__).parent / "templates" / "east_cobb_connect.html"
    template_html = template_path.read_text(encoding="utf-8")
    
    # Swap placeholders
    photo_tag = f'<img src="{photo_url}" alt="{pet_name}" style="width:100%;border-radius:12px;margin-bottom:16px;" />' if photo_url else ""
    
    content_html = template_html \
        .replace("{PET_NAME}", pet_name) \
        .replace("{PET_BLURB}", blurb) \
        .replace("{PET_PHOTO}", photo_tag) \
        .replace("{PET_SHELTER_NAME}", shelter_name) \
        .replace("{PET_SHELTER_ADDRESS}", shelter_address) \
        .replace("{PET_SHELTER_PHONE}", shelter_phone) \
        .replace("{PET_SHELTER_EMAIL}", shelter_email) \
        .replace("{PET_SHELTER_HOURS}", shelter_hours) \
        .replace("{PET_SOURCE_URL}", source_url)

    # Create Beehiiv draft
    draft_res = requests.post(
        f"https://api.beehiiv.com/v2/publications/{BEEHIIV_PUB_ID}/posts",
        headers={
            "Authorization": f"Bearer {BEEHIIV_API_KEY}",
            "Content-Type": "application/json"
        },

        json={
            "title": f"Meet {pet_name} | East Cobb Connect",
            "subject": f"Meet {pet_name} 🐾 | East Cobb Connect",
            "body_content": content_html,
            "status": "draft",
            "platform": "email"
        }
    )

    print(f"Beehiiv status: {draft_res.status_code}")
    print(f"Beehiiv response: {draft_res.text[:500]}")
    
    if draft_res.status_code in [200, 201]:
        data = draft_res.json()
        post_id = data.get("data", {}).get("id")
        print(f"Beehiiv draft created: {post_id}")
        print(f"View at: https://app.beehiiv.com/publications/{BEEHIIV_PUB_ID}/posts/{post_id}")
    else:
        print(f"Beehiiv error: {draft_res.status_code} {draft_res.text}")
