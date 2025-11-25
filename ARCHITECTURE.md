# 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        RECEIPT FLOW                              │
└─────────────────────────────────────────────────────────────────┘

1. USER SENDS RECEIPT
   ┌──────────┐
   │ WhatsApp │  📸 User sends receipt image
   │  User    │
   └────┬─────┘
        │
        ▼
   ┌──────────┐
   │  Kapso   │  Receives message, stores it
   │   API    │
   └────┬─────┘
        │
        │ Webhook POST /webhook
        ▼

2. FLASK SERVER RECEIVES
   ┌─────────────┐
   │   Railway   │
   │ Flask App   │  ← Your deployed server
   │  (app.py)   │
   └──────┬──────┘
          │
          ├─────────────────────────┐
          │                         │
          ▼                         ▼
   
3. PROCESS IMAGE          4. CHECK DUPLICATE
   ┌──────────┐              ┌──────────┐
   │  Claude  │              │  Sheets  │
   │  Vision  │              │  Handler │
   │   API    │              └──────────┘
   └────┬─────┘                    │
        │                          │
        │ Extract:                 │ SHA256 hash
        │ • Merchant               │ check
        │ • Date                   │
        │ • Amount                 ▼
        │ • Items              Is duplicate?
        │ • Payment            ├─ YES → Ask confirm
        │                      └─ NO  → Continue
        ▼
   Auto-categorize
   (Meals, Travel, etc.)

5. COLLECT MISSING INFO
   ┌──────────┐
   │ WhatsApp │  🤖 "What category?"
   │   Bot    │  👤 "Meals"
   └────┬─────┘  🤖 "What cost center?"
        │         👤 "Marketing"
        │
        ▼
   ┌──────────┐
   │  Claude  │  Parse user responses
   │   API    │  Update extracted data
   └──────────┘

6. SAVE TO GOOGLE
   ┌─────────────┐
   │Google Drive │  📎 Upload image
   │             │  → Get shareable link
   └─────────────┘
          │
          ▼
   ┌─────────────┐
   │Google Sheets│  📊 Log all data:
   │             │  • Timestamp
   │             │  • Merchant
   │             │  • Date
   │             │  • Amount
   │             │  • Category
   │             │  • Cost Center
   │             │  • Payment Method
   │             │  • Line Items
   │             │  • Drive URL
   │             │  • Hash
   └─────────────┘

7. CONFIRM TO USER
   ┌──────────┐
   │ WhatsApp │  ✅ "Receipt saved!"
   │   Bot    │  📝 Shows summary
   └──────────┘
```

---

## 🔄 Conversation State Management

```
conversation_states = {
  "+15551234567": {
    "state": "collecting_info",
    "image_data": <bytes>,
    "image_hash": "abc123...",
    "extracted_data": {
      "merchant_name": "Starbucks",
      "date": "2024-11-25",
      "total_amount": "15.67",
      "category": "Meals",  ← Auto-assigned
      "cost_center": null,  ← Need to ask
      "payment_method": "Credit Card",
      "line_items": [...]
    },
    "current_question": "cost_center"
  }
}
```

---

## 📦 Component Breakdown

### whatsapp_handler.py
- Sends messages via Kapso API
- Downloads media from WhatsApp
- Handles message formatting

### claude_handler.py
- Extracts receipt data from image
- Auto-categorizes based on merchant
- Parses user text responses
- Updates data with new info

### sheets_handler.py
- Creates/maintains sheet headers
- Appends new receipt rows
- Checks for duplicate hashes
- Formats line items as strings

### drive_handler.py
- Uploads images to specific folder
- Makes files publicly viewable
- Returns shareable links

### app.py
- Receives webhooks from Kapso
- Manages conversation state
- Orchestrates all handlers
- Controls conversation flow

---

## 🔐 Security Notes

**Credentials:**
- `credentials.json` contains Google service account private key
- NEVER commit to public repos
- Use environment variables for all secrets

**API Keys:**
- Stored as Railway environment variables
- Never hardcoded in source files
- Rotatable without code changes

**Data Storage:**
- Conversation states stored in memory (non-persistent)
- For production, use Redis or database
- Receipt images hashed for duplicate detection

---

## 🚀 Scaling Considerations

**Current Setup (Small Team):**
- In-memory conversation state
- Single Railway instance
- Good for <100 receipts/day

**For Large Teams:**
- Add Redis for conversation state
- Use database instead of Sheets
- Implement queue system (Celery)
- Add multiple Railway instances
- Consider containerization (Docker)

---

## 📊 Data Flow Summary

```
Receipt Photo
    ↓
WhatsApp → Kapso → Webhook → Flask
    ↓
Claude Vision (OCR)
    ↓
Auto-Categorize
    ↓
Ask Missing Info → User Responds → Update Data
    ↓
Hash Check (Duplicate?)
    ↓
Upload to Drive ← Generate Link
    ↓
Log to Sheets
    ↓
Send Confirmation → WhatsApp User
```

---

## 🎯 Success Metrics

Track these in Google Sheets:
- Receipts processed per day
- Average processing time
- Auto-categorization accuracy
- Duplicate detection hits
- User response time
- Error rates

Add a timestamp column to measure performance!
