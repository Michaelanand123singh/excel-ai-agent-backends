#!/usr/bin/env python3
"""
CORS Test Script
Tests the CORS functionality of the backend API
"""

import requests
import json
from typing import Dict, Any


def test_cors_endpoint(base_url: str) -> Dict[str, Any]:
    """Test CORS configuration endpoint"""
    try:
        response = requests.get(f"{base_url}/cors-test")
        return {
            "status": "success",
            "status_code": response.status_code,
            "data": response.json(),
            "headers": dict(response.headers)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def test_cors_preflight(base_url: str, origin: str) -> Dict[str, Any]:
    """Test CORS preflight request"""
    try:
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Authorization"
        }
        response = requests.options(f"{base_url}/api/v1/auth/login", headers=headers)
        return {
            "status": "success",
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "cors_headers": {
                "access_control_allow_origin": response.headers.get("Access-Control-Allow-Origin"),
                "access_control_allow_methods": response.headers.get("Access-Control-Allow-Methods"),
                "access_control_allow_headers": response.headers.get("Access-Control-Allow-Headers"),
                "access_control_allow_credentials": response.headers.get("Access-Control-Allow-Credentials"),
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def test_middleware_stack(base_url: str) -> Dict[str, Any]:
    """Test middleware stack endpoint"""
    try:
        response = requests.get(f"{base_url}/middleware-test")
        return {
            "status": "success",
            "status_code": response.status_code,
            "data": response.json(),
            "timing_header": response.headers.get("X-Process-Time-ms")
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def main():
    """Run all CORS tests"""
    base_url = "https://excel-ai-agent-backends-765930447632.asia-southeast1.run.app"
    frontend_origin = "https://excel-ai-agent-frontend-765930447632.asia-southeast1.run.app"
    
    print("🧪 Testing CORS Configuration...")
    print("=" * 50)
    
    # Test 1: CORS Configuration
    print("\n1. Testing CORS Configuration Endpoint:")
    cors_test = test_cors_endpoint(base_url)
    print(json.dumps(cors_test, indent=2))
    
    # Test 2: CORS Preflight
    print(f"\n2. Testing CORS Preflight from {frontend_origin}:")
    preflight_test = test_cors_preflight(base_url, frontend_origin)
    print(json.dumps(preflight_test, indent=2))
    
    # Test 3: Middleware Stack
    print("\n3. Testing Middleware Stack:")
    middleware_test = test_middleware_stack(base_url)
    print(json.dumps(middleware_test, indent=2))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    print(f"✅ CORS Config: {'PASS' if cors_test['status'] == 'success' else 'FAIL'}")
    print(f"✅ CORS Preflight: {'PASS' if preflight_test['status'] == 'success' and preflight_test.get('status_code') == 200 else 'FAIL'}")
    print(f"✅ Middleware Stack: {'PASS' if middleware_test['status'] == 'success' else 'FAIL'}")


if __name__ == "__main__":
    main()
