# Google Cloud OAuth Access Token Generator

## ✅ Successfully Working!

Your service account is now generating valid OAuth access tokens.

---

## 📁 Files Created

### 1. `get_access_token.py` - Main Token Generator
- **Purpose**: Automatically generates OAuth access tokens from your service account
- **Features**:
  - Generates access tokens with cloud-platform scope
  - Validates token authenticity
  - Saves token to `access_token.txt`
  - Shows token expiry time
  - Comprehensive error handling

**Usage:**
```powershell
python get_access_token.py
```

### 2. `get_token_with_custom_scope.py` - Custom Scope Generator
- **Purpose**: Generate tokens with specific Google Cloud API scopes
- **Features**:
  - Interactive menu for selecting scopes
  - Pre-configured options for common APIs:
    - Cloud Platform (Full Access)
    - Generative AI / Gemini API
    - Vertex AI
    - Cloud Storage
    - Compute Engine
    - BigQuery
    - Custom scope option
  - Saves token with scope information

**Usage:**
```powershell
python get_token_with_custom_scope.py
```

### 3. `access_token.txt` - Saved Token
- Contains your current valid access token
- Automatically updated each time you run the scripts
- Includes expiry information

---

## 🔑 Current Token Status

✅ **Token Generated Successfully!**
- **Service Account**: temporary-check@temporary-check-oauth.iam.gserviceaccount.com
- **Project ID**: temporary-check-oauth
- **Scope**: https://www.googleapis.com/auth/cloud-platform
- **Expires**: ~1 hour from generation
- **Valid**: ✓ Confirmed via Google's tokeninfo endpoint

---

## 🚀 How to Use the Access Token

### In HTTP Requests (cURL)
```bash
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  https://api.example.com/endpoint
```

### In Python (requests library)
```python
import requests

headers = {
    'Authorization': 'Bearer YOUR_ACCESS_TOKEN',
    'Content-Type': 'application/json'
}

response = requests.get('https://api.example.com/endpoint', headers=headers)
```

### In Python (Google Client Libraries)
```python
from google.oauth2 import service_account
import google.auth.transport.requests

credentials = service_account.Credentials.from_service_account_file(
    'temp-acc-1.json',
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)

# The library handles token refresh automatically
```

---

## 🔧 Troubleshooting

### Error: "PERMISSION_DENIED" or "ACCESS_TOKEN_SCOPE_INSUFFICIENT"

**Cause**: The service account doesn't have the required permissions or the wrong scope is being used.

**Solutions**:
1. **Check IAM Permissions** in Google Cloud Console:
   - Go to IAM & Admin → Service Accounts
   - Ensure your service account has the necessary roles
   - For AI/ML APIs, you may need roles like:
     - `AI Platform Admin`
     - `Vertex AI User`
     - `Storage Object Viewer/Admin` (if accessing storage)

2. **Enable Required APIs**:
   - Go to APIs & Services → Library
   - Search for and enable the API you're trying to use
   - Common APIs:
     - Vertex AI API
     - Generative Language API
     - Cloud AI Platform API

3. **Use Correct Scope**:
   - Use `get_token_with_custom_scope.py` to select the appropriate scope
   - The `cloud-platform` scope gives broad access but the service account still needs IAM permissions

4. **Grant Service Account Permissions**:
   ```bash
   # Example: Grant AI Platform Admin role
   gcloud projects add-iam-policy-binding PROJECT_ID \
     --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
     --role="roles/aiplatform.admin"
   ```

---

## 📝 Important Notes

1. **Token Expiry**: Access tokens expire after 1 hour. Re-run the script to get a fresh token.

2. **Security**: 
   - Never commit `temp-acc-1.json` or `access_token.txt` to version control
   - Add them to `.gitignore`
   - Store service account keys securely

3. **Scopes**: The `cloud-platform` scope is very broad. For production:
   - Use the minimum required scopes
   - Follow the principle of least privilege

4. **Service Account Permissions**: 
   - Having a valid token doesn't mean you can access all APIs
   - The service account must have proper IAM roles in Google Cloud Console
   - Check the error message to see which specific permission is missing

---

## 🎯 Quick Reference

### Generate Token (Default Scope)
```powershell
python get_access_token.py
```

### Generate Token (Custom Scope)
```powershell
python get_token_with_custom_scope.py
```

### Read Saved Token
```powershell
Get-Content access_token.txt
```

### Check Token Validity
The token is automatically validated when generated. You can also check manually:
```bash
curl https://oauth2.googleapis.com/tokeninfo?access_token=YOUR_TOKEN
```

---

## 📚 Useful Links

- [Google Cloud IAM Documentation](https://cloud.google.com/iam/docs)
- [Service Account Keys Best Practices](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)
- [OAuth 2.0 Scopes for Google APIs](https://developers.google.com/identity/protocols/oauth2/scopes)
- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)

---

**Last Updated**: November 4, 2025
**Status**: ✅ Working
