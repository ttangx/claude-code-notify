import json

from pywebpush import webpush, WebPushException

from server.config import VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIM_EMAIL
from server import store


def send_push_to_all(title: str, body: str, data: dict | None = None):
    """Send a push notification to all subscribed clients."""
    payload = json.dumps({
        "title": title,
        "body": body,
        "data": data or {},
    })

    vapid_claims = {"sub": VAPID_CLAIM_EMAIL}
    subscriptions = store.get_subscriptions()
    failed_endpoints = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=vapid_claims,
            )
        except WebPushException as e:
            print(f"Push failed for {sub.get('endpoint', '?')[:60]}: {e}")
            # 410 Gone or 404 means subscription expired
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (404, 410):
                failed_endpoints.append(sub.get("endpoint"))
        except Exception as e:
            print(f"Unexpected push error: {e}")

    # Clean up expired subscriptions
    for endpoint in failed_endpoints:
        store.remove_subscription(endpoint)

    return len(subscriptions) - len(failed_endpoints)
