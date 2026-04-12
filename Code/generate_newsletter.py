#!/usr/bin/env python3
"""
Simplified Newsletter Generator — East Cobb Connect
Runs all 4 sections, picks default winners, outputs to README.md.
No Notion, no UI, no manual approval needed.
"""
import os
import sys
import json
import time
import math
import re
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import requests
import anthropic

# ---------------------------------------------------------------------------
# ENVIRONMENT
# ---------------------------------------------------------------------------
CLAUDE_API_KEY      = os.environ["CLAUDE_API_KEY"]
APIFY_API_KEY       = os.environ["APIFY_API_KEY"]
GOOGLE_PLACES_API_KEY = os.environ["GOOGLE_PLACES_API_KEY"]
REALTOR_API_KEY     = os.environ["REALTOR_API_KEY"]
BRAVE_NEWS_API_KEY  = os.environ["BRAVE_NEWS_API_KEY"]

NEWSLETTER = {"name": "East_Cobb_Connect", "zip": "30062", "state": "ga",
              "lat": 33.9773, "lng": -84.5130, "display": "East Cobb"}

SKILLS_DIR = Path(__file__).parent.parent / "Skills"
OUTPUT_DIR = Path(__file__).parent.parent / "images"
OUTPUT_DIR.mkdir(exist_ok=True)

APIFY_TIMEOUT = 300


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def claude_call(system_prompt: str, user_prompt: str, max_tokens: int = 4000) -> str:
    """Call Claude with retry logic."""
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return next(b.text for b in response.content if b.type == "text")
        except Exception as e:
            if attempt < 2:
                print(f"  Claude error (attempt {attempt + 1}): {e}")
                time.sleep(10 * (attempt + 1))
            else:
                raise


def claude_json(system_prompt: str, user_prompt: str) -> list | dict:
    """Call Claude and parse JSON response."""
    raw = claude_call(system_prompt, user_prompt)
    clean = raw.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(clean)


SKILL_ENV_MAP = {
    "newsletter-pet-adoption-skill_auto.md": "SKILL_PETS",
    "newsletter-restaurant-blurb-skill.md": "SKILL_RESTAURANTS",
    "newsletter-local-lowdown-skill_auto.md": "SKILL_LOWDOWN",
    "newsletter-real-estate-skill_auto.md": "SKILL_REAL_ESTATE",
}


def load_skill(name: str) -> str:
    """Load skill from environment variable (for public repo) or file (for local dev)."""
    env_key = SKILL_ENV_MAP.get(name, "")
    if env_key and os.environ.get(env_key):
        return os.environ[env_key]
    path = SKILLS_DIR / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def clean_text(text: str) -> str:
    """Fix encoding issues from scraped text."""
    import html as html_module
    if not text:
        return ""
    text = html_module.unescape(text)
    try:
        text = text.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u00a0", " ")
    return text.strip()


# ---------------------------------------------------------------------------
# 1. PETS — Petfinder via Apify
# ---------------------------------------------------------------------------
def fetch_html_apify(urls: list, retries: int = 3) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {APIFY_API_KEY}"}
    for attempt in range(retries):
        try:
            print(f"  Apify: fetching {len(urls)} pages...")
            res = requests.post(
                "https://api.apify.com/v2/acts/apify~web-scraper/run-sync-get-dataset-items",
                headers=headers,
                json={
                    "startUrls": [{"url": u} for u in urls],
                    "pageFunction": "async function pageFunction(context) { return { url: context.request.url, html: document.documentElement.outerHTML }; }",
                    "maxConcurrency": 5,
                    "maxRequestsPerCrawl": len(urls),
                },
                timeout=APIFY_TIMEOUT,
            )
            if res.status_code not in (200, 201):
                if attempt < retries - 1:
                    time.sleep(10)
                    continue
                return {}
            result = {}
            for item in res.json():
                u, h = item.get("url", ""), item.get("html", "")
                if u and h:
                    result[u] = h
            print(f"  Apify returned {len(result)} pages")
            return result
        except Exception as e:
            print(f"  Apify error: {e}")
            if attempt < retries - 1:
                time.sleep(10)
    return {}


