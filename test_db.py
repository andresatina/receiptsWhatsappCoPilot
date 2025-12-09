"""
Test script for database_handler.py
Run: python test_db.py
"""

from dotenv import load_dotenv
load_dotenv()

from database_handler import DatabaseHandler

# Initialize
db = DatabaseHandler()

# Test phone number
test_phone = "13473042500"

print("=" * 50)
print("Testing Database Handler")
print("=" * 50)

# 1. Create/get client
print("\n1. Creating client...")
client = db.get_or_create_client(test_phone, "Test Property Management")
print(f"✓ Client: {client['phone_number']} - {client['business_name']}")

# 2. Add categories
print("\n2. Adding categories...")
cat1 = db.add_category(test_phone, "Maintenance")
cat2 = db.add_category(test_phone, "Office Supplies")
cat3 = db.add_category(test_phone, "Meals")
print(f"✓ Added categories: {cat1}, {cat2}, {cat3}")

# 3. Get all categories
print("\n3. Getting all categories...")
categories = db.get_categories(test_phone)
print(f"✓ Categories: {[c['name'] for c in categories]}")

# 4. Add cost centers
print("\n4. Adding cost centers...")
cc1 = db.add_cost_center(test_phone, "Building A")
cc2 = db.add_cost_center(test_phone, "Office")
print(f"✓ Added cost centers: {cc1}, {cc2}")

# 5. Get all cost centers
print("\n5. Getting all cost centers...")
cost_centers = db.get_cost_centers(test_phone)
print(f"✓ Cost centers: {[cc['name'] for cc in cost_centers]}")

# 6. Save a pattern
print("\n6. Saving pattern...")
pattern_id = db.save_pattern(
    client_id=test_phone,
    merchant="Home Depot",
    items_keywords=["paint", "brush", "roller"],
    category_name="Maintenance",
    cost_center_name="Building A"
)
print(f"✓ Pattern saved with ID: {pattern_id}")

# 7. Find matching patterns
print("\n7. Finding matching patterns...")
matches = db.find_matching_patterns(
    client_id=test_phone,
    merchant="Home Depot",
    items_keywords=["paint", "primer", "brush"]  # Similar items
)
if matches:
    best = matches[0]
    print(f"✓ Best match: {best['category_name']}/{best['cost_center_name']}")
    print(f"  Similarity: {best['similarity']:.1f}%")
    print(f"  Used {best['frequency']} times")
else:
    print("✗ No matches found")

print("\n" + "=" * 50)
print("All tests passed! ✓")
print("=" * 50)
