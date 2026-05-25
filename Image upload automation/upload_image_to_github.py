import base64
import os

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

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ECOQPAY_API_KEY = os.getenv("ECOQPAY_API_KEY")

GITHUB_USERNAME = "kyanng"
GITHUB_REPO = "AIRES-ENVIRONMENT"
GITHUB_UPLOAD_FOLDER = "images"
GITHUB_BRANCH = "main"

ECOQPAY_API_URL = "https://ecoqcode.sg/api/v1/generator/generate/ecoqpay"
#ECOQPAY_ENCRYPTION_KEY = "123456"

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
    """
    Generate a random 6-digit encryption key.
    First digit is 1-9 to avoid leading zero.
    """
    return str(secrets.randbelow(900000) + 100000)

def validate_config() -> None:
    if not GITHUB_TOKEN:
        raise RuntimeError("Missing GITHUB_TOKEN environment variable.")

    if not ECOQPAY_API_KEY:
        raise RuntimeError("Missing ECOQPAY_API_KEY environment variable.")


def upload_image_to_github(image_file, filename: str) -> str:
    safe_filename = secure_filename(filename)

    if not safe_filename:
        raise ValueError("Invalid filename.")

    repo_path = f"{GITHUB_UPLOAD_FOLDER}/{safe_filename}"

    api_url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{repo_path}"
    )

    encoded_content = base64.b64encode(image_file.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    check_response = requests.get(
        api_url,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )

    file_sha = None

    if check_response.status_code == 200:
        file_sha = check_response.json().get("sha")
    elif check_response.status_code != 404:
        raise RuntimeError(
            f"GitHub check error {check_response.status_code}: "
            f"{check_response.text}"
        )

    payload = {
        "message": f"Upload {safe_filename}",
        "content": encoded_content,
        "branch": GITHUB_BRANCH,
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
        f"{GITHUB_USERNAME}/{GITHUB_REPO}/"
        f"{GITHUB_BRANCH}/{repo_path}"
    )


def generate_ecoqpay_qr_base64(github_url: str) -> str:
    headers = {
        "API-KEY": ECOQPAY_API_KEY,
        "Content-Type": "application/json",
    }

    encryption_key = generate_encryption_key()

    payload = {
        "link1": github_url,
        "link2": "",
        "link3": "",
        "encryption-key": encryption_key,
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
            validate_config()

            image = request.files.get("image")

            if not image or image.filename == "":
                raise ValueError("No image uploaded.")

            github_url = upload_image_to_github(image, image.filename)
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
# =============================================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9999, debug=True)