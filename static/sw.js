self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(clients.claim());
});

self.addEventListener("push", (e) => {
  let data = { title: "Claude Code", body: "" };
  try {
    data = e.data.json();
  } catch {
    data.body = e.data?.text() || "";
  }

  const pushData = data.data || {};
  const options = {
    body: data.body,
    icon: "/static/icon-192.svg",
    badge: "/static/icon-192.svg",
    vibrate: [200, 100, 200],
    data: pushData,
    tag: "claude-code-" + (pushData.event_type || "notify"),
    renotify: true,
  };

  // Add action buttons for actionable notifications (permission prompts)
  if (pushData.actionable) {
    options.actions = [
      { action: "approve", title: "Approve" },
      { action: "reject", title: "Reject" },
    ];
    // Keep notification visible until user interacts
    options.requireInteraction = true;
  }

  e.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener("notificationclick", (e) => {
  const pushData = e.notification.data || {};
  const action = e.action; // "approve", "reject", or "" (body click)
  e.notification.close();

  if (action && pushData.notification_id) {
    // Handle action button click — send response to server
    e.waitUntil(
      fetch("/api/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          notification_id: pushData.notification_id,
          action: action,
        }),
      })
        .then((r) => {
          if (!r.ok) return r.json().then((d) => Promise.reject(d));
          // Show confirmation
          return self.registration.showNotification("Claude Code", {
            body: action === "approve" ? "Approved" : "Rejected",
            icon: "/static/icon-192.svg",
            tag: "claude-code-response",
            silent: true,
          });
        })
        .catch((err) => {
          console.error("Respond failed:", err);
          return self.registration.showNotification("Claude Code", {
            body: "Failed to send response: " + (err.detail || err.message || "unknown error"),
            icon: "/static/icon-192.svg",
            tag: "claude-code-response",
          });
        })
    );
  } else {
    // Body click — open or focus the PWA
    e.waitUntil(
      clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
        for (const client of list) {
          if (client.url.includes("/") && "focus" in client) {
            return client.focus();
          }
        }
        return clients.openWindow("/");
      })
    );
  }
});
