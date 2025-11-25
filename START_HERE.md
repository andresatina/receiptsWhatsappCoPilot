# 📱 WhatsApp Receipt Processing Agent

**Complete automated receipt processing system via WhatsApp**

---

## 🎯 What This Does

Your team sends receipt photos to WhatsApp → Bot automatically:
1. Extracts merchant, date, amount, items (Claude AI)
2. Auto-categorizes the expense
3. Asks for missing info (category, cost center)
4. Detects duplicates
5. Files image to Google Drive
6. Logs everything to Google Sheets
7. Sends confirmation with summary

---

## 📚 Documentation Index

**Start Here:**
- **[QUICKSTART.md](QUICKSTART.md)** - 3-step deployment (10 minutes)

**Detailed Guides:**
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete deployment walkthrough
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Fix common issues
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - How it all works
- **[README.md](README.md)** - Full project documentation

---

## ⚡ Quick Deploy (3 Steps)

### 1. Share Google Resources
Share with: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`
- [Your Google Sheet](https://docs.google.com/spreadsheets/d/1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8/edit)
- [Your Drive Folder](https://drive.google.com/drive/folders/1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut)

### 2. Deploy to Railway
1. Push code to GitHub
2. [Deploy on Railway](https://railway.app)
3. Add environment variables (see QUICKSTART.md)

### 3. Configure Webhook
1. Go to [Kapso Dashboard](https://app.kapso.ai)
2. Add webhook: `https://your-url.railway.app/webhook`
3. Verify token: `receipt_agent_secret_2024`

---

## 📁 Project Files

### Core Application
- `app.py` - Main Flask server & webhook handler
- `whatsapp_handler.py` - Kapso API integration
- `claude_handler.py` - Receipt OCR & extraction
- `sheets_handler.py` - Google Sheets logging
- `drive_handler.py` - Google Drive storage

### Configuration
- `requirements.txt` - Python dependencies
- `Procfile` - Railway deployment config
- `credentials.json` - Google service account key
- `.env` - Environment variables (template)

### Documentation
- `QUICKSTART.md` - Fast deployment guide
- `DEPLOYMENT.md` - Detailed setup instructions
- `TROUBLESHOOTING.md` - Debug & fix issues
- `ARCHITECTURE.md` - System design & flow
- `README.md` - Complete documentation

---

## 🔑 Your Credentials

**Already Configured:**
- ✅ Kapso API Key
- ✅ WhatsApp Number: +12019792493
- ✅ Claude API Key
- ✅ Google Service Account
- ✅ Google Sheet ID
- ✅ Google Drive Folder ID

**Just need to:**
1. Share Google resources
2. Deploy to Railway
3. Configure Kapso webhook

---

## 🏗️ Tech Stack

- **WhatsApp**: Kapso API (official Cloud API wrapper)
- **OCR**: Claude 4 Vision (Anthropic)
- **Storage**: Google Drive
- **Logging**: Google Sheets
- **Backend**: Python Flask
- **Hosting**: Railway (or any Python host)

---

## 💰 Costs

- **Railway**: $5 free/month, then ~$5-10/month
- **Kapso**: Free tier or ~$10-30/month
- **Claude API**: ~$1-3 per 100 receipts
- **Google**: Free

**Total**: ~$15-40/month for production

---

## 🚀 Next Steps

1. **Read QUICKSTART.md** - Deploy in 10 minutes
2. **Test with a receipt** - Send to +12019792493
3. **Check your Sheet** - See the data logged
4. **Browse your Drive** - Find the filed image
5. **Invite team members** - Share WhatsApp number

---

## 📊 What Gets Logged

Every receipt captures:
- Timestamp
- Merchant Name
- Date
- Total Amount
- Category (auto or user-provided)
- Cost Center (user-provided)
- Payment Method
- Line Items (detailed breakdown)
- Google Drive Link
- Image Hash (for duplicate detection)
- Submitted By (phone number)

---

## 🎯 Example Conversation

```
You: [sends receipt photo]

Bot: 🔍 Processing your receipt...
Bot: 📂 What category is this expense? 
     (e.g., Meals, Travel, Supplies)

You: Meals

Bot: 🏢 What cost center should this be assigned to?

You: Marketing

Bot: 💾 Saving receipt...

Bot: ✅ Receipt saved successfully!
     
     📝 Summary:
     • Merchant: Starbucks
     • Date: 2024-11-25
     • Amount: $15.67
     • Category: Meals
     • Cost Center: Marketing
     • Payment: Credit Card
     
     📎 Filed in Google Drive
     📊 Logged in Google Sheets
     
     Send another receipt anytime!
```

---

## ⚠️ Important Notes

**Before Deploying:**
- ✅ Share Google Sheet with service account
- ✅ Share Google Drive folder with service account
- ✅ Never commit credentials.json to public repos
- ✅ Use environment variables for all secrets

**Security:**
- Service account has limited scope (Sheets + Drive only)
- API keys stored in Railway env vars
- Conversation state in memory (cleared after processing)

---

## 🛠️ Customization

**Add More Categories:**
Edit `claude_handler.py` → `_auto_categorize()` function

**Add More Fields:**
Edit `sheets_handler.py` → modify headers and row data

**Change Conversation Flow:**
Edit `app.py` → `ask_for_missing_info()` function

**Adjust Duplicate Handling:**
Edit `app.py` → `handle_receipt_image()` function

---

## 📞 Support

**Documentation:**
- Start with QUICKSTART.md
- Check TROUBLESHOOTING.md for issues
- Review ARCHITECTURE.md to understand flow

**Still Stuck?**
- Check Railway logs
- Test each component separately
- Verify all sharing permissions

---

## ✅ Pre-Flight Checklist

Before going live:
- [ ] Google Sheet shared with service account (Editor)
- [ ] Google Drive folder shared with service account (Editor)
- [ ] All environment variables set in Railway
- [ ] Kapso webhook configured correctly
- [ ] Health endpoint responds (test `/health`)
- [ ] Test receipt processes successfully
- [ ] Sheet updates with correct data
- [ ] Drive shows uploaded image
- [ ] Bot sends confirmation message

---

## 🎉 Ready to Deploy?

**Start here:** [QUICKSTART.md](QUICKSTART.md)

Or jump straight to detailed setup: [DEPLOYMENT.md](DEPLOYMENT.md)

---

**Built with:**
- Python + Flask
- Claude AI (Anthropic)
- Kapso WhatsApp API
- Google Workspace APIs
- Railway hosting

---

*All credentials are pre-configured. Just deploy and start sending receipts!*
