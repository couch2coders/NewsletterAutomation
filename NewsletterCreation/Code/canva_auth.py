#!/usr/bin/env python3
"""
One-time Canva OAuth token generator.
Run this locally to authorize and get an access token + refresh token.

Usage:
    python canva_auth.py <CLIENT_SECRET>

It will:
1. Open your browser to Canva's authorization page
2. Start a local server to catch the callback
3. Exchange the code for access + refresh tokens
4. Print the tokens for you to save as GitHub secrets
"""
import sys
import hashlib
import base64
import secrets
import webbrowser
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
import requests

CLIENT_ID = "OC-AZ10LQbljNIw"
REDIRECT_URI = "http://127.0.0.1:8000/callback"
SCOPES = "design:content:read design:content:write asset:write"

# PKCE: generate code verifier and challenge
code_verifier = secrets.token_urlsafe(64)[:128]
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        query = parse_qs(urlparse(self.path).query)
        auth_code = query.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        if auth_code:
            self.wfile.write(b"<h1>Success! You can close this tab.</h1><p>Return to your terminal.</p>")
        else:
            error = query.get("error", ["unknown"])[0]
            self.wfile.write(f"<h1>Error: {error}</h1>".encode())

    def log_message(self, format, *args):
        pass  # Suppress log output


def main():
    if len(sys.argv) < 2:
        print("Usage: python canva_auth.py <CLIENT_SECRET>")
        print("  Get your client secret from: https://www.canva.com/developers/")
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
    print(f"\n1. Opening your browser to authorize...")
    print(f"   If it doesn't open, visit this URL:\n")
    print(f"   {auth_url}\n")

    webbrowser.open(auth_url)

    # Step 2: Start local server to catch callback
    print("2. Waiting for Canva to redirect back...")
    server = HTTPServer(("127.0.0.1", 8000), CallbackHandler)
    server.handle_request()  # Handle one request then stop

    if not auth_code:
        print("\n✗ No authorization code received. Try again.")
        sys.exit(1)

    print(f"\n3. Got authorization code. Exchanging for tokens...")

    # Step 3: Exchange code for tokens
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
    print(f"\nAccess Token (expires in {expires_in}s):")
    print(f"  {access_token[:20]}...{access_token[-10:]}")
    print(f"\nRefresh Token (save this — used to get new access tokens):")
    print(f"  {refresh_token[:20]}...{refresh_token[-10:]}")
    print(f"\n--- Save these as GitHub Secrets ---")
    print(f"  CANVA_ACCESS_TOKEN  = {access_token}")
    print(f"  CANVA_REFRESH_TOKEN = {refresh_token}")
    print(f"  CANVA_CLIENT_ID     = {CLIENT_ID}")
    print(f"  CANVA_CLIENT_SECRET = (already saved)")
    print(f"\nThe access token expires in {expires_in // 3600} hours.")
    print(f"The pipeline will use the refresh token to get new access tokens automatically.")


if __name__ == "__main__":
    main()
