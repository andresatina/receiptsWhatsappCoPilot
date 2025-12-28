"""
Database Handler for Companies and Users
Manages companies, users, categories, cost centers, and learned patterns
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager


class DatabaseHandler:
    """Handles all PostgreSQL operations for companies and users"""
    
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL not found in environment variables")
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = psycopg2.connect(self.database_url)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    # ============ USER MANAGEMENT ============
    
    def get_or_create_user(self, phone_number, name=None):
        """
        Get existing user or create new one in Test Company
        Returns user with company information
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Try to get existing user with company info
            cursor.execute(
                """SELECT u.*, c.business_name, c.default_currency, c.default_language,
                          c.google_sheet_id, c.google_drive_folder_id, c.cost_center_label,
                          c.requires_cost_center
                   FROM users u
                   JOIN companies c ON u.company_id = c.id
                   WHERE u.phone_number = %s AND u.is_active = TRUE""",
                (phone_number,)
            )
            user = cursor.fetchone()
            
            if not user:
                # Create new user in Test Company (id=1)
                cursor.execute(
                    """INSERT INTO users (phone_number, name, company_id) 
                       VALUES (%s, %s, 1) 
                       RETURNING id, phone_number, name, company_id, is_active""",
                    (phone_number, name)
                )
                new_user = cursor.fetchone()
                
                # Get company info
                cursor.execute(
                    """SELECT u.*, c.business_name, c.default_currency, c.default_language,
                              c.google_sheet_id, c.google_drive_folder_id, c.cost_center_label,
                              c.requires_cost_center
                       FROM users u
                       JOIN companies c ON u.company_id = c.id
                       WHERE u.id = %s""",
                    (new_user['id'],)
                )
                user = cursor.fetchone()
            
            return dict(user)
    
    # ============ COMPANY MANAGEMENT ============
    
    def create_company(self, business_name, default_currency='USD', default_language='en', 
                      google_sheet_id=None, google_drive_folder_id=None):
        """Create a new company"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """INSERT INTO companies 
                   (business_name, default_currency, default_language, google_sheet_id, google_drive_folder_id)
                   VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                (business_name, default_currency, default_language, google_sheet_id, google_drive_folder_id)
            )
            return dict(cursor.fetchone())
    
    def update_user_company(self, phone_number, company_id):
        """Move user to a different company"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET company_id = %s WHERE phone_number = %s",
                (company_id, phone_number)
            )
    
    def get_company(self, company_id):
        """Get company details"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM companies WHERE id = %s", (company_id,))
            return dict(cursor.fetchone())
    
    # ============ CATEGORIES (Chart of Accounts) ============
    
    def get_categories(self, company_id):
        """Get all categories for a company"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM categories WHERE company_id = %s ORDER BY name",
                (company_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def add_category(self, company_id, category_name):
        """Add new category if it doesn't exist, return category id"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Try to insert, ignore if duplicate
            cursor.execute(
                """INSERT INTO categories (company_id, name) 
                   VALUES (%s, %s) 
                   ON CONFLICT (company_id, name) DO NOTHING
                   RETURNING id""",
                (company_id, category_name)
            )
            result = cursor.fetchone()
            
            if result:
                return result['id']
            
            # If no result, category already exists - fetch it
            cursor.execute(
                "SELECT id FROM categories WHERE company_id = %s AND name = %s",
                (company_id, category_name)
            )
            return cursor.fetchone()['id']
    
    def delete_category(self, company_id, category_name):
        """Delete a category by name. Returns True if deleted, False if not found."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM categories WHERE company_id = %s AND LOWER(name) = LOWER(%s)",
                (company_id, category_name)
            )
            return cursor.rowcount > 0
    
    # ============ COST CENTERS ============
    
    def get_cost_centers(self, company_id):
        """Get all cost centers for a company"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM cost_centers WHERE company_id = %s ORDER BY name",
                (company_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def add_cost_center(self, company_id, cost_center_name):
        """Add new cost center if it doesn't exist, return cost center id"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute(
                """INSERT INTO cost_centers (company_id, name) 
                   VALUES (%s, %s) 
                   ON CONFLICT (company_id, name) DO NOTHING
                   RETURNING id""",
                (company_id, cost_center_name)
            )
            result = cursor.fetchone()
            
            if result:
                return result['id']
            
            # If no result, cost center already exists - fetch it
            cursor.execute(
                "SELECT id FROM cost_centers WHERE company_id = %s AND name = %s",
                (company_id, cost_center_name)
            )
            return cursor.fetchone()['id']
    
    def delete_cost_center(self, company_id, cost_center_name):
        """Delete a cost center by name. Returns True if deleted, False if not found."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM cost_centers WHERE company_id = %s AND LOWER(name) = LOWER(%s)",
                (company_id, cost_center_name)
            )
            return cursor.rowcount > 0
    
    # ============ DUPLICATE DETECTION ============
    
    def is_duplicate(self, company_id, image_hash):
        """Check if receipt with same hash already exists for this company"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) FROM receipt_events 
                   WHERE company_id = %s 
                   AND receipt_hash = %s 
                   AND event_type = 'receipt_saved'""",
                (company_id, image_hash)
            )
            count = cursor.fetchone()[0]
            return count > 0
    
    # ============ PATTERNS (Learning) ============
    
    def find_matching_patterns(self, company_id, merchant, items_keywords):
        """
        Find patterns that match merchant and have similar items
        Returns patterns sorted by similarity
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Find patterns for this merchant
            # Match on merchant first, then calculate similarity
            cursor.execute(
                """SELECT p.*, c.name as category_name, cc.name as cost_center_name,
                          array_length(p.items_keywords, 1) as keyword_count
                   FROM patterns p
                   JOIN categories c ON p.category_id = c.id
                   JOIN cost_centers cc ON p.cost_center_id = cc.id
                   WHERE p.company_id = %s 
                   AND LOWER(p.merchant) = LOWER(%s)
                   ORDER BY p.frequency DESC, p.last_used_at DESC
                   LIMIT 10""",
                (company_id, merchant)
            )
            
            patterns = [dict(row) for row in cursor.fetchall()]
            
            # Calculate similarity for each pattern
            for pattern in patterns:
                pattern_keywords = set(pattern['items_keywords']) if pattern['items_keywords'] else set()
                input_keywords = set(items_keywords) if items_keywords else set()
                
                # If both have items, calculate Jaccard similarity
                if pattern_keywords and input_keywords:
                    intersection = len(pattern_keywords & input_keywords)
                    union = len(pattern_keywords | input_keywords)
                    items_similarity = (intersection / union * 100) if union > 0 else 0
                    # Merchant match + items match = higher confidence
                    pattern['similarity'] = items_similarity
                elif not pattern_keywords and not input_keywords:
                    # Both empty items - merchant-only match
                    pattern['similarity'] = 100  # Perfect merchant match
                else:
                    # One has items, other doesn't - partial match
                    pattern['similarity'] = 50  # Merchant match only
            
            # Sort by similarity
            patterns.sort(key=lambda x: x['similarity'], reverse=True)
            
            return patterns
    
    def save_pattern(self, company_id, merchant, items_keywords, category_name, cost_center_name):
        """
        Save or update a learned pattern
        Creates category and cost_center if they don't exist
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get or create category and cost center
            category_id = self.add_category(company_id, category_name)
            cost_center_id = self.add_cost_center(company_id, cost_center_name)
            
            # Insert or update pattern
            cursor.execute(
                """INSERT INTO patterns 
                   (company_id, merchant, items_keywords, category_id, cost_center_id, frequency, last_used_at)
                   VALUES (%s, %s, %s, %s, %s, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT (company_id, merchant, category_id, cost_center_id) 
                   DO UPDATE SET 
                       frequency = patterns.frequency + 1,
                       last_used_at = CURRENT_TIMESTAMP,
                       items_keywords = EXCLUDED.items_keywords
                   RETURNING id, frequency""",
                (company_id, merchant.lower(), items_keywords, category_id, cost_center_id)
            )
            
            result = cursor.fetchone()
            print(f"💾 Pattern saved: {merchant} → {category_name}/{cost_center_name} (used {result[1]} times)")
            
            return result[0]
    
    # ============ BUSINESS RULES (Optional) ============
    
    def add_business_rule(self, company_id, rule_text):
        """Add a business rule for the company"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO business_rules (company_id, rule_text) VALUES (%s, %s)",
                (company_id, rule_text)
            )
    
    def get_business_rules(self, company_id):
        """Get all business rules for a company"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM business_rules WHERE company_id = %s ORDER BY created_at",
                (company_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # ============ MONTHLY TOTALS ============
    
    def get_monthly_total_by_cost_center(self, company_id, cost_center_name):
        """Get total amount for a specific cost center in current month"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COALESCE(SUM(amount), 0) as total
                   FROM receipt_events
                   WHERE company_id = %s 
                   AND cost_center = %s
                   AND event_type = 'receipt_saved'
                   AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)""",
                (company_id, cost_center_name)
            )
            result = cursor.fetchone()
            return float(result[0]) if result else 0.0
    
    def get_all_monthly_totals(self, company_id):
        """Get totals for all cost centers in current month"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """SELECT cost_center, SUM(amount) as total
                   FROM receipt_events
                   WHERE company_id = %s 
                   AND event_type = 'receipt_saved'
                   AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
                   GROUP BY cost_center
                   ORDER BY cost_center""",
                (company_id,)
            )
            return [dict(row) for row in cursor.fetchall()]