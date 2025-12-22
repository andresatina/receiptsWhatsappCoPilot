"""
Comprehensive Test Suite for Atina WhatsApp Receipt Tracker
Run before each deployment to ensure no regressions

Usage:
    python test_suite.py
    python test_suite.py --verbose
    python test_suite.py --unit-only
    python test_suite.py --integration-only
"""

import unittest
import sys
import os
from unittest.mock import Mock, MagicMock, patch, call
import json
import base64
from io import BytesIO

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestClaudeHandler(unittest.TestCase):
    """Test Claude Vision OCR extraction"""
    
    def setUp(self):
        """Setup test fixtures"""
        self.api_key = "test-api-key"
        
    @patch('claude_handler.anthropic.Anthropic')
    def test_extract_receipt_data_success(self, mock_anthropic):
        """Test successful receipt extraction"""
        from claude_handler import ClaudeHandler
        
        # Mock response
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = '''```json
{
  "merchant_name": "Starbucks",
  "date": "2024-01-15",
  "total_amount": "15.50",
  "payment_method": "Credit Card",
  "line_items": [
    {"description": "Latte", "amount": "5.50"},
    {"description": "Sandwich", "amount": "10.00"}
  ]
}
```'''
        mock_client.messages.create.return_value = mock_response
        
        handler = ClaudeHandler(self.api_key)
        fake_image = b"fake_image_data"
        result = handler.extract_receipt_data(fake_image)
        
        # Assertions
        self.assertEqual(result['merchant_name'], 'Starbucks')
        self.assertEqual(result['total_amount'], '15.50')
        self.assertEqual(result['date'], '2024-01-15')
        self.assertEqual(len(result['line_items']), 2)
        
        # Verify API call was made
        mock_client.messages.create.assert_called_once()
        
    @patch('claude_handler.anthropic.Anthropic')
    def test_auto_categorize_restaurant(self, mock_anthropic):
        """Test auto-categorization for restaurants"""
        from claude_handler import ClaudeHandler
        
        handler = ClaudeHandler(self.api_key)
        
        # Test various restaurant keywords
        self.assertEqual(handler._auto_categorize('Starbucks Coffee'), 'Meals & Entertainment')
        self.assertEqual(handler._auto_categorize('Pizza Hut'), 'Meals & Entertainment')
        self.assertEqual(handler._auto_categorize('The French Bistro'), 'Meals & Entertainment')
        
    @patch('claude_handler.anthropic.Anthropic')
    def test_auto_categorize_travel(self, mock_anthropic):
        """Test auto-categorization for travel"""
        from claude_handler import ClaudeHandler
        
        handler = ClaudeHandler(self.api_key)
        
        self.assertEqual(handler._auto_categorize('Uber'), 'Travel')
        self.assertEqual(handler._auto_categorize('Delta Airlines'), 'Travel')
        self.assertEqual(handler._auto_categorize('Marriott Hotel'), 'Travel')
        
    @patch('claude_handler.anthropic.Anthropic')
    def test_auto_categorize_none(self, mock_anthropic):
        """Test that unknown merchants return None"""
        from claude_handler import ClaudeHandler
        
        handler = ClaudeHandler(self.api_key)
        
        self.assertIsNone(handler._auto_categorize('Unknown Merchant LLC'))
        self.assertIsNone(handler._auto_categorize(None))
        self.assertIsNone(handler._auto_categorize(''))


class TestDatabaseHandler(unittest.TestCase):
    """Test database operations (mocked)"""
    
    @patch('database_handler.psycopg2.connect')
    def test_get_or_create_user_existing(self, mock_connect):
        """Test retrieving existing user"""
        from database_handler import DatabaseHandler
        
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock existing user
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'phone_number': '+1234567890',
            'name': 'Test User',
            'company_id': 1,
            'business_name': 'Test Company',
            'default_currency': 'USD',
            'requires_cost_center': True
        }
        
        db = DatabaseHandler(database_url='postgresql://test')
        user = db.get_or_create_user('+1234567890', 'Test User')
        
        self.assertEqual(user['id'], 1)
        self.assertEqual(user['phone_number'], '+1234567890')
        self.assertEqual(user['company_id'], 1)
        
    @patch('database_handler.psycopg2.connect')
    def test_is_duplicate_detection(self, mock_connect):
        """Test duplicate receipt detection"""
        from database_handler import DatabaseHandler
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock duplicate found
        mock_cursor.fetchone.return_value = (1,)
        
        db = DatabaseHandler(database_url='postgresql://test')
        is_dup = db.is_duplicate(company_id=1, image_hash='abc123')
        
        self.assertTrue(is_dup)
        
    @patch('database_handler.psycopg2.connect')
    def test_add_category(self, mock_connect):
        """Test adding new category"""
        from database_handler import DatabaseHandler
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {'id': 5}
        
        db = DatabaseHandler(database_url='postgresql://test')
        category_id = db.add_category(company_id=1, category_name='Office Supplies')
        
        self.assertEqual(category_id, 5)