def generate_pets():
    print("\n" + "="*60)
    print("  🐾 PETS")
    print("="*60)

    from bs4 import BeautifulSoup

    # Scrape search pages
    search_urls = [
        f"https://www.petfinder.com/search/cats-for-adoption/us/{NEWSLETTER['state']}/{NEWSLETTER['zip']}/",
        f"https://www.petfinder.com/search/dogs-for-adoption/us/{NEWSLETTER['state']}/{NEWSLETTER['zip']}/",
    ]
    search_cache = fetch_html_apify(search_urls)

    all_pets = []
    for species in ["cat", "dog"]:
        search_url = [u for u in search_urls if species in u][0]
        html = search_cache.get(search_url, "")
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        candidates = []
        for link in soup.select("a[href]"):
            href = link.get("href", "")
            if f"/{species}/" not in href or "/search/" in href or href in seen:
                continue
            seen.add(href)
            card = link.parent.parent if link.parent else None
            if not card:
                continue
            name_el = card.select_one("div.tw-font-extrabold")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            pet_url = f"https://www.petfinder.com{href}" if href.startswith("/") else href

            # Age/gender
            info_div = card.select_one("div.tw-text-primary-600")
            age_gender = info_div.select_one("span").get_text(strip=True) if info_div and info_div.select_one("span") else ""
            age, gender = ("", "")
            if "•" in age_gender:
                parts = [p.strip() for p in age_gender.split("•")]
                age, gender = (parts[0], parts[1]) if len(parts) > 1 else (parts[0], "")

            breed_el = card.select_one("span.tw-truncate")
            breed = breed_el.get_text(strip=True) if breed_el else ""
            img_el = link.select_one("img")
            photo = (img_el.get("src") or "") if img_el else ""

            candidates.append({"name": name, "url": pet_url, "species": species,
                              "breed": breed, "age": age, "gender": gender, "photos": [photo] if photo else []})
            if len(candidates) >= 5:
                break

        # Scrape detail pages
        detail_urls = [c["url"].rstrip("/") for c in candidates[:5]]
        if detail_urls:
            detail_cache = fetch_html_apify(detail_urls)
            for c in candidates:
                detail_html = detail_cache.get(c["url"].rstrip("/"), "")
                if not detail_html:
                    continue
                dsoup = BeautifulSoup(detail_html, "html.parser")

                # Get description and org from __NEXT_DATA__
                nd_tag = dsoup.find("script", id="__NEXT_DATA__")
                if nd_tag:
                    try:
                        nd = json.loads(nd_tag.string)
                        pp = nd.get("props", {}).get("pageProps", {})
                        animal = pp.get("animal") or {}
                        c["description"] = clean_text(animal.get("description", ""))
                        org = pp.get("organization", {})
                        loc = (org.get("primaryLocation") or {})
                        loc_addr = loc.get("address") or {}
                        c["shelter_name"] = org.get("organizationName", "")
                        c["shelter_address"] = " ".join(filter(None, [loc_addr.get("street", ""), loc_addr.get("city", ""), loc_addr.get("state", ""), loc_addr.get("postalCode", "")])).strip()
                        c["shelter_phone"] = loc.get("phone", "")
                        c["shelter_email"] = loc.get("email", "")
                    except Exception:
                        pass

                # Get photos from Swiper
                dom_photos = []
                for slide in dsoup.select(".swiper-slide img"):
                    src = slide.get("src", "")
                    if src and "cloudfront" in src:
                        dom_photos.append(src)
                if len(dom_photos) > len(c.get("photos", [])):
                    c["photos"] = dom_photos[:3]

        # Filter pets with descriptions
        valid = [c for c in candidates if c.get("description") and len(c["description"]) > 30]
        all_pets.extend(valid[:3])

    if not all_pets:
        return {"markdown": "*No pets found this week.*", "winner": None}

    # Generate blurbs
    skill = load_skill("newsletter-pet-adoption-skill_auto.md")
    profiles = "\n".join([f"--- Pet {i+1} ---\nSource URL: {p['url']}\nProfile:\nName: {p['name']}\nSpecies: {p['species']}\nBreed: {p.get('breed','')}\nAge: {p.get('age','')}\nGender: {p.get('gender','')}\nDescription: {p.get('description','')}\nShelter: {p.get('shelter_name','')}\nAddress: {p.get('shelter_address','')}\nPhone: {p.get('shelter_phone','')}\nEmail: {p.get('shelter_email','')}" for i, p in enumerate(all_pets)])

    results = claude_json(skill, f"Here are adoptable pets from shelters near East Cobb, GA.\nPick the TOP 3 and write a blurb for each.\nReturn ONLY a JSON array.\n\n{profiles}")

    # Normalize field names (Claude may return 'name' or 'pet_name', etc.)
    for r in results:
        r["pet_name"] = r.get("pet_name") or r.get("name", "Unknown")
        r["source_url"] = r.get("source_url") or r.get("url", "")
        r["blurb"] = r.get("blurb") or r.get("description", "")
        r["shelter_name"] = r.get("shelter_name") or r.get("shelter", "")
    print(f"  Claude returned {len(results)} pet blurbs")

    # Score — pick highest by blurb quality (skip separate scoring call to save time)
    for i, r in enumerate(results):
        r["total_score"] = len(results) - i  # Simple rank-based score

    winner = results[0] if results else None

    # Map photos back by URL and name
    photo_map_url = {p["url"]: p for p in all_pets}
    photo_map_name = {p["name"].lower(): p for p in all_pets}

    # Generate WebP for winner
    if winner:
        pet_name = winner.get("pet_name", "")
        # Find the original pet data
        orig = photo_map_url.get(winner.get("source_url", "")) or photo_map_name.get(pet_name.lower(), {})
        photos = orig.get("photos", [])
        source_url = orig.get("url", winner.get("source_url", ""))
        winner["source_url"] = source_url
        shelter = orig.get("shelter_name", "")

        print(f"  Winner: {pet_name} | {len(photos)} photos | {source_url[:50]}")

        if len(photos) >= 2:
            from gif_maker import create_gif_from_urls
            webp = create_gif_from_urls(photos[:3], crop_top=True)
            if webp:
                path = OUTPUT_DIR / f"pet_winner_{datetime.today().strftime('%Y%m%d')}.webp"
                path.write_bytes(webp)
                winner["webp_path"] = str(path)
                print(f"  ✓ Pet WebP: {len(webp):,} bytes")
        elif len(photos) == 1:
            winner["single_photo"] = photos[0]

    # Build markdown
    md = ""
    if winner:
        pet_name = winner.get("pet_name", "Unknown")
        md += f"**{pet_name}**\n\n"
        if winner.get("webp_path"):
            img_name = Path(winner["webp_path"]).name
            md += f"![{pet_name}](images/{img_name})\n\n"
        elif winner.get("single_photo"):
            md += f"![{pet_name}]({winner['single_photo']})\n\n"
        md += f"{winner.get('blurb', '')}\n\n"
        if winner.get("source_url"):
            md += f"[Meet {pet_name} →]({winner['source_url']})\n"

    return {"markdown": md, "winner": winner}


