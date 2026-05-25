import base64
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

GITHUB_TOKEN     = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME  = "kyanng"
GITHUB_REPO      = "AIRES-ENVIRONMENT"
GITHUB_FOLDER    = "uploaded_images"   # folder inside the repo where images land
GITHUB_BRANCH    = "main"

# Local folder (next to the repo root) where a copy is also kept
LOCAL_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", "uploaded_images")
os.makedirs(LOCAL_UPLOAD_FOLDER, exist_ok=True)

REQUEST_TIMEOUT = 20

# =============================================================================
# Helpers
# =============================================================================

def validate_config() -> None:
    if not GITHUB_TOKEN:
        raise RuntimeError("Missing GITHUB_TOKEN in your .env file.")


def upload_image(image_path: str) -> str:
    """
    1. Reads the image from `image_path`.
    2. Saves a local copy to uploaded_images/.
    3. Uploads it to the GitHub repo.
    4. Returns the public raw URL.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"File not found: {image_path}")

    filename = os.path.basename(image_path)

    # --- Step 1: save local copy ---
    local_dest = os.path.join(LOCAL_UPLOAD_FOLDER, filename)
    with open(image_path, "rb") as src:
        image_bytes = src.read()

    with open(local_dest, "wb") as dst:
        dst.write(image_bytes)

    print(f"[1/3] Local copy saved  →  {os.path.abspath(local_dest)}")

    # --- Step 2: upload to GitHub ---
    repo_path   = f"{GITHUB_FOLDER}/{filename}"
    api_url     = (
        f"https://api.github.com/repos/"
        f"{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{repo_path}"
    )
    encoded     = base64.b64encode(image_bytes).decode("utf-8")
    headers     = {
        "Authorization":       f"Bearer {GITHUB_TOKEN}",
        "Accept":              "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Check if the file already exists (so we can pass its SHA for an update)
    check = requests.get(api_url, headers=headers, timeout=REQUEST_TIMEOUT)
    sha   = None
    if check.status_code == 200:
        sha = check.json().get("sha")
    elif check.status_code != 404:
        raise RuntimeError(f"GitHub check failed ({check.status_code}): {check.text}")

    payload = {
        "message": f"Upload {filename}",
        "content": encoded,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    print(f"[2/3] Uploading to GitHub repo ({GITHUB_REPO}/{GITHUB_FOLDER})...")

    upload = requests.put(api_url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    if upload.status_code not in (200, 201):
        raise RuntimeError(f"GitHub upload failed ({upload.status_code}): {upload.text}")

    # --- Step 3: build and return the public URL ---
    public_url = (
        f"https://raw.githubusercontent.com/"
        f"{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{repo_path}"
    )
    return public_url


# =============================================================================
# Entry Point  —  python upload_image_to_github.py "path/to/photo.jpg"
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python upload_image_to_github.py \"path/to/your/photo.jpg\"")
        sys.exit(1)

    image_path = sys.argv[1]

    try:
        validate_config()
        url = upload_image(image_path)
        print(f"[3/3] Upload complete!")
        print(f"\n Image URL:\n  {url}\n")
    except Exception as exc:
        print(f"\n Error: {exc}")
        sys.exit(1)
