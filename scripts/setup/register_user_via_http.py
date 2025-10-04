#!/usr/bin/env python3
import sys
import json
import argparse
import requests


def register(email: str, password: str) -> int:
    url = "https://excel-ai-agent-backends-765930447632.asia-southeast1.run.app/api/v1/auth/register"
    body = {"email": email, "password": password}
    resp = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(body), timeout=20)
    print(resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text)
    return resp.status_code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    code = register(args.email, args.password)
    sys.exit(0 if 200 <= code < 300 else 1)


if __name__ == "__main__":
    main()