# ---------------------------------------------------------------------------
# 2. RESTAURANTS — Google Places API
# ---------------------------------------------------------------------------
def generate_restaurants():
    print("\n" + "="*60)
    print("  🍽️ RESTAURANTS")
    print("="*60)

    KNOWN_CHAINS = {"mcdonald's", "starbucks", "chick-fil-a", "subway", "burger king", "wendy's",
                    "taco bell", "chipotle", "panera bread", "olive garden", "applebee's", "chili's",
                    "ihop", "waffle house", "cracker barrel", "buffalo wild wings", "outback steakhouse",
                    "texas roadhouse", "domino's", "pizza hut", "five guys", "zaxby's", "popeyes",
                    "dave & buster's", "golden corral", "panda express"}

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.googleMapsUri,places.rating,places.userRatingCount,places.priceLevel,places.photos,places.primaryTypeDisplayName,places.editorialSummary,places.reviews"
    }

    all_places = []
    for rank in ["POPULARITY", "DISTANCE"]:
        try:
            res = requests.post(url, headers=headers, json={
                "includedTypes": ["restaurant"], "maxResultCount": 20,
                "locationRestriction": {"circle": {"center": {"latitude": NEWSLETTER["lat"], "longitude": NEWSLETTER["lng"]}, "radius": 8047}},
                "rankPreference": rank,
            }, timeout=30)
            if res.status_code == 200:
                all_places.extend(res.json().get("places", []))
            time.sleep(1)
        except Exception as e:
            print(f"  Places error: {e}")

    # Deduplicate and filter
    seen = set()
    restaurants = []
    for place in all_places:
        pid = place.get("id", "")
        if pid in seen:
            continue
        seen.add(pid)
        name = place.get("displayName", {}).get("text", "")
        if any(c in name.lower() for c in KNOWN_CHAINS):
            continue
        rating = place.get("rating", 0)
        reviews = place.get("userRatingCount", 0)
        if rating < 4.0 or reviews < 50:
            continue

        # Get up to 3 photos
        photo_urls = []
        for p in place.get("photos", [])[:3]:
            ref = p.get("name", "")
            if ref:
                try:
                    pr = requests.get(f"https://places.googleapis.com/v1/{ref}/media?maxHeightPx=800&skipHttpRedirect=true&key={GOOGLE_PLACES_API_KEY}", timeout=10)
                    if pr.status_code == 200:
                        pu = pr.json().get("photoUri", "")
                        if pu:
                            photo_urls.append(pu)
                except Exception:
                    pass

        cuisine = place.get("primaryTypeDisplayName", {}).get("text", "Restaurant")
        summary = place.get("editorialSummary", {}).get("text", "")
        if not summary:
            rvs = place.get("reviews", [])
            if rvs:
                summary = rvs[0].get("text", {}).get("text", "")

        restaurants.append({
            "place_id": pid, "name": name, "cuisine": cuisine,
            "address": place.get("formattedAddress", ""),
            "phone": place.get("nationalPhoneNumber", ""),
            "website": place.get("websiteUri", ""),
            "maps_url": place.get("googleMapsUri", ""),
            "rating": rating, "review_count": reviews,
            "price_level": place.get("priceLevel", ""),
            "photo_url": photo_urls[0] if photo_urls else "",
            "photo_urls": photo_urls,
            "summary": summary[:500] if summary else "",
        })
        if len(restaurants) >= 5:
            break

    if not restaurants:
        return {"markdown": "*No restaurants found this week.*"}

    # Generate blurbs
    skill = load_skill("newsletter-restaurant-blurb-skill.md")
    combined = "\n".join([f"--- Restaurant {i+1} ---\nName: {r['name']}\nCuisine: {r['cuisine']}\nAddress: {r['address']}\nRating: {r['rating']} ({r['review_count']} reviews)\nSummary: {r['summary']}" for i, r in enumerate(restaurants)])

    results = claude_json(skill, f"Write a blurb for each restaurant.\nReturn JSON array.\n\n{combined}")

    # Generate WebPs and map filenames
    from gif_maker import create_gif_from_urls
    photo_name_map = {rest["name"]: rest.get("photo_urls", []) for rest in restaurants}
    for r in results:
        rname = r.get("restaurant_name", "")
        photos = photo_name_map.get(rname, [])
        if not photos:
            pid = r.get("place_id", "")
            photos = next((rest["photo_urls"] for rest in restaurants if rest["place_id"] == pid), [])
        if len(photos) >= 2:
            webp = create_gif_from_urls(photos[:3])
            if webp:
                slug = rname[:20].lower().replace(" ", "_").replace("'", "")
                fname = f"rest_{slug}_{datetime.today().strftime('%Y%m%d')}.webp"
                (OUTPUT_DIR / fname).write_bytes(webp)
                r["image_file"] = fname
                print(f"  ✓ {rname} WebP: {len(webp):,} bytes")

    # Build markdown
    md = ""
    for r in results[:5]:
        md += f"**{r.get('restaurant_name', '')}** | {r.get('cuisine_type', '')}\n\n"
        if r.get("image_file"):
            md += f"![{r.get('restaurant_name', '')}](images/{r['image_file']})\n\n"
        md += f"{r.get('blurb', '')}\n\n"
        md += f"📍 {r.get('address', '')} | ⭐ {r.get('rating', '')}\n\n---\n\n"

    return {"markdown": md}


