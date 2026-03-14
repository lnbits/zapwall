# Zapwall

`zapwall` is an LNbits extension for selling paywalled content to Nostr users.

It combines:

- LNbits wallets and invoice handling
- Nostr identity and distribution
- DM-delivered unlock links
- signed entitlement receipts

## MVP flow

1. A creator configures a Nostr pubkey and relay list in Zapwall.
2. The creator creates a paywalled item with preview text, full content, price, and unlock mode.
3. Zapwall generates or publishes a preview note with machine-readable tags.
4. A buyer either zaps the preview note or uses the invoice fallback on the public page.
5. Zapwall verifies the payment, records the purchase, creates a receipt, and optionally sends a Nostr DM with an unlock link.
6. The buyer opens `/zapwall/unlock/{token}` to view the unlocked content.

## Included pieces

- Creator dashboard and item/settings pages in LNbits
- Public preview and unlock pages
- JSON API for items, invoice fallback, purchase status, entitlement, and zap notifications
- Relay listener for zap receipts using the same relay set configured in `nostrclient`
- Signed purchase receipts for portable entitlement checks

## Current scope

This version focuses on:

- paid text / image / file items
- invoice fallback
- Nostr preview note generation
- Nostr DM unlock delivery
- one-time permanent unlocks per buyer pubkey and item

More advanced flows like subscriptions, split payments, and richer media hosting can be layered on top later.
