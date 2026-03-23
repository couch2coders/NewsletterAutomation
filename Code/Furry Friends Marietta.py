#!/usr/bin/env python
# coding: utf-8

# # Newsletter Automation

# ## Package installation

# In[ ]:


# !pip install anthropic


# In[ ]:


# !pip install google-api-python-client google-auth
# !pip install google-auth-oauthlib
# %pip install anthropic requests python-dotenv schedule


# In[1]:


import os
import json
import time
import random
import schedule
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic


# In[3]:


#claude api key ---need to find where to store later


# In[5]:


# pip install python-dotenv


# ### Humane Society Pull

# In[8]:


from bs4 import BeautifulSoup
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def fetch_with_zyte(url, retries=2):
    for attempt in range(retries):
        try:
            response = requests.post(
                "https://api.zyte.com/v1/extract",
                auth=(ZYTE_API_KEY, ""),
                json={"url": url, "browserHtml": True},
                timeout=120
            )
            return response.json()["browserHtml"]
        except requests.exceptions.ReadTimeout:
            print(f"Timeout on attempt {attempt + 1} for {url}")
            if attempt < retries - 1:
                time.sleep(3)
            else:
                print(f"Skipping {url} after {retries} attempts")
                return None

def fetch_and_parse(url):
    html = fetch_with_zyte(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    clean_text = soup.get_text(separator="\n", strip=True)
    return url, soup, clean_text

# Fetch Marietta cat links
html = fetch_with_zyte("https://atlantahumane.org/adopt/cats/?PrimaryBreed=0&Location_4=Marietta&PrimaryColor=0&search=+Search+&ClientID=13&Species=Cat")
soup = BeautifulSoup(html, "html.parser")
for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
    tag.decompose()
links = soup.find_all("a", href=True)
pet_links = list(set([a["href"] for a in links if "/adopt/" in a["href"] and "aid=" in a["href"]]))
print(f"Found {len(pet_links)} Marietta cats total")

# Fetch all pet pages in parallel and filter
humane_society_pets_with_description = []

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(fetch_and_parse, url): url for url in pet_links}
    for future in as_completed(futures):
        result = future.result()
        if result is None:
            continue
        url, soup, clean_text = result

        if "Adoption Fee:" in clean_text:
            after_fee = clean_text.split("Adoption Fee:")[1]
            remaining = "\n".join(after_fee.strip().split("\n")[2:]).strip()

            if len(remaining) > 100 and "PetBridge" not in remaining[:150]:
                images = soup.find_all("img")
                pet_photos = [
                    img.get("src")
                    for img in images
                    if img.get("src") and "petango.com" in img.get("src")
                ]
                humane_society_pets_with_description.append({
                    "url": url,
                    "profile": clean_text,
                    "photos": pet_photos
                })
                print(f"✓ Has description: {url} | {len(pet_photos)} photos")
            else:
                print(f"✗ No description: {url}")

print(f"\n{len(humane_society_pets_with_description)} cats with descriptions found")


# ### Petfinder Pull

# In[10]:


import time
from bs4 import BeautifulSoup

MAX_WITH_DESCRIPTION = 5
MAX_TOTAL_FETCHED = 10
MAX_LISTING_PAGES = 3  # caps how many listing pages we scrape

BASE_URL = "https://www.petfinder.com"
LISTING_URL = "https://www.petfinder.com/search/cats-for-adoption/us/ga/eastcobb/?includeOutOfTown=true&distance=25&page={page}"

# Step 1 -- collect candidate links across multiple listing pages
all_pet_links = []

for page in range(1, MAX_LISTING_PAGES + 1):
    print(f"Fetching listing page {page}...")
    html = fetch_with_zyte(LISTING_URL.format(page=page))
    if html is None:
        break
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    links = soup.find_all("a", href=True)
    page_links = list(set([
        a["href"] for a in links
        if "/cat/" in a["href"] and "/details/" in a["href"]
    ]))
    all_pet_links.extend(page_links)
    print(f"  Found {len(page_links)} links on page {page} ({len(all_pet_links)} total)")
    time.sleep(1)

# Deduplicate
all_pet_links = list(set(all_pet_links))
full_pet_links = [BASE_URL + link for link in all_pet_links]
print(f"\n{len(full_pet_links)} total candidate links collected")

# Step 2 -- fetch detail pages with early stop
pet_finder_pets_with_descriptions = []
total_fetched = 0

for url in full_pet_links:
    if len(pet_finder_pets_with_descriptions) >= MAX_WITH_DESCRIPTION:
        print("Reached 5 pets with descriptions. Stopping.")
        break
    if total_fetched >= MAX_TOTAL_FETCHED:
        print("Reached 10 total fetches. Stopping.")
        break

    html = fetch_with_zyte(url)
    total_fetched += 1
    if html is None:
        continue

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    clean_text = soup.get_text(separator="\n", strip=True)

    if "Story" in clean_text and len(clean_text) > 500:
        images = soup.find_all("img")
        pet_photos = [
            img.get("src") for img in images
            if img.get("src") and ("petfinder" in img.get("src") or "petango" in img.get("src"))
        ]
        pet_finder_pets_with_descriptions.append({
            "url": url,
            "profile": clean_text,
            "photos": pet_photos
        })
        print(f"✓ {total_fetched} fetched | {len(pet_finder_pets_with_descriptions)} with description: {url}")
    else:
        print(f"✗ No description: {url}")

    time.sleep(1)

