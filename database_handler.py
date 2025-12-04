"""
Database Handler for Client Knowledge Base
Manages categories, cost centers, and learned patterns
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager


class DatabaseHandler:
    """Handles all PostgreSQL operations for client knowledge base"""
    
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
    
    # ============ CLIENT MANAGEMENT ============
    
    def get_or_create_client(self, phone_number, business_name=None):
        """Get existing client or create new one"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Try to get existing
            cursor.execute(
                "SELECT * FROM clients WHERE phone_number = %s",
                (phone_number,)
            )
            client = cursor.fetchone()
            
            if not client:
                # Create new client
                cursor.execute(
                    """INSERT INTO clients (phone_number, business_name) 
                       VALUES (%s, %s) RETURNING *""",
                    (phone_number, business_name)
                )
                client = cursor.fetchone()
            
            return dict(client)
    
    # ============ CATEGORIES (Chart of Accounts) ============
    
    def get_categories(self, client_id):
        """Get all categories for a client"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM categories WHERE client_id = %s ORDER BY name",
                (client_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def add_category(self, client_id, category_name):
        """Add new category if it doesn't exist, return category id"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Try to insert, ignore if duplicate
            cursor.execute(
                """INSERT INTO categories (client_id, name) 
                   VALUES (%s, %s) 
                   ON CONFLICT (client_id, name) DO NOTHING
                   RETURNING id""",
                (client_id, category_name)
            )
            result = cursor.fetchone()
            
            if result:
                return result['id']
            
            # If no result, category already exists - fetch it
            cursor.execute(
                "SELECT id FROM categories WHERE client_id = %s AND name = %s",
                (client_id, category_name)
            )
            return cursor.fetchone()['id']
    
    # ============ COST CENTERS ============
    
    def get_cost_centers(self, client_id):
        """Get all cost centers for a client"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM cost_centers WHERE client_id = %s ORDER BY name",
                (client_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def add_cost_center(self, client_id, cost_center_name):
        """Add new cost center if it doesn't exist, return cost center id"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute(
                """INSERT INTO cost_centers (client_id, name) 
                   VALUES (%s, %s) 
                   ON CONFLICT (client_id, name) DO NOTHING
                   RETURNING id""",
                (client_id, cost_center_name)
            )
            result = cursor.fetchone()
            
            if result:
                return result['id']
            
            # If no result, cost center already exists - fetch it
            cursor.execute(
                "SELECT id FROM cost_centers WHERE client_id = %s AND name = %s",
                (client_id, cost_center_name)
            )
            return cursor.fetchone()['id']
    
    # ============ PATTERNS (Learning) ============
    
    def find_matching_patterns(self, client_id, merchant, items_keywords):
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
                   WHERE p.client_id = %s 
                   AND LOWER(p.merchant) = LOWER(%s)
                   ORDER BY p.frequency DESC, p.last_used_at DESC
                   LIMIT 10""",
                (client_id, merchant)
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
    
    def save_pattern(self, client_id, merchant, items_keywords, category_name, cost_center_name):
        """
        Save or update a learned pattern
        Creates category and cost_center if they don't exist
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get or create category and cost center
            category_id = self.add_category(client_id, category_name)
            cost_center_id = self.add_cost_center(client_id, cost_center_name)
            
            # Insert or update pattern
            cursor.execute(
                """INSERT INTO patterns 
                   (client_id, merchant, items_keywords, category_id, cost_center_id, frequency, last_used_at)
                   VALUES (%s, %s, %s, %s, %s, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT (client_id, merchant, category_id, cost_center_id) 
                   DO UPDATE SET 
                       frequency = patterns.frequency + 1,
                       last_used_at = CURRENT_TIMESTAMP,
                       items_keywords = EXCLUDED.items_keywords
                   RETURNING id, frequency""",
                (client_id, merchant.lower(), items_keywords, category_id, cost_center_id)
            )
            
            result = cursor.fetchone()
            print(f"💾 Pattern saved: {merchant} → {category_name}/{cost_center_name} (used {result[1]} times)")
            
            return result[0]
    
    # ============ BUSINESS RULES (Optional) ============
    
    def add_business_rule(self, client_id, rule_text):
        """Add a business rule for the client"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO business_rules (client_id, rule_text) VALUES (%s, %s)",
                (client_id, rule_text)
            )
    
    def get_business_rules(self, client_id):
        """Get all business rules for a client"""
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM business_rules WHERE client_id = %s ORDER BY created_at",
                (client_id,)
            )
            return [dict(row) for row in cursor.fetchall()]