# ---------------------------------------------------------------------------
# 3. LOCAL LOWDOWN — Brave Search
# ---------------------------------------------------------------------------
def generate_lowdown():
    print("\n" + "="*60)
    print("  🗞️ LOCAL LOWDOWN")
    print("="*60)

    EXCLUDED_KEYWORDS = {"murder", "homicide", "killed", "stabbed", "shooting", "assault",
                         "rape", "domestic violence", "arson", "robbery", "carjacking",
                         "trump", "biden", "GOP", "democrat", "republican"}

    def is_paywalled(url):
        try:
            r = requests.get(url, timeout=8, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; newsletter-bot)"})
            if r.status_code in (401, 403, 451):
                return True
            final = r.url.lower()
            if any(kw in final for kw in ["login", "signin", "subscribe", "paywall"]):
                return True
            content = r.text[:10000].lower()
            signals = ["paywall", "metered", "leaky-paywall", "subscribe to read",
                       "subscribers only", "to continue reading", "townnews",
                       "bloxcms", "piano-paywall", "subscription-required"]
            if any(s in content for s in signals):
                return True
        except Exception:
            pass
        return False

    headers = {"Accept": "application/json", "X-Subscription-Token": BRAVE_NEWS_API_KEY}
    articles = []
    seen = set()

    try:
        res = requests.get("https://api.search.brave.com/res/v1/news/search",
                          headers=headers, params={"q": "East Cobb GA news", "count": 15, "freshness": "pw"}, timeout=30)
        if res.status_code == 200:
            for item in res.json().get("results", []):
                url = item.get("url", "")
                title = item.get("title", "")
                if not url or url in seen:
                    continue
                text = f"{title} {item.get('description', '')}".lower()
                if any(kw in text for kw in EXCLUDED_KEYWORDS):
                    print(f"    ✗ Excluded topic: {title[:50]}")
                    continue
                if is_paywalled(url):
                    print(f"    ✗ Paywalled: {title[:50]}")
                    continue
                seen.add(url)
                articles.append({"title": title, "url": url,
                                "source": item.get("meta_url", {}).get("hostname", "") if isinstance(item.get("meta_url"), dict) else "",
                                "summary": item.get("description", "")})
    except Exception as e:
        print(f"  Brave error: {e}")

    if not articles:
        return {"markdown": "*No local news this week.*"}

    skill = load_skill("newsletter-local-lowdown-skill_auto.md")
    result = claude_json(skill, f"Select 3-5 stories for East Cobb Connect.\nReturn JSON.\n\nArticles:\n{json.dumps(articles, indent=2)}")

    # Post-filter: remove paywalled URLs from Claude's output
    for story in result.get("stories", []):
        clean_urls = []
        for src in story.get("source_urls", []):
            url = src.get("url", "")
            if url and not is_paywalled(url):
                clean_urls.append(src)
            else:
                print(f"    ✗ Removed paywalled source: {src.get('label', '')}")
        story["source_urls"] = clean_urls

    md = ""
    for story in result.get("stories", []):
        emoji = story.get("emoji", "")
        headline = story.get("headline", "")
        body = story.get("body", "").replace("\\n\\n", "\n\n").replace("\\n", "\n")
        sources = story.get("source_urls", [])
        source_links = " | ".join(f"[{s['label']}]({s['url']})" for s in sources)
        md += f"### {emoji} {headline}\n\n{body}\n\n"
        if source_links:
            md += f"More: {source_links}\n\n"

    return {"markdown": md}


