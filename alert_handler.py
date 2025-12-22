"""
Alert Handler - Failed receipts queue and Slack notifications
"""

import os
import requests
import psycopg2
from psycopg2.extras import Json
from datetime import datetime, timedelta


class AlertHandler:
    """Handles failed receipts and anomaly alerts"""
    
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
    
    def save_failed_receipt(self, user_id, company_id, phone_number, receipt_url, 
                           failure_reason, context=None):
        """Save failed receipt to queue"""
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO failed_receipts 
                   (user_id, company_id, phone_number, receipt_url, failure_reason, context)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (user_id, company_id, phone_number, receipt_url, failure_reason, Json(context or {}))
            )
            
            failed_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            
            print(f"💾 Failed receipt saved: ID {failed_id}")
            return failed_id
            
        except Exception as e:
            print(f"Error saving failed receipt: {str(e)}")
            return None
    
    def log_anomaly(self, alert_type, severity, description, user_id=None, 
                    company_id=None, context=None):
        """Log anomaly to database and send Slack alert"""
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            cursor.execute(
                """INSERT INTO anomaly_alerts 
                   (alert_type, user_id, company_id, severity, description, context, notified_at)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW())
                   RETURNING id""",
                (alert_type, user_id, company_id, severity, description, Json(context or {}))
            )
            
            alert_id = cursor.fetchone()[0]
            conn.commit()
            conn.close()
            
            print(f"🚨 Anomaly logged: {alert_type} - {description}")
            
            # Send to Slack
            self.send_slack_alert(severity, alert_type, description, context)
            
            return alert_id
            
        except Exception as e:
            print(f"Error logging anomaly: {str(e)}")
            return None
    
    def send_slack_alert(self, severity, alert_type, description, context=None):
        """Send alert to Slack"""
        if not self.slack_webhook:
            print("⚠️  Slack webhook not configured")
            return
        
        # Color based on severity
        color = {
            'critical': '#FF0000',
            'warning': '#FFA500',
            'info': '#0000FF'
        }.get(severity, '#808080')
        
        # Build message
        payload = {
            "attachments": [{
                "color": color,
                "title": f"🚨 {severity.upper()}: {alert_type}",
                "text": description,
                "fields": [
                    {
                        "title": "Time",
                        "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "short": True
                    }
                ],
                "footer": "Atina Alert System"
            }]
        }
        
        # Add context if available
        if context:
            if context.get('user_id'):
                payload["attachments"][0]["fields"].append({
                    "title": "User ID",
                    "value": str(context['user_id']),
                    "short": True
                })
            if context.get('phone_number'):
                payload["attachments"][0]["fields"].append({
                    "title": "Phone",
                    "value": context['phone_number'],
                    "short": True
                })
        
        try:
            response = requests.post(self.slack_webhook, json=payload)
            if response.status_code == 200:
                print("✅ Slack alert sent")
            else:
                print(f"❌ Slack alert failed: {response.status_code}")
        except Exception as e:
            print(f"Error sending Slack alert: {str(e)}")
    
    def check_consecutive_events(self, user_id, event_type, threshold=3):
        """Check if same event happened N times consecutively without progress"""
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            # Get last N events for this user
            cursor.execute(
                """SELECT event_type FROM receipt_events 
                   WHERE user_id = %s 
                   ORDER BY created_at DESC 
                   LIMIT %s""",
                (user_id, threshold)
            )
            
            recent_events = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            # Check if all are the same event
            if len(recent_events) >= threshold and all(e == event_type for e in recent_events):
                return True
            
            return False
            
        except Exception as e:
            print(f"Error checking consecutive events: {str(e)}")
            return False
    
    def check_failure_rate(self, user_id, minutes=10, threshold=3):
        """Check if user had N failures in last M minutes"""
        try:
            conn = psycopg2.connect(self.database_url)
            cursor = conn.cursor()
            
            time_threshold = datetime.now() - timedelta(minutes=minutes)
            
            cursor.execute(
                """SELECT COUNT(*) FROM error_logs 
                   WHERE user_id = %s 
                   AND created_at > %s""",
                (user_id, time_threshold)
            )
            
            failure_count = cursor.fetchone()[0]
            conn.close()
            
            return failure_count >= threshold
            
        except Exception as e:
            print(f"Error checking failure rate: {str(e)}")
            return False


# Global instance
alert_handler = AlertHandler()
