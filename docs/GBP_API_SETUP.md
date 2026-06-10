# Google Business Profile (GBP) API — setup for RankPilot

RankPilot connects to GBP via OAuth (`business.manage` scope) and these Google APIs:

- **My Business Account Management API** — list accounts
- **My Business Business Information API** — list/select locations

This is **not** the same as enabling “Google Maps” or “Places” in Cloud Console. GBP has an extra **approval step** from Google before your Cloud project can call the APIs in production.

Official guide: [GBP API prerequisites](https://developers.google.com/my-business/content/prereqs#request-access)

---

## What Google requires (before API access)

| Requirement | What it means for you |
|-------------|------------------------|
| Google Account | Account used for OAuth must be **owner or manager** on the GBP you want to connect |
| Verified GBP | A Business Profile that is **verified** and **active for 60+ days** (your office or a client’s) |
| Website on GBP | That profile must list a **real business website** |
| Cloud project | Same project as `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (e.g. SERPMapper) |
| **API access application** | Submit Google’s form — **approval is mandatory** |

Until Google approves your project, quota is often **0 QPM** and location listing fails even if OAuth “Connect” works.

---

## Step 1 — Google Cloud project (RankPilot)

1. Open [Google Cloud Console](https://console.cloud.google.com/) → select your project (e.g. **SERPMapper**).
2. Note the **Project number** on the dashboard (needed for the access request).

---

## Step 2 — Request GBP API access (required)

Follow [Request access to the APIs](https://developers.google.com/my-business/content/prereqs#request-access):

1. In Cloud Console, open your project and copy the **Project number**.
2. Submit the [GBP API contact form](https://support.google.com/business/contact/api_default) (or the form linked from the prerequisites page).
3. Choose **“Application for Basic API Access”**.
4. Use an email that is an **owner/manager** on the verified GBP (e.g. `analytics@ctanalytics.net.au` if that account manages the profile).
5. Wait for Google’s follow-up email (can take days).

**Check approval status**

- Cloud Console → **APIs & Services** → **Enabled APIs** → open a Business Profile API → **Quotas**
- **0 QPM** = not approved yet
- **300 QPM** = approved ([per Google docs](https://developers.google.com/my-business/content/prereqs#request-access))

---

## Step 3 — Enable APIs (after approval)

**APIs & Services → Library** → enable:

| API name in Library |
|---------------------|
| My Business Account Management API |
| My Business Business Information API |

---

## Step 4 — OAuth client (Web application)

**APIs & Services → Credentials → OAuth 2.0 Client ID (Web application)**

**Authorized redirect URIs** (exact paths):

```
http://localhost:8000/api/v1/integrations/google/callback
https://rankpilot-serp.up.railway.app/api/v1/integrations/google/callback
```

**OAuth consent screen**

- **Testing**: only emails listed under **Test users** can connect (max 100).
- **In production**: any user can try; restricted scopes may still need [app verification](https://developers.google.com/identity/protocols/oauth2/policies).

**Authorized domains** (consent screen): add `railway.app` (not the full `*.up.railway.app` URL).

---

## Step 5 — RankPilot environment variables

**`backend/.env`** (local) and **Railway backend service** (production):

```env
GOOGLE_CLIENT_ID=xxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
GOOGLE_REDIRECT_BASE_URL=http://localhost:8000
```

Production:

```env
GOOGLE_REDIRECT_BASE_URL=https://rankpilot-serp.up.railway.app
```

Restart the backend after changes.

---

## Step 6 — Connect in the app

1. Log in to RankPilot (email/password — not Google login).
2. Onboarding → **Connect** on **Google Business Profile**.
3. Sign in with the Google account that **owns/manages** the location.
4. Pick the location in the modal.

If the list is empty or errors:

- Reconnect with the **GBP owner** account (not a personal Gmail with no locations).
- Confirm APIs are enabled and project quota is **300 QPM**, not 0.
- Confirm the connecting email is a **Test user** while the app is in Testing mode.

---

## Common errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Access blocked` / `403 access_denied` | OAuth app in **Testing**, email not in **Test users** | Add email under Test users or Publish app |
| `400 invalid_request` on redirect | Redirect URI mismatch | Add full `/api/v1/integrations/google/callback` URL in Credentials |
| `Request contains an invalid argument` | Missing `readMask` on locations API (fixed in code) or API not enabled | Enable Business Information API; redeploy backend |
| `No properties found` / empty list | Wrong Google account, no locations, or **0 QPM** quota | Use owner account; wait for GBP API approval |
| `service is disabled` | APIs not enabled in Cloud Console | Enable both My Business APIs |
| Description publishes, **photo** fails (`request-access`) | Description uses **Business Information API**; photos use **Media API** (may need extra approval + **Google My Business API** enabled) | [Request access](https://developers.google.com/my-business/content/prereqs#request-access); or upload photos at business.google.com |
| Photo publish on **localhost** | Google cannot download images from `localhost` | Use **ngrok** (below) or set `PUBLIC_API_BASE_URL` to Railway / production API |

### Photo publish on localhost (ngrok)

Google must fetch the image over **public HTTPS**. Keep `GOOGLE_REDIRECT_BASE_URL=http://localhost:8000` for OAuth; use a separate public URL for photos only.

1. Start backend: `python -m uvicorn app.main:app --reload --port 8000`
2. In another terminal: `ngrok http 8000`
3. Copy the **https** forwarding URL (e.g. `https://abc123.ngrok-free.app`)
4. In `backend/.env`:
   ```env
   PUBLIC_API_BASE_URL=https://abc123.ngrok-free.app
   ```
   (no trailing slash)
5. Restart the backend, then **Publish** on the GBP Photos tab.

RankPilot builds a signed URL like `{PUBLIC_API_BASE_URL}/api/v1/gbp/photos/{id}/publish-source?...` for Google to download the file.

---

## RankPilot vs OAuth-only products

| Layer | GSC / GA4 | GBP |
|-------|-----------|-----|
| Enable API in Console | Usually enough | **Not enough** — need Google’s **Basic API Access** approval |
| OAuth scope | Sensitive | **Restricted** (`business.manage`) |
| Typical timeline | Same day | Days to weeks for API access approval |

---

## Links

- [Prerequisites & request access](https://developers.google.com/my-business/content/prereqs#request-access)
- [Basic setup (after approval)](https://developers.google.com/my-business/content/basic-setup)
- [OAuth with GBP APIs](https://developers.google.com/my-business/content/implement-oauth)
- [List locations (`readMask` required)](https://developers.google.com/my-business/reference/businessinformation/rest/v1/accounts.locations/list)
