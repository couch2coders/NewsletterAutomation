#!/usr/bin/env python3
"""
Canva OAuth token generator.
1. Opens browser to Canva authorization
2. Canva redirects to GitHub Pages with the auth code
3. You paste the code here
4. Script exchanges it for access + refresh tokens

Usage:
    python canva_auth.py <CLIENT_SECRET>
"""
import sys
import hashlib
import base64
import secrets
import webbrowser
from urllib.parse import urlencode
import requests

CLIENT_ID = "OC-AZ10LQbljNIw"
REDIRECT_URI = "https://couch2coders.github.io/NewsletterAutomation/callback.html"
SCOPES = "design:content:read design:content:write asset:write"

# PKCE
code_verifier = secrets.token_urlsafe(64)[:128]
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()


def main():
    if len(sys.argv) < 2:
        print("Usage: python canva_auth.py <CLIENT_SECRET>")
        sys.exit(1)

    client_secret = sys.argv[1]

    # Step 1: Build authorization URL
    auth_params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(16),
    }
    auth_url = f"https://www.canva.com/api/oauth/authorize?{urlencode(auth_params)}"

    print("\n" + "=" * 60)
    print("  Canva OAuth Authorization")
    print("=" * 60)
    print(f"\n1. Opening your browser...")
    webbrowser.open(auth_url)
    print(f"\n   If it doesn't open, visit:\n   {auth_url}\n")
    print("2. Click 'Allow' in Canva")
    print("3. You'll be redirected to a page showing a code")
    print("4. Copy the code and paste it below:\n")

    auth_code = input("   Paste the authorization code here: ").strip()

    if not auth_code:
        print("\n✗ No code entered.")
        sys.exit(1)

    print(f"\n5. Exchanging code for tokens...")

    # Step 2: Exchange code for tokens
    token_res = requests.post(
        "https://api.canva.com/rest/v1/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": client_secret,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )

    if token_res.status_code != 200:
        print(f"\n✗ Token exchange failed: {token_res.status_code}")
        print(f"  {token_res.text[:500]}")
        sys.exit(1)

    tokens = token_res.json()
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 0)

    print(f"\n" + "=" * 60)
    print(f"  ✓ Authorization successful!")
    print(f"=" * 60)
    print(f"\n--- Save these as GitHub Secrets ---\n")
    print(f"  CANVA_ACCESS_TOKEN  = {access_token}")
    print(f"  CANVA_REFRESH_TOKEN = {refresh_token}")
    print(f"  CANVA_CLIENT_ID     = {CLIENT_ID}")
    print(f"\nAccess token expires in {expires_in // 3600} hours.")
    print(f"The pipeline will use the refresh token to get new ones automatically.")


if __name__ == "__main__":
    main()
