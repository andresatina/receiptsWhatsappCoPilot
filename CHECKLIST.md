# ✅ Deployment Checklist

Use this to track your deployment progress.

---

## 📋 Pre-Deployment

### Google Setup
- [ ] Opened Google Sheet: https://docs.google.com/spreadsheets/d/1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8/edit
- [ ] Clicked "Share" button
- [ ] Added email: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`
- [ ] Set permission to "Editor"
- [ ] Clicked "Send"

- [ ] Opened Drive folder: https://drive.google.com/drive/folders/1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut
- [ ] Clicked "Share" button
- [ ] Added email: `atinareceiptswhatsapp@receipts-479317.iam.gserviceaccount.com`
- [ ] Set permission to "Editor"
- [ ] Clicked "Send"

### Code Setup
- [ ] Created GitHub repository
- [ ] Pushed all project files to repo
- [ ] Verified `credentials.json` is in `.gitignore`
- [ ] Verified `.env` is in `.gitignore`

---

## 🚂 Railway Deployment

### Account Setup
- [ ] Went to https://railway.app
- [ ] Signed up with GitHub account
- [ ] Authorized Railway to access repos

### Project Creation
- [ ] Clicked "New Project"
- [ ] Selected "Deploy from GitHub repo"
- [ ] Connected to GitHub
- [ ] Selected `receipt-agent` repository
- [ ] Railway started building

### Environment Variables
Added all these variables in Railway dashboard:

- [ ] `KAPSO_API_KEY` = `YOUR_KAPSO_API_KEY`
- [ ] `WHATSAPP_PHONE_NUMBER` = `+12019792493`
- [ ] `WEBHOOK_VERIFY_TOKEN` = `receipt_agent_secret_2024`
- [ ] `CLAUDE_API_KEY` = `YOUR_CLAUDE_API_KEY`
- [ ] `GOOGLE_SHEET_ID` = `1K3soZ_i_MpV6jUPzE20sukYh0oBcN1VdWSSo9o6jzX8`
- [ ] `GOOGLE_DRIVE_FOLDER_ID` = `1XKHfbghVnfzjdp4ZYqsEFGfqN_5AWFut`

### Deployment
- [ ] Build completed successfully
- [ ] No errors in build logs
- [ ] Went to "Settings" tab
- [ ] Clicked "Generate Domain"
- [ ] Copied Railway URL: `https://_____________________.railway.app`

---

## 📱 Kapso Configuration

### Webhook Setup
- [ ] Went to https://app.kapso.ai
- [ ] Logged in to account
- [ ] Navigated to Settings → Webhooks
- [ ] Clicked "Add Webhook"
- [ ] Entered webhook URL: `https://[your-railway-url].railway.app/webhook`
- [ ] Entered verify token: `receipt_agent_secret_2024`
- [ ] Saved webhook configuration

---

## 🧪 Testing

### Health Check
- [ ] Opened in browser: `https://[your-railway-url].railway.app/health`
- [ ] Confirmed response: `{"status":"healthy"}`

### Send Test Receipt
- [ ] Saved a test receipt image to phone
- [ ] Sent image to WhatsApp: `+12019792493`
- [ ] Bot responded with "🔍 Processing your receipt..."

### Verify Extraction
- [ ] Bot asked for category
- [ ] Replied with category (e.g., "Meals")
- [ ] Bot asked for cost center
- [ ] Replied with cost center (e.g., "Marketing")

### Check Logs
- [ ] Went to Railway dashboard
- [ ] Clicked on service → "Logs" tab
- [ ] Saw webhook received
- [ ] Saw Claude API call
- [ ] Saw Google Sheets update
- [ ] Saw Google Drive upload
- [ ] No errors in logs

### Verify Data Storage
- [ ] Opened Google Sheet
- [ ] Confirmed new row with receipt data
- [ ] All fields populated correctly

- [ ] Opened Google Drive folder
- [ ] Confirmed receipt image uploaded
- [ ] Image viewable via link

### Verify Confirmation
- [ ] Bot sent "✅ Receipt saved successfully!"
- [ ] Confirmation included summary
- [ ] Summary data matched receipt

---

## 🔄 Test Additional Features

### Duplicate Detection
- [ ] Sent same receipt image again
- [ ] Bot warned about duplicate
- [ ] Asked for confirmation
- [ ] Tested both "yes" and "no" responses

### Multiple Users
- [ ] Had team member send receipt to `+12019792493`
- [ ] Their receipt processed correctly
- [ ] Logged in sheet separately

### Error Handling
- [ ] Sent non-receipt image (random photo)
- [ ] Sent very blurry receipt
- [ ] Confirmed bot handled gracefully

---

## 🎯 Production Readiness

### Security
- [ ] Confirmed credentials.json not in public repo
- [ ] Verified all secrets in Railway env vars
- [ ] Service account has minimal permissions

### Monitoring
- [ ] Set up Railway alerts (optional)
- [ ] Bookmarked Railway logs page
- [ ] Subscribed to Kapso status updates (optional)

### Documentation
- [ ] Shared WhatsApp number with team
- [ ] Created internal guide for users
- [ ] Documented expense categories
- [ ] Listed cost centers for team

### Backup Plan
- [ ] Know how to export Google Sheet
- [ ] Have Railway rollback plan
- [ ] Saved copy of all credentials

---

## 📊 Post-Launch

### First Week
- [ ] Monitor Railway logs daily
- [ ] Check error rates
- [ ] Verify all receipts processing
- [ ] Gather team feedback

### Optimization
- [ ] Review auto-categorization accuracy
- [ ] Adjust categories if needed
- [ ] Add more auto-category rules
- [ ] Optimize conversation flow

### Costs
- [ ] Checked Railway usage
- [ ] Monitored Claude API costs
- [ ] Tracked Kapso message counts
- [ ] Confirmed within budget

---

## ✅ Launch Complete!

- [ ] All tests passed
- [ ] Team trained
- [ ] Documentation shared
- [ ] Monitoring in place
- [ ] Ready for production use

---

**Your Receipt Agent is Live! 🎉**

Send receipts to: **+12019792493**

---

## 📝 Notes & Issues

Use this space to track any issues or observations:

```
Date: ___________
Issue: ___________
Resolution: ___________

Date: ___________
Issue: ___________
Resolution: ___________
```

---

**Need Help?**
- Check TROUBLESHOOTING.md
- Review Railway logs
- Test components separately