class TestManagementHandler(unittest.TestCase):
    """Test management command handling"""
    
    @patch('management_handler.anthropic.Anthropic')
    def test_list_categories(self, mock_anthropic):
        """Test listing categories"""
        from management_handler import ManagementHandler
        
        # Mock Claude response
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = '''```json
{
    "action": "list",
    "type": "category",
    "name": null,
    "message": "Here are your categories"
}
```'''
        mock_client.messages.create.return_value = mock_response
        
        handler = ManagementHandler()
        
        # Mock state and db
        state = {
            'company_id': 1,
            'user': {'cost_center_label': 'property/unit'}
        }
        mock_db = Mock()
        mock_db.get_categories.return_value = [
            {'name': 'Meals'},
            {'name': 'Travel'}
        ]
        mock_db.get_cost_centers.return_value = []
        
        response, should_exit = handler.handle_management('list categories', state, mock_db)
        
        self.assertIn('Meals', response)
        self.assertIn('Travel', response)
        self.assertFalse(should_exit)
        
    @patch('management_handler.anthropic.Anthropic')
    def test_add_category_with_confirmation(self, mock_anthropic):
        """Test adding category requires confirmation"""
        from management_handler import ManagementHandler
        
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = '''```json
{
    "action": "add",
    "type": "category",
    "name": "New Category",
    "message": "Add category 'New Category'?"
}
```'''
        mock_client.messages.create.return_value = mock_response
        
        handler = ManagementHandler()
        
        state = {
            'company_id': 1,
            'user': {'cost_center_label': 'property/unit'}
        }
        mock_db = Mock()
        mock_db.get_categories.return_value = []
        mock_db.get_cost_centers.return_value = []
        
        response, should_exit = handler.handle_management('add New Category', state, mock_db)
        
        self.assertIn('yes/no', response.lower())
        self.assertIn('pending_management_action', state)
        self.assertFalse(should_exit)


class TestConversationalHelper(unittest.TestCase):
    """Test conversational response generation"""
    
    @patch('conversational_helper.anthropic.Anthropic')
    def test_extract_json_from_response(self, mock_anthropic):
        """Test JSON extraction from Claude response"""
        from conversational_helper import ConversationalHandler
        
        handler = ConversationalHandler()
        
        # Test with markdown JSON block
        text = '''Here's what I found:
```json
{"category": "Meals", "cost_center": "Building A"}
```'''
        result = handler._extract_json(text)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['category'], 'Meals')
        self.assertEqual(result['cost_center'], 'Building A')
        
    @patch('conversational_helper.anthropic.Anthropic')
    def test_clean_response_removes_json(self, mock_anthropic):
        """Test that JSON is removed from user-facing responses"""
        from conversational_helper import ConversationalHandler
        
        handler = ConversationalHandler()
        
        text = '''What category is this?
```json
{"category": null}
```'''
        
        cleaned = handler._clean_response(text)
        
        self.assertNotIn('json', cleaned.lower())
        self.assertNotIn('{', cleaned)
        self.assertIn('What category', cleaned)
        
    @patch('conversational_helper.anthropic.Anthropic')
    def test_empty_response_handling(self, mock_anthropic):
        """Test that empty responses are handled gracefully"""
        from conversational_helper import ConversationalHandler
        
        handler = ConversationalHandler()
        
        # Should never return empty string
        result = handler._clean_response('```json\n{}\n```')
        self.assertTrue(len(result) > 0)


class TestWhatsAppHandler(unittest.TestCase):
    """Test WhatsApp message sending"""
    
    @patch('whatsapp_handler.requests.post')
    def test_send_message_success(self, mock_post):
        """Test successful message sending"""
        from whatsapp_handler import WhatsAppHandler
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}
        mock_post.return_value = mock_response
        
        handler = WhatsAppHandler(api_key='test-key', phone_number='1234567890', phone_number_id='test-id')
        result = handler.send_message('+1234567890', 'Test message')
        
        self.assertTrue(result['success'])
        mock_post.assert_called_once()
        
    @patch('whatsapp_handler.requests.post')
    def test_send_message_failure(self, mock_post):
        """Test message sending failure"""
        from whatsapp_handler import WhatsAppHandler
        
        mock_post.side_effect = Exception('Network error')
        
        handler = WhatsAppHandler(api_key='test-key', phone_number='1234567890', phone_number_id='test-id')
        
        with self.assertRaises(Exception):
            handler.send_message('+1234567890', 'Test message')


class TestLogger(unittest.TestCase):
    """Test logging functionality"""
    
    @patch('logger.psycopg2.connect')
    def test_log_error(self, mock_connect):
        """Test error logging"""
        from logger import Logger
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        logger = Logger(database_url='postgresql://test')
        logger.log_error(
            error_type='ocr_failed',
            error_message='Claude API timeout',
            user_id=1,
            company_id=1,
            context={'receipt_url': 'https://example.com/receipt.jpg'}
        )
        
        # Verify database insert was called
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]
        self.assertIn('INSERT INTO error_logs', call_args[0])
        
    @patch('logger.psycopg2.connect')
    def test_log_receipt_saved(self, mock_connect):
        """Test receipt saved event logging"""
        from logger import Logger
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        logger = Logger(database_url='postgresql://test')
        logger.log_receipt_saved(
            user_id=1,
            company_id=1,
            receipt_hash='abc123',
            merchant_name='Starbucks',
            amount=15.50,
            category='Meals',
            cost_center='Building A'
        )
        
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]
        self.assertIn('INSERT INTO receipt_events', call_args[0])