# ---------------------------------------------------------------------------
# 4. REAL ESTATE — Realtor.com via RapidAPI
# ---------------------------------------------------------------------------
def generate_real_estate():
    print("\n" + "="*60)
    print("  🏠 REAL ESTATE")
    print("="*60)

    headers = {"Content-Type": "application/json", "x-rapidapi-host": "realtor-search.p.rapidapi.com",
               "x-rapidapi-key": REALTOR_API_KEY}

    try:
        res = requests.get("https://realtor-search.p.rapidapi.com/properties/search-buy",
                          headers=headers, params={"location": "city:Marietta, GA", "limit": "20"}, timeout=30)
        listings = res.json().get("data", {}).get("results", [])
    except Exception as e:
        print(f"  Realtor error: {e}")
        return {"markdown": "*No real estate listings this week.*"}

    # Filter by tier
    tiers = [
        {"name": "Starter", "min": 0, "max": 400000, "emoji": "🏠"},
        {"name": "Sweet Spot", "min": 400000, "max": 700000, "emoji": "🏡"},
        {"name": "Showcase", "min": 1000000, "max": None, "emoji": "🏰"},
    ]

    tier_picks = []
    used = set()
    for tier in tiers:
        filtered = [r for r in listings
                    if (r.get("list_price", 0) or 0) >= tier["min"]
                    and (tier["max"] is None or (r.get("list_price", 0) or 0) <= tier["max"])
                    and r.get("property_id") not in used
                    and r.get("primary_photo", {}).get("href", "") and "l-m" in r.get("primary_photo", {}).get("href", "")]
        if filtered:
            pick = filtered[0]
            loc = pick.get("location", {}).get("address", {})
            desc = pick.get("description", {})
            photo = pick.get("primary_photo", {}).get("href", "").replace("http://", "https://")
            if "l-m" in photo:
                photo = re.sub(r's\.jpg$', 'od.jpg', photo)

            # Get multiple photos
            photos = []
            for p in pick.get("photos", [])[:3]:
                pu = p.get("href", "").replace("http://", "https://")
                if "l-m" in pu:
                    pu = re.sub(r's\.jpg$', 'od.jpg', pu)
                    photos.append(pu)

            href = pick.get("href", "")
            listing_url = href if href.startswith("https://") else f"https://www.realtor.com{href}" if href else ""

            tier_picks.append({
                "tier": tier["name"], "emoji": tier["emoji"],
                "price": pick.get("list_price", 0),
                "address": f"{loc.get('line', '')} {loc.get('city', '')} {loc.get('state_code', '')} {loc.get('postal_code', '')}".strip(),
                "beds": desc.get("beds", 0), "baths": desc.get("baths", 0),
                "sqft": desc.get("sqft", 0) or 0,
                "photo_url": photo, "photos": photos,
                "listing_url": listing_url,
            })
            used.add(pick.get("property_id"))

    if not tier_picks:
        return {"markdown": "*No real estate listings this week.*"}

    # Generate blurbs
    skill = load_skill("newsletter-real-estate-skill_auto.md")
    listings_text = "\n".join([f"--- {t['tier']} ---\nPrice: ${t['price']:,}\nAddress: {t['address']}\nBeds: {t['beds']} | Baths: {t['baths']} | Sqft: {t['sqft']:,}\nListing URL: {t['listing_url']}" for t in tier_picks])
    results = claude_json(skill, f"Write Real Estate Corner for East Cobb.\nReturn JSON array.\n\n{listings_text}")

    # Generate template images
    image_map = {}
    try:
        from re_image_maker import generate_re_images
        img_results = generate_re_images(tier_picks, NEWSLETTER["name"], str(OUTPUT_DIR))
        for img in img_results:
            image_map[img["tier"]] = img["image_filename"]
    except Exception as e:
        print(f"  Template image error: {e}")

    # Merge original data into Claude results
    tier_data = {t["tier"]: t for t in tier_picks}
    for r in results:
        tier = r.get("tier", "")
        orig = tier_data.get(tier, {})
        r["price"] = orig.get("price", r.get("price", 0))
        r["address"] = orig.get("address", r.get("address", ""))
        r["beds"] = orig.get("beds", r.get("beds", 0))
        r["baths"] = orig.get("baths", r.get("baths", 0))
        r["sqft"] = orig.get("sqft", r.get("sqft", 0))
        r["listing_url"] = orig.get("listing_url", r.get("listing_url", ""))

    # Build markdown
    md = ""
    for r in results:
        tier = r.get("tier", "")
        emoji = next((t["emoji"] for t in tiers if t["name"] == tier), "🏠")
        price = r.get("price", 0)
        md += f"### {emoji} {tier}: {r.get('headline', '')}\n\n"
        # Embed template image
        img_file = image_map.get(tier, "")
        if img_file:
            md += f"![{tier}](images/{img_file})\n\n"
        md += f"{r.get('blurb', '')}\n\n"
        url = r.get("listing_url", "")
        if url:
            md += f"[View Listing →]({url})\n\n"
        md += "---\n\n"

    return {"markdown": md}


# ---------------------------------------------------------------------------
# ASSEMBLE README
# ---------------------------------------------------------------------------
def assemble_readme(pets, restaurants, lowdown, real_estate):
    today = datetime.today().strftime("%B %d, %Y")
    readme = f"""# 🗞️ East Cobb Connect — Week of {today}

*Auto-generated newsletter content for East Cobb, GA*

---

## 🐾 Furry Friends

{pets['markdown']}

---

## 🍽️ Restaurant Radar

{restaurants['markdown']}

---

## 🗞️ Local Lowdown

{lowdown['markdown']}

---

## 🏠 Real Estate Corner

{real_estate['markdown']}

---

*Generated on {today} by [Newsletter Automation](https://github.com/couch2coders/NewsletterAutomation)*
"""
    readme_path = Path(__file__).parent.parent / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    print(f"\n✓ README.md updated ({len(readme):,} chars)")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"Starting newsletter generation — {datetime.today().strftime('%Y-%m-%d')}")

    pets = generate_pets()
    restaurants = generate_restaurants()
    lowdown = generate_lowdown()
    real_estate = generate_real_estate()

    assemble_readme(pets, restaurants, lowdown, real_estate)
    print("\n✓ All sections complete!")
