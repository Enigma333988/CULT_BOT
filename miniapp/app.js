function loadScript(src, timeoutMs) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === "1") {
        resolve();
        return;
      }
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
      return;
    }

    const script = document.createElement("script");
    const timeoutId = window.setTimeout(() => {
      reject(new Error(`Timeout while loading ${src}`));
    }, timeoutMs || 6000);

    script.src = src;
    script.async = true;
    script.onload = () => {
      window.clearTimeout(timeoutId);
      script.dataset.loaded = "1";
      resolve();
    };
    script.onerror = () => {
      window.clearTimeout(timeoutId);
      reject(new Error(`Failed to load ${src}`));
    };
    document.head.appendChild(script);
  });
}

function applyClientClasses() {
  const root = document.documentElement;
  if (!root) {
    return;
  }

  const ua = (navigator.userAgent || "").toLowerCase();
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const platform = tg && typeof tg.platform === "string" ? tg.platform.toLowerCase() : "";
  const isDesktopPlatform =
    platform === "tdesktop" ||
    platform === "macos" ||
    platform === "web" ||
    platform === "weba" ||
    platform === "webk";
  const isAyuGram = ua.includes("ayugram");

  if (isDesktopPlatform || isAyuGram) {
    root.classList.add("client-desktop");
  }
}

function initTelegramBridge() {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (!tg) {
    return false;
  }
  try {
    if (typeof tg.ready === "function") {
      tg.ready();
    }
    if (typeof tg.expand === "function") {
      tg.expand();
    }
    applyClientClasses();
    return true;
  } catch (error) {
    console.error("Telegram bridge init failed", error);
    return false;
  }
}

function initMaxBridge() {
  const maxApp = window.WebApp || null;
  if (!maxApp || typeof maxApp.ready !== "function") {
    return false;
  }
  try {
    maxApp.ready();
    return true;
  } catch (error) {
    console.error("MAX bridge init failed", error);
    return false;
  }
}

function initVkBridge() {
  const vkBridge = window.vkBridge || null;
  if (!vkBridge || typeof vkBridge.send !== "function") {
    return false;
  }
  try {
    const result = vkBridge.send("VKWebAppInit");
    if (result && typeof result.catch === "function") {
      result.catch((error) => {
        console.error("VK bridge init failed", error);
      });
    }
    return true;
  } catch (error) {
    console.error("VK bridge init failed", error);
    return false;
  }
}

function setupBridges() {
  applyClientClasses();

  if (!initTelegramBridge()) {
    loadScript("https://telegram.org/js/telegram-web-app.js", 6000)
      .then(() => {
        initTelegramBridge();
      })
      .catch((error) => {
        console.warn(error.message);
      });
  }

  if (!initMaxBridge()) {
    loadScript("https://st.max.ru/js/max-web-app.js", 6000)
      .then(() => {
        initMaxBridge();
      })
      .catch((error) => {
        console.warn(error.message);
      });
  }

  if (!initVkBridge()) {
    loadScript("./vendor/vk-bridge.browser.min.js", 4000)
      .then(() => {
        initVkBridge();
      })
      .catch(() => {
        loadScript("https://unpkg.com/@vkontakte/vk-bridge/dist/browser.min.js", 6000)
          .then(() => {
            initVkBridge();
          })
          .catch((error) => {
            console.warn(error.message);
          });
      });
  }
}

function getTextNodeRootById(id) {
  if (!id) {
    return null;
  }
  return document.getElementById(id);
}

function setTextNodeById(id, text) {
  const root = getTextNodeRootById(id);
  if (!root) {
    return;
  }
  const firstTextNode = root.querySelector("span.text-node");
  if (firstTextNode) {
    firstTextNode.textContent = text;
    return;
  }
  root.textContent = text;
}

function setOrderNumber(value) {
  const numberEl = document.querySelector('[data-role="order-number-value"]');
  if (!numberEl) {
    return;
  }
  numberEl.textContent = value;
}

