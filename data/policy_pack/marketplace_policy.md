# Marketplace policy pack

The rules GigBid must follow when it writes anything a client will see. Each rule has an **id** that matches the
machine-checked rule in `agent/config.yaml` (`compliance.rules`, `liaison`, `risk`), so the human-readable policy
and what the Compliance Guard enforces cannot drift apart (`tests/unit/test_policy_pack.py` checks this).

Paraphrased from common freelance-marketplace terms of service (communication, payments, fees and honest
representation). It is not legal text; check the real platform's current terms before using GigBid on a live account.

## Rules enforced on every proposal and reply (Compliance Guard)

| Id | Rule | Action |
|---|---|---|
| `contact_email` | Do not share an email address before a contract starts | Remove the sentence |
| `contact_phone` | Do not share a phone number | Remove the sentence |
| `external_link` | No external links, except a GitHub profile or repository as work samples | Remove the sentence |
| `off_platform_contact` | Do not ask to move the conversation to WhatsApp, Telegram, Skype, WeChat or similar | Remove the sentence |
| `off_platform_payment` | Do not offer or accept payment outside the platform (PayPal, bank transfer, crypto, ...) | Remove the sentence |
| `guarantee` | Do not guarantee results ("100% success", "risk-free", "guaranteed") | Remove the sentence |
| `below_floor` | Never quote a price below the freelancer's minimum rate (replies) | Remove the sentence |

If more than `block_if_removed_more_than` sentences are removed, the whole draft is **blocked** and needs a human.

## Rules enforced before bidding (Risk Assessor)

| Id | Signal | Effect |
|---|---|---|
| `unpaid_work` | Unpaid "test tasks" or free trials | Scam flag: skip |
| `off_platform_contact` | Job asks to be contacted off the platform | Scam flag: skip |
| `payment_or_identity_request` | Asks for bank details, ID documents, crypto or gift cards | Scam flag: skip |
| `prompt_injection` | Text that tries to instruct an AI assistant | Flag; the writer is warned to ignore it |

## Rules for client messages (Client Liaison)

- Scam signals (off-platform contact or payment, personal contact details, ID or bank details, instructions to the
  assistant) get a fixed, safe reply that keeps everything on the platform. No LLM writes it.
- Every reply waits for the freelancer's approval. Nothing is sent automatically.

## Changing the policy (the "platform policy update" change request)

1. Edit the rule in `agent/config.yaml` (pattern, action, or a new rule with a new id).
2. Add or update the row in this file with the same id.
3. Run `python -m pytest tests/unit/test_policy_pack.py tests/integration -q` and the smoke evaluation.

No Python code changes are needed for a new remove/flag rule.
