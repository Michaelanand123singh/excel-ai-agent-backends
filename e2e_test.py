import os
import sys
import time
import csv
import io
import json
from typing import Optional

import requests


BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API = f"{BASE_URL}/api/v1"


def log(title: str, data=None):
    print(f"\n=== {title} ===")
    if data is not None:
        try:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            print(data)


def login(username: str, password: str) -> Optional[str]:
    url = f"{API}/auth/login"
    r = requests.post(url, json={"username": username, "password": password})
    log("Login response", {"status": r.status_code, "body": safe_json(r)})
    if r.status_code == 200:
        token = r.json().get("access_token")
        return token
    return None


def safe_json(r: requests.Response):
    try:
        return r.json()
    except Exception:
        return r.text


def make_sample_csv() -> bytes:
    headers = [
        "Potential Buyer 1",
        "Item_Description",
        "Quantity",
        "UQC",
        "Unit_Price",
        "Potential Buyer 2",
        "Potential Buyer 1 Contact Details",
        "Potential Buyer 1 email id",
    ]
    rows = [
        [
            "SUPRETRON ELECTRONICS PRIVATE LIMITED",
            "EXTERNAL SOLID STATE DRIVE 2 1/2(STKGC2000400)|SPEED:2000|BRAND:SEAGATE",
            160,
            "NOS",
            17000.75,
            "SEAGATE SINGAPORE INTERNATIONAL",
            "918903154689",
            "mehari@supretronindia.com",
        ],
        [
            "RAN Smart Technologies",
            "INTEGRATED CIRCUITS - CX20773-122",
            4000,
            "NOS",
            127.82,
            "EDOM TECHNOLOGY CO., LTD",
            "N/A",
            "sales@ran-smart.com",
        ],
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def upload_file(token: Optional[str], content: bytes, filename: str = "sample.csv") -> dict:
    url = f"{API}/upload"
    files = {"file": (filename, content, "text/csv")}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.post(url, files=files, headers=headers)
    log("Upload response", {"status": r.status_code, "body": safe_json(r)})
    r.raise_for_status()
    return r.json()


def get_file_status(token: Optional[str], file_id: int) -> dict:
    url = f"{API}/upload/{file_id}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(url, headers=headers)
    return r.json() if r.status_code == 200 else {"status": "unknown", "detail": safe_json(r)}


def wait_until_processed(token: Optional[str], file_id: int, timeout_s: int = 90) -> dict:
    start = time.time()
    while True:
        info = get_file_status(token, file_id)
        status = info.get("status")
        log("File status", info)
        if status == "processed":
            return info
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Processing timeout for file {file_id}")
        time.sleep(3)


def part_search(token: Optional[str], file_id: int, query: str) -> dict:
    url = f"{API}/query/search-part"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.post(url, json={"file_id": file_id, "part_number": query}, headers=headers)
    log("Part search response", {"status": r.status_code, "body": safe_json(r)})
    r.raise_for_status()
    return r.json()


def ask_question(token: Optional[str], file_id: int, question: str) -> dict:
    url = f"{API}/query"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.post(url, json={"file_id": file_id, "question": question}, headers=headers)
    log("NL query response", {"status": r.status_code, "body": safe_json(r)})
    r.raise_for_status()
    return r.json()


def list_files(token: Optional[str]) -> list:
    url = f"{API}/upload/"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.get(url, headers=headers)
    log("List files", {"status": r.status_code, "body": safe_json(r)})
    r.raise_for_status()
    return r.json()


def delete_file(token: Optional[str], file_id: int) -> dict:
    url = f"{API}/upload/{file_id}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = requests.delete(url, headers=headers)
    log("Delete file", {"status": r.status_code, "body": safe_json(r)})
    r.raise_for_status()
    return r.json()


def main():
    username = os.getenv("TEST_USERNAME") or "admin"
    password = os.getenv("TEST_PASSWORD") or "admin"
    keep_dataset = os.getenv("KEEP_DATASET", "0") == "1"

    log("Config", {"API": API, "username": username, "keep_dataset": keep_dataset})

    token = login(username, password)
    if not token:
        print("Login failed (401). Ensure credentials are correct.")
        sys.exit(1)

    content = make_sample_csv()
    upload = upload_file(token, content)
    file_id = upload.get("id") or upload.get("file_id")
    if not file_id:
        print("Upload did not return file id", upload)
        sys.exit(1)

    wait_until_processed(token, int(file_id))

    # Part search on description token
    part_search(token, int(file_id), "CX20773-122")

    # NL query: top quantity
    ask_question(token, int(file_id), "top available quantity product")

    list_files(token)

    if not keep_dataset:
        delete_file(token, int(file_id))

    print("\nAll tests executed successfully.")


if __name__ == "__main__":
    main()