print(f"\nDone. {len(pet_finder_pets_with_descriptions)} cats with descriptions from {total_fetched} fetched.")


# ### Prepping scraped data into flat set

# In[16]:


# Combine both sources
all_pets = pet_finder_pets_with_descriptions + humane_society_pets_with_description # petfinder + humane society

# Format all profiles for Claude
combined_profiles = ""
for i, pet in enumerate(all_pets, 1):
    combined_profiles += f"""
--- Pet {i} ---
Source URL: {pet['url']}
Photos: {', '.join(pet['photos'][:2]) if pet['photos'] else 'None'}
Profile:
{pet['profile'][:2000]}

"""


# In[18]:


# Check the first pet we already have
for i, pet in enumerate(all_pets):
    html = fetch_with_zyte(pet['url'])
    if html is None:
        continue
    soup = BeautifulSoup(html, "html.parser")
    images = soup.find_all("img")

    if "petfinder.com" in pet['url']:
        pet_photos = [
            img.get("src") for img in images
            if img.get("src") and "cloudfront.net" in img.get("src")
            and "Enlarge" not in (img.get("alt") or "")
        ][:3]
    else:  # Atlanta Humane
        pet_photos = [
            img.get("src") for img in images
            if img.get("src") and "petango.com" in img.get("src")
        ][:3]

    all_pets[i]['photos'] = pet_photos
    print(f"✓ {pet['url']} -- {len(pet_photos)} photos")
    time.sleep(1)


# In[19]:


from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io


# notes, will need to figure out how to work pipeline without having to manually authenticate
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
OAUTH_FILE = "/Users/couch2coders/Downloads/CLINE_SECRET_CLAUDE.json" #this is the code file that links python to gdrive

# Auth
flow = InstalledAppFlow.from_client_secrets_file(OAUTH_FILE, SCOPES)
creds = flow.run_local_server(port=0)
service = build("drive", "v3", credentials=creds)

# Find the file by name
results = service.files().list(
    q="name='newsletter-pet-adoption-skill_auto.md'",
    fields="files(id, name)"
).execute()

files = results.get("files", [])
if not files:
    raise FileNotFoundError("newsletter-pet-adoption-skill.md not found in Google Drive")

file_id = files[0]["id"]
print(f"Found file: {files[0]['name']} (ID: {file_id})")

# Download it
request = service.files().get_media(fileId=file_id)
buffer = io.BytesIO()
downloader = MediaIoBaseDownload(buffer, request)

done = False
while not done:
    _, done = downloader.next_chunk()

skill_prompt = buffer.getvalue().decode("utf-8")
print("Downloaded successfully. Preview:")
print(skill_prompt[:500])


# In[26]:


import os
import anthropic

client = anthropic.Anthropic(api_key=claude_api_key)


# In[30]:


response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    system=skill_prompt,
    messages=[{
        "role": "user",
        "content": f"""
Here are up to 7 adoptable cats from shelters near East Cobb, GA.
Review all of them and pick the one with the best story potential.
Write the East Cobb Connect adoption blurb for that pet only.
Use the pet's actual description -- do not invent details.

Return ONLY a JSON object with no preamble, explanation, or markdown. 
Exact format:
{{
  "pet_name": "Patrick Star",
  "shelter_name": "Good Mews Animal Foundation",
  "blurb": "Full blurb text here...",
  "shelter_address": "3805 Robinson Road NW, Marietta, GA 30067",
  "shelter_phone": "(770) 499-2287",
  "shelter_email": "adopt@goodmews.org",
  "shelter_hours": "Mon-Fri 12-6pm, Sat-Sun 11am-5pm",
  "source_url": "https://...",
  "photo_url": "https://... or null"
}}

{combined_profiles}
"""
    }]
)

blurb = next(block.text for block in response.content if block.type == "text")
print(blurb)


# In[32]:


import json

raw = next(block.text for block in response.content if block.type == "text")
data = json.loads(raw)

# Access any field directly
print(data["pet_name"])    # Patrick Star
print(data["blurb"])       # Full blurb text
print(data["source_url"])  # https://...


# In[ ]:


import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# --- Fill these in ---
CREDENTIALS_FILE = "/Users/couch2coders/Downloads/couch2coding-fb9ed9b51c5f.JSON"  # path to your JSON file on your computer
FOLDER_ID = "1OJqZnOiW47ysn_lJkW6ygL0T98TMUa-5"

# --- Connect to Drive ---
creds = Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=["https://www.googleapis.com/auth/drive"]
)

service = build("drive", "v3", credentials=creds)

# --- Upload a test file ---
from googleapiclient.http import MediaInMemoryUpload

file_metadata = {
    "name": "test_connection.txt",
    "parents": [FOLDER_ID]
}

media = MediaInMemoryUpload(b"Connection works!", mimetype="text/plain")

file = service.files().create(
    body=file_metadata,
    media_body=media
).execute()

print(f"Success! File uploaded with ID: {file.get('id')}")

