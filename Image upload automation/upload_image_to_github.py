import base64
import os
import sys

import requests
import secrets
from dotenv import load_dotenv
from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# =============================================================================
# Configuration
# =============================================================================

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN")
ECOQPAY_API_KEY = os.getenv("ECOQPAY_API_KEY")

GITHUB_USERNAME      = "kyanng"
GITHUB_REPO          = "AIRES-ENVIRONMENT"
GITHUB_UPLOAD_FOLDER = "uploaded_images"
GITHUB_BRANCH        = "main"

# Local copy folder saved alongside the repo root
LOCAL_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "..", "uploaded_images")
os.makedirs(LOCAL_UPLOAD_FOLDER, exist_ok=True)

ECOQPAY_API_URL = "https://ecoqcode.sg/api/v1/generator/generate/ecoqpay"

REQUEST_TIMEOUT = 20


# =============================================================================
# HTML Template
# =============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>EcoQPay Generator</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f5f5f5;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }

        .card {
            width: 500px;
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            text-align: center;
        }

        input[type=file] {
            width: 100%;
            margin-bottom: 15px;
        }

        button {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: #111827;
            color: white;
            cursor: pointer;
        }

        button:hover {
            background: black;
        }

        img {
            margin-top: 20px;
            max-width: 100%;
        }

        .error {
            margin-top: 15px;
            color: red;
        }
    </style>
</head>
<body>
<div class="card">
    <h2>EcoQPay QR Generator</h2>

    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="image" accept="image/*" required>
        <button type="submit">Generate QR</button>
    </form>

    {% if ecoqpay_image_base64 %}
        <h3>Generated EcoQPay</h3>
        <img src="data:image/png;base64,{{ ecoqpay_image_base64 }}">
    {% endif %}

    {% if error %}
        <div class="error">{{ error }}</div>
    {% endif %}
</div>
</body>
</html>
"""


# =============================================================================
# Helpers
# =============================================================================

def generate_encryption_key() -> str:
    """Generate a random 6-digit encryption key (no leading zero)."""
    return str(secrets.randbelow(900000) + 100000)


def validate_config(require_ecoqpay: bool = True) -> None:
    """
    Validate required environment variables.

    Parameters
    ----------
    require_ecoqpay:
        Set to False when running in CLI-only mode (no QR generation needed).
    """
    if not GITHUB_TOKEN:
        raise RuntimeError("Missing GITHUB_TOKEN environment variable.")
    if require_ecoqpay and not ECOQPAY_API_KEY:
        raise RuntimeError("Missing ECOQPAY_API_KEY environment variable.")


def _save_local_copy(image_bytes: bytes, filename: str) -> str:
    """
    Save *image_bytes* to the local uploaded_images folder.

    Returns the absolute path of the saved file.
    """
    local_dest = os.path.join(LOCAL_UPLOAD_FOLDER, filename)
    with open(local_dest, "wb") as fh:
        fh.write(image_bytes)
    return os.path.abspath(local_dest)


def _upload_bytes_to_github(image_bytes: bytes, safe_filename: str) -> str:
    """
    Core GitHub upload logic shared by both the web route and the CLI.

    Uploads *image_bytes* to the configured repo and returns the public
    raw.githubusercontent.com URL.
    """
    repo_path = f"{GITHUB_UPLOAD_FOLDER}/{safe_filename}"
    api_url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{repo_path}"
    )

    encoded_content = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization":        f"Bearer {GITHUB_TOKEN}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Check whether the file already exists so we can supply its SHA
    check_response = requests.get(api_url, headers=headers, timeout=REQUEST_TIMEOUT)

    file_sha = None
    if check_response.status_code == 200:
        file_sha = check_response.json().get("sha")
    elif check_response.status_code != 404:
        raise RuntimeError(
            f"GitHub check error {check_response.status_code}: "
            f"{check_response.text}"
        )

    payload: dict = {
        "message": f"Upload {safe_filename}",
        "content": encoded_content,
        "branch":  GITHUB_BRANCH,
    }
    if file_sha:
        payload["sha"] = file_sha

    upload_response = requests.put(
        api_url,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )

    if upload_response.status_code not in (200, 201):
        raise RuntimeError(
            f"GitHub upload error {upload_response.status_code}: "
            f"{upload_response.text}"
        )

    return (
        f"https://raw.githubusercontent.com/"
        f"{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/{repo_path}"
    )


def upload_image_to_github(image_file, filename: str) -> str:
    """
    Web route helper — accepts a Werkzeug FileStorage object.

    1. Validates and sanitises the filename.
    2. Saves a local copy to LOCAL_UPLOAD_FOLDER.
    3. Uploads to GitHub.
    4. Returns the public raw URL.
    """
    safe_filename = secure_filename(filename)
    if not safe_filename:
        raise ValueError("Invalid filename.")

    image_bytes = image_file.read()

    local_path = _save_local_copy(image_bytes, safe_filename)
    print(f"Local copy saved  →  {local_path}")

    return _upload_bytes_to_github(image_bytes, safe_filename)


def upload_image(image_path: str) -> str:
    """
    CLI helper — accepts a local file path string.

    1. Reads the image from disk.
    2. Saves a local copy to LOCAL_UPLOAD_FOLDER.
    3. Uploads to GitHub.
    4. Returns the public raw URL.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"File not found: {image_path}")

    filename      = os.path.basename(image_path)
    safe_filename = secure_filename(filename)

    with open(image_path, "rb") as fh:
        image_bytes = fh.read()

    local_path = _save_local_copy(image_bytes, safe_filename)
    print(f"[1/3] Local copy saved  →  {local_path}")

    print(f"[2/3] Uploading to GitHub repo ({GITHUB_REPO}/{GITHUB_UPLOAD_FOLDER})…")
    url = _upload_bytes_to_github(image_bytes, safe_filename)
    print("[3/3] Upload complete!")

    return url


