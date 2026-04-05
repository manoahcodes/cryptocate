# Paddle Billing — WhaleWatch

## Overview

WhaleWatch uses [Paddle](https://paddle.com/) for subscription billing.
Paddle acts as the Merchant of Record — it handles tax, VAT, and compliance globally.

## Setup

### 1. Create a Paddle account

- Go to https://paddle.com and create an account
- Switch to **Sandbox** mode for development (https://sandbox-vendors.paddle.com)

### 2. Create a product and price

1. Catalog → Products → New Product → "cyptocate Pro"
2. Catalog → Prices → New Price → $29.00/month recurring
3. Copy the **Price ID** (e.g. `pri_01abc...`) → set as `PADDLE_PRICE_ID`

### 3. Get API credentials

- Developer Tools → Authentication → API Keys → Generate
- Copy the key → set as `PADDLE_API_KEY`

### 4. Configure webhooks

- Developer Tools → Notifications → New notification destination
- URL: `https://your-app.railway.app/bot/paddle/webhook/`
- Events to subscribe:
  - `subscription.activated`
  - `subscription.canceled`
  - `subscription.paused`
  - `subscription.updated`
  - `transaction.completed`
- Copy the **signing secret** → set as `PADDLE_WEBHOOK_SECRET`

### 5. Environment variables

```
PADDLE_API_KEY=pdl_sbox_...
PADDLE_WEBHOOK_SECRET=pdlntfy_...
PADDLE_PRICE_ID=pri_...
PADDLE_SANDBOX=True          # False in production
```

## OAuth Callback URLs

### Google OAuth2
```
https://your-app.railway.app/auth/google/login/callback/
http://localhost:8000/auth/google/login/callback/   (local dev)
```

### GitHub OAuth2
```
https://your-app.railway.app/auth/github/login/callback/
```

## Flow

1. User runs `/subscribe` in Telegram
2. Bot calls `create_checkout_url(tg_user)` — requires verified email
3. User taps inline button → Paddle hosted checkout page
4. Payment succeeds → Paddle sends `subscription.activated` webhook
5. `handle_paddle_event()` upgrades user to Pro in DB
6. Bot sends Telegram confirmation message

## Important: Email requirement

`get_or_create_paddle_customer()` raises `NeedsRegistration` if the
TelegramUser has no verified email. This is intentional — Paddle always
receives a real, verified email address for every paying customer.

The `/subscribe` command handles `NeedsRegistration` by sending the
registration link instead.

## Sandbox testing

Use Paddle's test card: `4242 4242 4242 4242`, any future expiry, any CVV.

Reference: https://developer.paddle.com/concepts/payment/sandbox
