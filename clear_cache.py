#!/usr/bin/env python3
"""
Clear conversation cache from Redis

Usage:
    python clear_cache.py                    # Clear all users
    python clear_cache.py +1234567890       # Clear specific user
"""

import redis
import sys

# Railway Redis URL
REDIS_URL = "redis://default:CYLcnTxjBMRXQsDzBMhtDdxTdThiFKLb@junction.proxy.rlwy.net:21658"

def clear_all():
    """Clear all user states"""
    r = redis.from_url(REDIS_URL, decode_responses=True)
    keys = r.keys("user_state:*")
    
    if not keys:
        print("✅ No cached conversations found")
        return
    
    print(f"Found {len(keys)} cached conversations:")
    for key in keys:
        phone = key.replace("user_state:", "")
        print(f"  - {phone}")
    
    confirm = input("\n⚠️  Delete ALL? (yes/no): ")
    if confirm.lower() == 'yes':
        for key in keys:
            r.delete(key)
        print(f"\n✅ Cleared {len(keys)} conversations!")
    else:
        print("❌ Cancelled")

def clear_user(phone_number):
    """Clear specific user state"""
    r = redis.from_url(REDIS_URL, decode_responses=True)
    key = f"user_state:{phone_number}"
    
    if r.exists(key):
        r.delete(key)
        print(f"✅ Cleared cache for {phone_number}")
    else:
        print(f"❌ No cache found for {phone_number}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Clear specific user
        phone = sys.argv[1]
        clear_user(phone)
    else:
        # Clear all
        clear_all()