function parseOrderToken() {
  const params = new URLSearchParams(window.location.search || "");
  const directKeys = ["token", "order_token", "orderToken", "start", "startapp"];
  for (const key of directKeys) {
    const raw = (params.get(key) || "").trim();
    if (raw) {
      return raw.startsWith("order_") ? raw.slice("order_".length) : raw;
    }
  }

  const hash = (window.location.hash || "").replace(/^#/, "");
  if (hash) {
    const hashParams = new URLSearchParams(hash);
    for (const key of directKeys) {
      const raw = (hashParams.get(key) || "").trim();
      if (raw) {
        return raw.startsWith("order_") ? raw.slice("order_".length) : raw;
      }
    }
  }

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const startParam = tg && tg.initDataUnsafe ? (tg.initDataUnsafe.start_param || "").trim() : "";
  if (startParam) {
    return startParam.startsWith("order_") ? startParam.slice("order_".length) : startParam;
  }
  return "";
}

function formatRuble(value) {
  const safe = Number.isFinite(value) ? value : 0;
  return `${safe.toLocaleString("ru-RU")} ₽`;
}

function updateProgressVisuals(order) {
  const stepRaw = Number(order && order.status_step);
  const step = Number.isFinite(stepRaw) && stepRaw > 0 ? Math.min(8, Math.floor(stepRaw)) : 1;

  const circleSelectors = [
    ".ellipse-1-975c7346ec97",
    ".ellipse-2-2138379dd673",
    ".ellipse-3-4428dfc8698d",
    ".ellipse-7-3b4e9d6dbcc5",
    ".ellipse-6-eccfbdf53466",
    ".ellipse-5-5fdd1c1756f4",
    ".ellipse-4-7d500bdf3c7c",
    ".ellipse-8-feb3e007e6ba",
  ];
  const lineSelectors = [
    ".rectangle-a2f924893031",
    ".rectangle-ac86f3d42c1e",
    ".rectangle-d9b370d1bb61",
    ".rectangle-bc24cd728766",
    ".rectangle-57ab4c732da1",
    ".rectangle-0e3f93f2bc2e",
    ".rectangle-fa30a91b2ec9",
  ];
  const checkSelectors = [
    ".vector-f2181409f6e5",
    ".vector-bd69ec772748",
    ".vector-efa119933166",
  ];

  circleSelectors.forEach((selector, index) => {
    const el = document.querySelector(selector);
    if (!el) {
      return;
    }
    const doneOrActive = index < step;
    el.style.background = doneOrActive ? "#ff6c36" : "transparent";
    el.style.borderColor = doneOrActive ? "transparent" : "#ffae91";
  });

  lineSelectors.forEach((selector, index) => {
    const el = document.querySelector(selector);
    if (!el) {
      return;
    }
    const done = index < step - 1;
    el.style.background = done ? "#ff6c36" : "#ffae91";
  });

  const doneChecks = Math.max(0, step - 1);
  checkSelectors.forEach((selector, index) => {
    const el = document.querySelector(selector);
    if (!el) {
      return;
    }
    el.style.opacity = index < doneChecks ? "1" : "0";
  });
}

function applyOrder(order) {
  const idLabel = order && order.id ? `#${order.id}` : "#—";
  setOrderNumber(idLabel);

  setTextNodeById("html-text-node-ea135164-4082-520f-b13f-e0d95688b827", order.title || "Заказ");
  setTextNodeById(
    "html-text-node-2511a009-e158-54fb-92da-2ee21763201b",
    `Примечание: ${order.notes && order.notes.trim() ? order.notes : "Без примечания"}`
  );

  setTextNodeById("html-text-node-8947bb6d-34bb-5b86-8431-1ea02b231ed7", `Цена: ${order.total_price_label || "—"}`);

  const due = Math.max(0, Number(order.total_price || 0) - Number(order.paid_amount || 0));
  setTextNodeById("html-text-node-689a0d6f-ece5-5dde-a06d-5e022b5210c0", `К оплате: ${formatRuble(due)}`);
  setTextNodeById("html-text-node-556c4119-ad6a-5d6b-b00f-c3cfd96ee3ea", `Оплачено: ${order.paid_text || "0%"}`);

  const customerLabel = order.customer_status_label || order.status_label || "Статус";
  const customerStep = Number(order.customer_status_step || 1);
  const customerTotal = Number(order.customer_status_total_steps || 1);
  setTextNodeById(
    "html-text-node-a925aaf5-6d2c-53bc-909d-fad0c2f94262",
    `${customerLabel} (${customerStep}/${customerTotal})`
  );
  setTextNodeById(
    "html-text-node-f4184536-902f-5cb3-99ce-6cb363c3d526",
    order.customer_status_description || "Статус обновляется автоматически."
  );

  updateProgressVisuals(order);
}

function showOrderError(text) {
  setTextNodeById("html-text-node-a925aaf5-6d2c-53bc-909d-fad0c2f94262", "Заказ не найден");
  setTextNodeById("html-text-node-f4184536-902f-5cb3-99ce-6cb363c3d526", text || "Проверьте ссылку на заказ.");
}

async function loadOrderData() {
  const token = parseOrderToken();
  if (!token) {
    showOrderError("Не передан токен заказа.");
    return;
  }

  try {
    const byPath = await fetch(`/api/order/${encodeURIComponent(token)}`, { method: "GET" });
    let payload = null;
    if (byPath.ok) {
      payload = await byPath.json();
    } else {
      const byQuery = await fetch(`/api/order?token=${encodeURIComponent(token)}`, { method: "GET" });
      payload = await byQuery.json();
    }

    if (!payload || !payload.ok || !payload.order) {
      showOrderError("Заказ не найден или недоступен.");
      return;
    }

    applyOrder(payload.order);
  } catch (error) {
    console.error("Failed to load order", error);
    showOrderError("Ошибка загрузки заказа.");
  }
}

setupBridges();
loadOrderData();
