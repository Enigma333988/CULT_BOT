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

setupBridges();
