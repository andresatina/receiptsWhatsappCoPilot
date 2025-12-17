#!/usr/bin/env python3
"""
Quick Smoke Tests - Manual verification of critical functionality
Run this after deployment to verify everything works

Usage:
    python smoke_test.py
"""

import os
import sys
import requests
from datetime import datetime


def test_health_endpoint():
    """Test that the Flask app is running"""
    print("\n🔍 Testing health endpoint...")
    
    base_url = os.getenv('APP_URL', 'http://localhost:5000')
    
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health endpoint responding")
            return True
        else:
            print(f"❌ Health endpoint returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health endpoint failed: {str(e)}")
        return False


def test_database_connection():
    """Test database connectivity"""
    print("\n🔍 Testing database connection...")
    
    try:
        import psycopg2
        db_url = os.getenv('DATABASE_URL')
        
        if not db_url:
            print("❌ DATABASE_URL not set")
            return False
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Test basic query
        cursor.execute("SELECT COUNT(*) FROM companies")
        count = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"✅ Database connected ({count} companies)")
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        return False


def test_claude_api():
    """Test Claude API connectivity"""
    print("\n🔍 Testing Claude API...")
    
    try:
        import anthropic
        
        api_key = os.getenv('CLAUDE_API_KEY')
        if not api_key:
            print("❌ CLAUDE_API_KEY not set")
            return False
        
        client = anthropic.Anthropic(api_key=api_key)
        
        # Simple test message
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
        
        if response.content:
            print("✅ Claude API responding")
            return True
        else:
            print("❌ Claude API returned empty response")
            return False
            
    except Exception as e:
        print(f"❌ Claude API failed: {str(e)}")
        return False


def test_google_credentials():
    """Test Google Sheets/Drive credentials"""
    print("\n🔍 Testing Google credentials...")
    
    if not os.path.exists('credentials.json'):
        print("❌ credentials.json not found")
        return False
    
    try:
        from google.oauth2 import service_account
        
        credentials = service_account.Credentials.from_service_account_file(
            'credentials.json',
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
        )
        
        if credentials:
            print("✅ Google credentials valid")
            return True
        else:
            print("❌ Google credentials invalid")
            return False
            
    except Exception as e:
        print(f"❌ Google credentials failed: {str(e)}")
        return False


def test_webhook_endpoint():
    """Test webhook endpoint (GET verification)"""
    print("\n🔍 Testing webhook verification...")
    
    base_url = os.getenv('APP_URL', 'http://localhost:5000')
    verify_token = os.getenv('WEBHOOK_VERIFY_TOKEN', 'test-token')
    
    try:
        response = requests.get(
            f"{base_url}/webhook",
            params={
                'hub.verify_token': verify_token,
                'hub.challenge': 'test-challenge'
            },
            timeout=5
        )
        
        if response.status_code == 200 and response.text == 'test-challenge':
            print("✅ Webhook verification working")
            return True
        else:
            print(f"❌ Webhook verification failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Webhook verification failed: {str(e)}")
        return False


def test_cache_clear_endpoint():
    """Test cache clearing endpoints"""
    print("\n🔍 Testing cache management...")
    
    base_url = os.getenv('APP_URL', 'http://localhost:5000')
    
    try:
        response = requests.post(
            f"{base_url}/clear-all-cache",
            timeout=5
        )
        
        if response.status_code == 200:
            print("✅ Cache clearing endpoint working")
            return True
        else:
            print(f"❌ Cache clearing failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Cache clearing failed: {str(e)}")
        return False


def test_environment_variables():
    """Check critical environment variables"""
    print("\n🔍 Checking environment variables...")
    
    required_vars = {
        'DATABASE_URL': 'Database connection string',
        'CLAUDE_API_KEY': 'Claude API access',
        'KAPSO_API_KEY': 'WhatsApp API access',
        'WHATSAPP_PHONE_NUMBER': 'WhatsApp phone number',
        'WEBHOOK_VERIFY_TOKEN': 'Webhook verification',
        'POSTHOG_API_KEY': 'Analytics tracking'
    }
    
    all_set = True
    for var, description in required_vars.items():
        if os.getenv(var):
            print(f"✅ {var} - {description}")
        else:
            print(f"❌ {var} - {description} (MISSING)")
            all_set = False
    
    return all_set


def run_smoke_tests():
    """Run all smoke tests"""
    print("\n" + "="*70)
    print("ATINA - SMOKE TESTS")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("="*70)
    
    tests = [
        ("Environment Variables", test_environment_variables),
        ("Database Connection", test_database_connection),
        ("Claude API", test_claude_api),
        ("Google Credentials", test_google_credentials),
        ("Health Endpoint", test_health_endpoint),
        ("Webhook Verification", test_webhook_endpoint),
        ("Cache Management", test_cache_clear_endpoint)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} crashed: {str(e)}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ ALL SMOKE TESTS PASSED - System operational")
        return 0
    else:
        print(f"\n❌ {total - passed} SMOKE TEST(S) FAILED - Check logs")
        return 1


if __name__ == '__main__':
    sys.exit(run_smoke_tests())