def generate_ecoqpay_qr_base64(github_url: str) -> str:
    """Call the EcoQPay API and return the QR image as a base64 string."""
    headers = {
        "API-KEY":      ECOQPAY_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "link1":           github_url,
        "link2":           "",
        "link3":           "",
        "encryption-key":  generate_encryption_key(),
    }

    response = requests.post(
        ECOQPAY_API_URL,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"EcoQPay error {response.status_code}: {response.text}"
        )

    return base64.b64encode(response.content).decode("utf-8")


# =============================================================================
# Routes
# =============================================================================

@app.route("/", methods=["GET", "POST"])
def index():
    ecoqpay_image_base64 = None
    error = None

    if request.method == "POST":
        try:
            validate_config(require_ecoqpay=True)

            image = request.files.get("image")
            if not image or image.filename == "":
                raise ValueError("No image uploaded.")

            github_url           = upload_image_to_github(image, image.filename)
            ecoqpay_image_base64 = generate_ecoqpay_qr_base64(github_url)

        except Exception as exc:
            error = str(exc)

    return render_template_string(
        HTML_TEMPLATE,
        ecoqpay_image_base64=ecoqpay_image_base64,
        error=error,
    )


# =============================================================================
# Entry Point
#
#   Flask server  →  python upload_image_to_github.py
#   CLI upload    →  python upload_image_to_github.py "path/to/photo.jpg"
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) == 2:
        # ── CLI mode: upload a single image and print the URL ──────────────
        cli_image_path = sys.argv[1]
        try:
            validate_config(require_ecoqpay=False)
            url = upload_image(cli_image_path)
            print(f"\n  Image URL:\n  {url}\n")
        except Exception as exc:
            print(f"\n  Error: {exc}")
            sys.exit(1)

    elif len(sys.argv) == 1:
        # ── Web mode: start the Flask development server ───────────────────
        app.run(host="0.0.0.0", port=9999, debug=True)

    else:
        print("Usage:")
        print("  Flask server  →  python upload_image_to_github.py")
        print("  CLI upload    →  python upload_image_to_github.py \"path/to/photo.jpg\"")
        sys.exit(1)
