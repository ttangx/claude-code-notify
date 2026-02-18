let swRegistration = null;
let isSubscribed = false;

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const subscribeBtn = document.getElementById("subscribe-btn");
const testBtn = document.getElementById("test-btn");
const notificationList = document.getElementById("notification-list");
const iosInstructions = document.getElementById("ios-instructions");

async function init() {
  // Check iOS standalone
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const isStandalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;

  if (isIOS && !isStandalone) {
    iosInstructions.style.display = "block";
  }

  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    setStatus("error", "Push notifications not supported in this browser");
    subscribeBtn.disabled = true;
    return;
  }

  try {
    swRegistration = await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
    console.log("Service worker registered");
  } catch (err) {
    setStatus("error", "Service worker registration failed");
    console.error(err);
    return;
  }

  // Check current subscription
  const sub = await swRegistration.pushManager.getSubscription();
  isSubscribed = !!sub;
  updateUI();
  loadNotifications();
}

function setStatus(state, text) {
  statusDot.className = "status-dot " + state;
  statusText.textContent = text;
}

function updateUI() {
  if (isSubscribed) {
    setStatus("active", "Subscribed — notifications enabled");
    subscribeBtn.textContent = "Unsubscribe";
    subscribeBtn.className = "danger";
    testBtn.style.display = "block";
  } else {
    setStatus("", "Not subscribed");
    subscribeBtn.textContent = "Enable Notifications";
    subscribeBtn.className = "primary";
    testBtn.style.display = "none";
  }
}

async function toggleSubscription() {
  subscribeBtn.disabled = true;
  try {
    if (isSubscribed) {
      await unsubscribe();
    } else {
      await subscribe();
    }
  } catch (err) {
    console.error("Subscription toggle failed:", err);
    setStatus("error", "Failed: " + err.message);
  }
  subscribeBtn.disabled = false;
}

async function subscribe() {
  const resp = await fetch("/api/vapid-public-key");
  const { publicKey } = await resp.json();

  const applicationServerKey = urlBase64ToUint8Array(publicKey);
  const sub = await swRegistration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey,
  });

  await fetch("/api/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sub.toJSON()),
  });

  isSubscribed = true;
  updateUI();
}

async function unsubscribe() {
  const sub = await swRegistration.pushManager.getSubscription();
  if (sub) {
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    await fetch("/api/unsubscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint }),
    });
  }
  isSubscribed = false;
  updateUI();
}

async function sendTestNotification() {
  testBtn.disabled = true;
  try {
    const resp = await fetch("/api/test-notify", { method: "POST" });
    if (!resp.ok) throw new Error("Test failed");
  } catch (err) {
    console.error("Test notification failed:", err);
  }
  testBtn.disabled = false;
}

async function respondToNotification(nid, action, btnEl) {
  btnEl.disabled = true;
  // Disable sibling buttons too
  const row = btnEl.closest(".action-row");
  if (row) row.querySelectorAll("button").forEach((b) => (b.disabled = true));

  try {
    const resp = await fetch("/api/respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notification_id: nid, action }),
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.detail || "Failed");

    // Update the row to show result
    if (row) {
      row.innerHTML = `<span class="responded">${action === "approve" ? "Approved" : "Rejected"}</span>`;
    }
  } catch (err) {
    console.error("Respond failed:", err);
    if (row) {
      row.innerHTML = `<span class="respond-error">Error: ${escapeHtml(err.message)}</span>`;
    }
  }
}

async function sendTextResponse(nid, formEl) {
  const input = formEl.querySelector("input");
  const text = input.value.trim();
  if (!text) return;

  const btns = formEl.querySelectorAll("button");
  btns.forEach((b) => (b.disabled = true));
  input.disabled = true;

  try {
    const resp = await fetch("/api/respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notification_id: nid, action: "text", text }),
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.detail || "Failed");
    formEl.innerHTML = `<span class="responded">Sent: ${escapeHtml(text)}</span>`;
  } catch (err) {
    console.error("Text respond failed:", err);
    formEl.innerHTML = `<span class="respond-error">Error: ${escapeHtml(err.message)}</span>`;
  }
}

async function loadNotifications() {
  try {
    const resp = await fetch("/api/notifications");
    const notifications = await resp.json();
    renderNotifications(notifications);
  } catch (err) {
    console.error("Failed to load notifications:", err);
  }
}

function renderNotifications(notifications) {
  if (!notifications.length) {
    notificationList.innerHTML = '<li class="empty">No notifications yet</li>';
    return;
  }

  notificationList.innerHTML = notifications
    .map((n) => {
      const time = new Date(n.timestamp * 1000).toLocaleString();
      const canAct = n.tmux_pane && !n.responded;
      const isPermission = n.event_type === "Notification";

      let actionsHtml = "";
      if (n.responded) {
        actionsHtml = `<div class="action-row"><span class="responded">${escapeHtml(n.responded)}</span></div>`;
      } else if (canAct && isPermission) {
        actionsHtml = `
        <div class="action-row">
          <button class="btn-approve" onclick="respondToNotification('${n.id}', 'approve', this)">Approve</button>
          <button class="btn-reject" onclick="respondToNotification('${n.id}', 'reject', this)">Reject</button>
        </div>`;
      } else if (canAct) {
        actionsHtml = `
        <form class="text-row" onsubmit="event.preventDefault(); sendTextResponse('${n.id}', this)">
          <input type="text" placeholder="Send text to Claude..." class="text-input">
          <button type="submit" class="btn-send">Send</button>
        </form>`;
      }

      return `
      <li class="notification-item">
        <div class="notification-title">${escapeHtml(n.title)}</div>
        <div class="notification-body">${escapeHtml(n.message)}</div>
        <div class="notification-time">${escapeHtml(time)}</div>
        ${actionsHtml}
      </li>
    `;
    })
    .join("");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

subscribeBtn.addEventListener("click", toggleSubscription);
testBtn.addEventListener("click", sendTestNotification);

// Poll for new notifications every 30s
setInterval(loadNotifications, 30000);

init();