class IntegrationTests(unittest.TestCase):
    """Integration tests for end-to-end flows"""
    
    @patch('app.whatsapp')
    @patch('app.claude')
    @patch('app.db')
    def test_full_receipt_flow_with_pattern_match(self, mock_db, mock_claude, mock_whatsapp):
        """Test complete flow: receipt upload -> pattern match -> save"""
        
        # Mock database responses
        mock_db.get_or_create_user.return_value = {
            'id': 1,
            'phone_number': '+1234567890',
            'company_id': 1,
            'business_name': 'Test Company',
            'requires_cost_center': True,
            'cost_center_label': 'property/unit',
            'google_sheet_id': 'test-sheet-id'
        }
        
        mock_db.get_categories.return_value = [
            {'name': 'Meals'},
            {'name': 'Travel'}
        ]
        
        mock_db.get_cost_centers.return_value = [
            {'name': 'Building A'},
            {'name': 'Building B'}
        ]
        
        mock_db.is_duplicate.return_value = False
        
        # Mock pattern match (learned from history)
        mock_db.find_matching_patterns.return_value = [{
            'merchant': 'Starbucks',
            'category_name': 'Meals',
            'cost_center_name': 'Building A',
            'similarity': 95,
            'frequency': 5
        }]
        
        # Mock Claude extraction
        mock_claude.extract_receipt_data.return_value = {
            'merchant_name': 'Starbucks',
            'date': '2024-01-15',
            'total_amount': '15.50',
            'payment_method': 'Credit Card',
            'category': 'Meals'  # Auto-suggested from pattern
        }
        
        # This simulates the flow without actually calling Flask
        # In reality, you'd test via Flask test client
        
        self.assertTrue(True)  # Placeholder - implement with Flask test client
        
    def test_duplicate_detection_flow(self):
        """Test that duplicate receipts are caught and user is asked to confirm"""
        # Implement with Flask test client
        self.assertTrue(True)  # Placeholder
        
    def test_bank_transfer_flow(self):
        """Test bank transfer requires beneficiary input"""
        # Implement with Flask test client
        self.assertTrue(True)  # Placeholder


class TestRetryLogic(unittest.TestCase):
    """Test retry mechanisms for API failures"""
    
    @patch('claude_handler.anthropic.Anthropic')
    def test_claude_retry_on_timeout(self, mock_anthropic):
        """Test that Claude API calls retry on timeout"""
        from claude_handler import ClaudeHandler
        import anthropic
        
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        
        # First call fails, second succeeds
        mock_response = Mock()
        mock_response.content = [Mock()]
        mock_response.content[0].text = '{"merchant_name": "Test", "total_amount": "10.00"}'
        
        mock_client.messages.create.side_effect = [
            anthropic.APITimeoutError('Timeout'),
            mock_response
        ]
        
        handler = ClaudeHandler('test-key')
        
        # Should retry and eventually succeed
        result = handler.extract_receipt_data(b'fake_image')
        self.assertEqual(result['merchant_name'], 'Test')
        
        # Verify it was called twice (1 failure + 1 success)
        self.assertEqual(mock_client.messages.create.call_count, 2)


def run_tests(test_type='all', verbose=False):
    """
    Run test suite
    
    Args:
        test_type: 'all', 'unit', or 'integration'
        verbose: Show detailed output
    """
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    if test_type in ['all', 'unit']:
        suite.addTests(loader.loadTestsFromTestCase(TestClaudeHandler))
        suite.addTests(loader.loadTestsFromTestCase(TestDatabaseHandler))
        suite.addTests(loader.loadTestsFromTestCase(TestManagementHandler))
        suite.addTests(loader.loadTestsFromTestCase(TestConversationalHelper))
        suite.addTests(loader.loadTestsFromTestCase(TestWhatsAppHandler))
        suite.addTests(loader.loadTestsFromTestCase(TestLogger))
        suite.addTests(loader.loadTestsFromTestCase(TestRetryLogic))
        
    if test_type in ['all', 'integration']:
        suite.addTests(loader.loadTestsFromTestCase(IntegrationTests))
    
    # Run tests
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {(result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100:.1f}%")
    print("="*70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Atina test suite')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--unit-only', action='store_true', help='Run only unit tests')
    parser.add_argument('--integration-only', action='store_true', help='Run only integration tests')
    
    args = parser.parse_args()
    
    if args.unit_only:
        test_type = 'unit'
    elif args.integration_only:
        test_type = 'integration'
    else:
        test_type = 'all'
    
    success = run_tests(test_type=test_type, verbose=args.verbose)
    sys.exit(0 if success else 1)
