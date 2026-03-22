const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
const maxApp = window.WebApp || null;
const vkBridge = window.vkBridge || null;

if (tg) {
  try {
    tg.ready();
    tg.expand();
  } catch (error) {
    console.error('Telegram bridge init failed', error);
  }
}

if (maxApp && typeof maxApp.ready === 'function') {
  try {
    maxApp.ready();
  } catch (error) {
    console.error('MAX bridge init failed', error);
  }
}

if (vkBridge && typeof vkBridge.send === 'function') {
  vkBridge.send('VKWebAppInit').catch((error) => {
    console.error('VK bridge init failed', error);
  });
}
