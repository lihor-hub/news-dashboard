# Sharing articles

Share interesting articles with other users on your News Dashboard instance
using the built-in **Sharing** feature. Sharing is authenticated and
in-app: you pick a recipient by username, and the article shows up directly
in their **Shared** inbox — there's no public link or token involved.

## How sharing works

When you share an article:
1. The system creates a share record linking you (the sender), the
   recipient, and the article
2. The recipient sees it appear in their **Shared → Received** tab
3. The recipient can read the article, leave messages back and forth with
   you, and see any highlights you attached to the share
4. You can revoke the share at any time from your **Shared → Sent** tab

Sharing is **not** forwarding the article text or URL — it grants the
recipient access to the article within the app, scoped to that specific
share (this matters for private-source articles the recipient wouldn't
otherwise be able to see).

## Sharing from the article view

To share an article you're viewing:

1. Open the article
2. Use the **Share** action in the article view
3. In the share dialog:
   - Pick the recipient from the list of other users on your instance
   - Optionally add a note explaining why you're sharing
   - Send the share
4. The recipient gets a push notification (if enabled) and sees the share in
   their **Shared** inbox

## Receiving shares

When someone shares an article with you:
- It appears under **Shared → Received**, with an unread indicator until you
  open it
- You'll see who shared it, their note (if any), any highlighted passages,
  and an AI-generated note on why it's relevant to you
- Opening the share view marks it read and clears the unread badge
- You can reply in the share's message thread — this is a two-way
  conversation between you and the sender, not a public comment section

## Sent shares and revoking

Under **Shared → Sent**, you can see every article you've sent to other
users:
- Recipient username, when it was sent, and whether they've read it yet
- **Revoke** removes the recipient's access — a revoked share disappears
  from their received list and no longer counts toward their unread total,
  and they can no longer open the shared article or its detail view
- Revoking does not delete the record: it still appears in your own Sent
  history, marked **Revoked**, so you keep a full audit trail of what you
  sent

## Privacy

Sharing respects the app's privacy model:
- No article content leaves your server
- The recipient does not see your personal triage state, notes, or reading
  history — only the article, your note, and anything you explicitly
  highlighted for that share
- Access to a shared article is scoped to the share itself: it doesn't
  change what the recipient can see anywhere else in the app, and revoking
  the share removes that access

## Requirements

Sharing requires:
- A multi-user instance with at least one other account to share with
- No additional configuration needed — sharing is enabled by default

## Troubleshooting

If sharing doesn't work:
- **"Recipient user not found"**: the recipient's account may have been
  removed; refresh the recipient list and try again
- **A shared article returns "not found"**: the sender may have revoked the
  share, or you're not the sender or recipient of that share
- No push notifications?: check your notification settings (bell icon →
  Settings)

Sharing works the same whether you're on desktop, tablet, or mobile.
