const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
const maxApp = window.WebApp || null;
const vkBridge = window.vkBridge || null;

if (tg) {
  try {
    tg.ready();
    tg.expand();
  } catch (error) {
    console.error("Telegram bridge init failed", error);
  }
}

if (maxApp && typeof maxApp.ready === "function") {
  try {
    maxApp.ready();
  } catch (error) {
    console.error("MAX bridge init failed", error);
  }
}

if (vkBridge && typeof vkBridge.send === "function") {
  vkBridge.send("VKWebAppInit").catch((error) => {
    console.error("VK bridge init failed", error);
  });
}

const timelineItems = [
  {
    title: "Заказ создан.",
    description: "",
    state: "done",
  },
  {
    title: "Ожидают подтверждения.",
    description: "Проверьте детали, оферту и сумму к оплате.",
    state: "done",
  },
  {
    title: "В очередь.",
    description: "Заказ подтвержден и поставлен в работу, скоро приступим к выполнению.",
    state: "done",
  },
  {
    title: "В работу.",
    description: "Мы работаем над вашим заказом.",
    state: "pending",
  },
  {
    title: "На проверке.",
    description: "Проверьте результат и подтвердите, что все устраивает.",
    state: "pending",
  },
  {
    title: "Упаковка / готовность.",
    description: "Заказ упакован и ожидает выдачи.",
    state: "pending",
  },
  {
    title: "В пути.",
    description: "Заказ в пути.",
    state: "pending",
  },
  {
    title: "Завершение заказа.",
    description: "Заказ завершен. Спасибо за покупку!",
    state: "pending",
  },
];

function renderTimeline(items) {
  return items
    .map((item, index) => {
      const isLast = index === items.length - 1;
      return `
        <li class="timeline-item timeline-item--${item.state}">
          <div class="timeline-marker${isLast ? " timeline-marker--last" : ""}">
            <span class="timeline-dot"></span>
          </div>
          <div class="timeline-copy">
            <h3>${item.title}</h3>
            ${item.description ? `<p>${item.description}</p>` : ""}
          </div>
        </li>
      `;
    })
    .join("");
}

function renderApp() {
  const root = document.getElementById("app");
  if (!root) {
    return;
  }

  root.innerHTML = `
    <main class="screen">
      <section class="hero" aria-label="КУЛЬТ мебель">
        <div class="hero__pattern" aria-hidden="true"></div>
        <div class="hero__logo">
          <span class="hero__brand">КУЛЬТ</span>
          <span class="hero__subbrand">мебель</span>
        </div>
      </section>

      <section class="order-card">
        <div class="order-card__media">
          <img src="./mockups/cat-crop.png" alt="Фото товара" class="order-card__image">
          <p class="order-card__caption">ФОТО ВРЕМЕННО ОТСУТСТВУЕТ</p>
        </div>

        <p class="order-card__number">Номер заказа: <strong>#4</strong></p>

        <div class="order-card__summary">
          <h1>Кровать для мамы 160×200</h1>
          <p>Примечание: тут всякая инфа или конфигурация или иные изменения</p>
        </div>

        <div class="order-card__price">
          <span class="order-card__price-label">Цена:</span>
          <span class="order-card__price-old">64 600 ₽</span>
          <span class="order-card__price-current">59 600 ₽</span>
        </div>

        <p class="order-card__payment">Оплачено: 50% (24 200 ₽ из 48 400 ₽)</p>

        <button class="pay-button" type="button">Оплатить</button>

        <p class="order-card__agreement">
          Оплата подтверждает согласие
          <a href="#" aria-label="Ознакомиться с офертой">с офертой.</a>
        </p>

        <section class="status-card" aria-labelledby="status-title">
          <h2 id="status-title">Статус в очереди (3/8)</h2>
          <ol class="timeline">
            ${renderTimeline(timelineItems)}
          </ol>
        </section>
      </section>
    </main>
  `;
}

function initMockupPreview() {
  const root = document.querySelector(".screen");
  if (!root) {
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const explicitMockup = params.get("mockup");
  const candidates = explicitMockup
    ? [`./mockups/${explicitMockup}`]
    : [
        "./mockups/current.png",
        "./mockups/current.jpg",
        "./mockups/current.jpeg",
        "./mockups/current.webp",
      ];

  const overlay = document.createElement("img");
  overlay.className = "mockup-overlay";
  overlay.alt = "";
  overlay.setAttribute("aria-hidden", "true");

  const controls = document.createElement("button");
  controls.className = "mockup-toggle";
  controls.type = "button";
  controls.textContent = "Hide mockup";

  controls.addEventListener("click", () => {
    overlay.classList.toggle("mockup-overlay--hidden");
    controls.textContent = overlay.classList.contains("mockup-overlay--hidden")
      ? "Show mockup"
      : "Hide mockup";
  });

  const tryLoad = (index = 0) => {
    if (index >= candidates.length) {
      return;
    }

    overlay.onload = () => {
      root.appendChild(overlay);
      root.appendChild(controls);
    };

    overlay.onerror = () => {
      tryLoad(index + 1);
    };

    overlay.src = candidates[index];
  };

  tryLoad();
}

renderApp();
initMockupPreview();
