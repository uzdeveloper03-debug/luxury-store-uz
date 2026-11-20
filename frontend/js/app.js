const API = "/api";

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

async function apiFetch(path, options = {}) {
  if (!tg?.initData) {
    throw new Error("Откройте магазин через Telegram");
  }

  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `tma ${tg.initData}`);

  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Ошибка API: ${response.status}`);
  }

  return response;
}

async function loadCategories() {
  const container = document.getElementById("categories");

  try {
    const response = await fetch(`${API}/categories`);
    if (!response.ok) throw new Error("API error");

    const categories = await response.json();
    container.innerHTML = "";

    categories
      .filter(item => item.slug === "sneakers" || item.slug === "classic")
      .forEach(item => {
        const button = document.createElement("button");
        button.className = "category-item";
        button.textContent = item.name_ru;
        button.onclick = () => showCategoryProducts(item.id);
        container.appendChild(button);
      });
  } catch (error) {
    container.textContent = "Не удалось загрузить категории";
  }
}

let productSearchTimer = null;
let productSearchRequest = 0;

async function loadProducts(categoryId = null, searchQuery = "") {
  const container = document.getElementById("products");
  const requestId = ++productSearchRequest;
  container.innerHTML = '<p class="muted">Загрузка товаров...</p>';

  try {
    const params = new URLSearchParams();
    if (categoryId) params.set("category_id", categoryId);
    if (searchQuery.trim()) params.set("q", searchQuery.trim());

    const queryString = params.toString();
    const url = queryString
      ? `${API}/products?${queryString}`
      : `${API}/products`;

    const response = await fetch(url);
    if (!response.ok) throw new Error("API error");

    const result = await response.json();
    if (requestId !== productSearchRequest) return;

    const products = result.items || [];
    container.innerHTML = "";

    if (!products.length) {
      container.textContent = searchQuery.trim()
        ? "Ничего не найдено"
        : "Пока товаров нет. Скоро добавим новинки.";
      return;
    }

    products.forEach(product => {
      const card = document.createElement("article");
      card.className = "product-card";

      const image = document.createElement("img");
      image.src = product.images?.[0] || "";
      image.alt = product.name;

      const info = document.createElement("div");
      info.className = "product-info";

      const name = document.createElement("h3");
      name.textContent = product.name;

      const price = document.createElement("p");
      price.className = "product-price";
      price.textContent = `${Number(product.price).toLocaleString("ru-RU")} сум`;

      info.append(name, price);
      card.append(image, info);
      card.style.cursor = "pointer";
      card.onclick = () => openProduct(product);
      container.appendChild(card);
    });
  } catch (error) {
    if (requestId === productSearchRequest) {
      container.textContent = "Не удалось загрузить товары";
    }
  }
}

function initProductSearch() {
  const input = document.getElementById("product-search-input");
  const clearButton = document.getElementById("product-search-clear");

  if (!input || !clearButton) return;

  input.addEventListener("input", () => {
    clearTimeout(productSearchTimer);
    const query = input.value.trim();

    productSearchTimer = setTimeout(() => {
      loadProducts(null, query);
    }, 350);
  });

  clearButton.addEventListener("click", () => {
    clearTimeout(productSearchTimer);
    input.value = "";
    loadProducts();
    input.focus();
  });
}

function setActivePage(page) {
  document.querySelectorAll(".bottom-nav button").forEach(button => {
    button.classList.toggle("active", button.dataset.page === page);
  });
}

function showHome() {
  document.querySelector(".hero").hidden = false;
  document.querySelector(".categories").hidden = true;
  document.querySelector(".products").hidden = true;
  document.getElementById("user-view").hidden = true;
  setActivePage("home");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showCategories() {
  document.querySelector(".hero").hidden = true;
  document.querySelector(".categories").hidden = false;
  document.querySelector(".products").hidden = true;
  document.getElementById("user-view").hidden = true;
  setActivePage("catalog");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showCatalog() {
  document.querySelector(".hero").hidden = true;
  document.querySelector(".categories").hidden = true;
  document.querySelector(".products").hidden = false;
  document.getElementById("user-view").hidden = true;
  setActivePage("catalog");
  window.scrollTo({ top: 0, behavior: "smooth" });
  loadProducts();
}

function showCategoryProducts(categoryId) {
  document.querySelector(".hero").hidden = true;
  document.querySelector(".categories").hidden = true;
  document.querySelector(".products").hidden = false;
  document.getElementById("user-view").hidden = true;
  setActivePage("catalog");
  window.scrollTo({ top: 0, behavior: "smooth" });
  loadProducts(categoryId);
}

async function showProfile() {
  const view = document.getElementById("user-view");

  document.querySelector(".hero").hidden = true;
  document.querySelector(".categories").hidden = true;
  document.querySelector(".products").hidden = true;

  view.hidden = false;
  view.innerHTML = '<h2>МОЙ ПРОФИЛЬ</h2><p class="muted">Загрузка...</p>';

  setActivePage("profile");
  window.scrollTo({ top: 0 });

  try {
    const [profileResponse, ordersResponse] = await Promise.all([
      apiFetch("/me"),
      apiFetch("/orders/my")
    ]);

    const profile = await profileResponse.json();
    const orders = await ordersResponse.json();

    renderProfile(profile, orders);
  } catch (error) {
    view.innerHTML = `<h2>МОЙ ПРОФИЛЬ</h2><p class="user-empty">${escapeHTML(error.message)}</p>`;
  }
}

function renderProfile(profile, orders) {
  const view = document.getElementById("user-view");

  const telegramUser = tg?.initDataUnsafe?.user || {};
  const photoUrl = typeof telegramUser.photo_url === "string"
    && telegramUser.photo_url.startsWith("https://")
      ? escapeHTML(telegramUser.photo_url)
      : "";

  const firstName = profile.first_name || "Покупатель";
  const username = profile.username
    ? "@" + profile.username
    : "Username не указан";

  const avatar = photoUrl
    ? `<img class="profile-avatar" src="${photoUrl}" alt="Аватар пользователя">`
    : `<div class="profile-avatar-fallback">${escapeHTML(firstName.charAt(0).toUpperCase())}</div>`;

  const orderCards = orders.length
    ? orders.map(order => `
        <article class="profile-order-card">
          <div class="profile-order-top">
            <h3>ЗАКАЗ №${order.id}</h3>
            <span class="profile-order-status">${escapeHTML(order.status)}</span>
          </div>
          <p class="profile-order-date">
            ${new Date(order.created_at).toLocaleString("ru-RU")}
          </p>
          <div class="profile-order-products">
            ${order.items.map(item => `
              <p>${escapeHTML(item.product_name)} — ${escapeHTML(item.size)}, ${item.quantity} шт.</p>
            `).join("")}
          </div>
          <div class="profile-order-total">
            <span>Итого</span>
            <strong>${Number(order.total).toLocaleString("ru-RU")} сум</strong>
          </div>
        </article>
      `).join("")
    : '<div class="profile-no-orders">У вас пока нет заказов</div>';

  view.innerHTML = `
    <h2 class="profile-page-title">МОЙ ПРОФИЛЬ</h2>

    <section class="profile-card">
      <div class="profile-avatar-wrap">
        ${avatar}
      </div>

      <h3 class="profile-name">${escapeHTML(firstName)}</h3>
      <p class="profile-username">${escapeHTML(username)}</p>

      <div class="profile-id">
        <span>TELEGRAM ID</span>
        <strong>${escapeHTML(String(profile.telegram_id))}</strong>
      </div>

      <div class="profile-divider"></div>

      <div class="profile-details">
        <div>
          <span>Дата регистрации</span>
          <strong>${new Date(profile.created_at).toLocaleDateString("ru-RU")}</strong>
        </div>
        <div>
          <span>Язык магазина</span>
          <strong>${profile.language === "uz" ? "O‘zbekcha" : "Русский"}</strong>
        </div>
      </div>

      <div class="profile-language">
        <p>ЯЗЫК ИНТЕРФЕЙСА</p>
        <div>
          <button onclick="changeLanguage('ru')">РУССКИЙ</button>
          <button onclick="changeLanguage('uz')">O‘ZBEKCHA</button>
        </div>
      </div>
    </section>

    <section class="profile-orders-section">
      <div class="profile-section-heading">
        <h2>МОИ ЗАКАЗЫ</h2>
        <span>${orders.length}</span>
      </div>
      <div class="cart-list">${orderCards}</div>
    </section>
  `;
}

async function changeLanguage(language) {
  try {
    await apiFetch("/me/language", {
      method: "PUT",
      body: JSON.stringify({ language })
    });
    await showProfile();
  } catch (error) {
    alert(error.message);
  }
}

async function showCart() {
  const view = document.getElementById("user-view");

  document.querySelector(".hero").hidden = true;
  document.querySelector(".categories").hidden = true;
  document.querySelector(".products").hidden = true;
  view.hidden = false;
  view.innerHTML = '<h2>КОРЗИНА</h2><p class="muted">Загрузка корзины...</p>';
  setActivePage("cart");
  window.scrollTo({ top: 0 });

  try {
    const response = await apiFetch("/cart");
    const items = await response.json();
    renderCart(items);
  } catch (error) {
    view.innerHTML = `<h2>КОРЗИНА</h2><p class="user-empty">${escapeHTML(error.message)}</p>`;
  }
}

function renderCart(items) {
  const view = document.getElementById("user-view");

  if (!items.length) {
    view.innerHTML = '<h2>КОРЗИНА</h2><p class="user-empty">Ваша корзина пока пуста</p>';
    return;
  }

  let total = 0;

  const cards = items.map(item => {
    const product = item.product;
    const price = Number(product.price) || 0;
    total += price * item.quantity;

    const image = product.images?.[0] || "";

    return `
      <article class="cart-item">
        <img src="${escapeHTML(image)}" alt="${escapeHTML(product.name)}">
        <div class="cart-item-info">
          <h3>${escapeHTML(product.name)}</h3>
          <p>Размер: ${escapeHTML(item.size)}</p>
          <p>${price.toLocaleString("ru-RU")} сум</p>
          <div class="cart-controls">
            <button onclick="changeCartQuantity(${item.id}, ${item.quantity - 1})"
              ${item.quantity <= 1 ? "disabled" : ""}>−</button>
            <span>${item.quantity}</span>
            <button onclick="changeCartQuantity(${item.id}, ${item.quantity + 1})"
              ${item.quantity >= Math.min(item.available, 10) ? "disabled" : ""}>+</button>
          </div>
          <button class="cart-remove" onclick="removeCartItem(${item.id})">УДАЛИТЬ</button>
        </div>
      </article>
    `;
  }).join("");

  view.innerHTML = `
    <h2>КОРЗИНА</h2>
    <div class="cart-list">${cards}</div>
    <div class="cart-total">
      <span>ИТОГО</span>
      <span>${total.toLocaleString("ru-RU")} сум</span>
    </div>
  `;
}

async function changeCartQuantity(itemId, quantity) {
  try {
    await apiFetch(`/cart/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ quantity })
    });
    await showCart();
  } catch (error) {
    alert(error.message);
  }
}

async function removeCartItem(itemId) {
  try {
    await apiFetch(`/cart/${itemId}`, {
      method: "DELETE"
    });
    await showCart();
  } catch (error) {
    alert(error.message);
  }
}

async function initCinematicShowcase() {
  const image = document.getElementById("cinematic-image");
  const counter = document.getElementById("cinematic-counter");

  if (!image || !counter) return;

  try {
    const response = await fetch(`${API}/products`);
    if (!response.ok) return;

    const result = await response.json();
    const products = result.items || [];

    const photos = products.flatMap(product =>
      (product.images || []).map(src => ({
        src,
        name: product.name
      }))
    );

    if (!photos.length) return;

    let current = 0;

    function showPhoto(index, animate = false) {
      const photo = photos[index];

      const reveal = () => {
        image.classList.remove("is-changing");
        image.classList.add("is-visible");
        counter.textContent =
          `LUXURY / ${String(index + 1).padStart(2, "0")}`;
      };

      if (animate) {
        image.classList.remove("is-visible");
        image.classList.add("is-changing");

        setTimeout(() => {
          image.onload = reveal;
          image.onerror = () => {
            image.classList.remove("is-changing");
          };
          image.src = photo.src;
        }, 700);
      } else {
        image.onload = reveal;
        image.onerror = () => {
          image.classList.remove("is-changing");
        };
        image.src = photo.src;
      }
    }

    showPhoto(current);

    if (photos.length > 1) {
      setInterval(() => {
        current = (current + 1) % photos.length;
        showPhoto(current, true);
      }, 6500);
    }
  } catch (error) {
    console.error("Cinematic showcase:", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  showHome();
  initCinematicShowcase();
  initProductSearch();
});


let selectedSizeId = null;
let selectedProductId = null;
let isFavorite = false;

function openProduct(product) {
  selectedProductId = Number(product.id);
  let modal = document.getElementById("product-modal");

  if (!modal) {
    modal = document.createElement("div");
    modal.id = "product-modal";
    modal.className = "product-modal";
    document.body.appendChild(modal);
  }

  selectedSizeId = null;

  const sizes = product.sizes || [];
  const images = (product.images || []).filter(Boolean);
  const galleryImages = images.length ? images : [""];

  modal.innerHTML = `
    <div class="product-detail">
      <button class="detail-close" onclick="document.getElementById('product-modal').style.display='none'">✕</button>
      <div class="detail-gallery" id="detail-gallery">
        ${galleryImages.map((src, index) => `
          <img class="detail-image" src="${escapeHTML(src)}" alt=""
               data-gallery-index="${index}">
        `).join("")}
      </div>
      <div class="detail-dots" id="detail-dots">
        ${galleryImages.length > 1 ? galleryImages.map((_, index) => `
          <button class="detail-dot${index === 0 ? " active" : ""}"
                  data-gallery-index="${index}"
                  aria-label="Фото ${index + 1}"></button>
        `).join("") : ""}
      </div>
      <h2>${escapeHTML(product.name)}</h2>
      <p class="detail-price">${Number(product.price).toLocaleString("ru-RU")} сум</p>
      <p class="detail-description">${escapeHTML(product.description_ru || "")}</p>
      <h3>ВЫБЕРИТЕ РАЗМЕР</h3>
      <div class="detail-sizes">
        ${sizes.map(size => `
          <button class="size-option"
            ${size.available <= 0 ? "disabled" : ""}
            onclick="selectProductSize(this, ${Number(size.id)})">${escapeHTML(size.size)}</button>
        `).join("")}
      </div>
      <p id="selected-size">Размер не выбран</p>
      <button class="hero-button" onclick="addToCart()">В КОРЗИНУ</button>
      <p id="cart-message"></p>
    </div>
  `;

  const gallery = modal.querySelector("#detail-gallery");
  const dots = [...modal.querySelectorAll(".detail-dot")];

  if (gallery && dots.length) {
    const slides = [...gallery.querySelectorAll(".detail-image")];

    function goToSlide(index) {
      index = Math.max(0, Math.min(index, slides.length - 1));
      const galleryLeft = gallery.getBoundingClientRect().left;
      const slideLeft = slides[index].getBoundingClientRect().left;

      gallery.scrollTo({
        left: gallery.scrollLeft + slideLeft - galleryLeft,
        behavior: "smooth"
      });

      dots.forEach((dot, i) => {
        dot.classList.toggle("active", i === index);
      });
    }

    gallery.addEventListener("scroll", () => {
      const galleryLeft = gallery.getBoundingClientRect().left;
      let active = 0;
      let distance = Infinity;

      slides.forEach((slide, i) => {
        const d = Math.abs(slide.getBoundingClientRect().left - galleryLeft);
        if (d < distance) {
          distance = d;
          active = i;
        }
      });

      dots.forEach((dot, i) => {
        dot.classList.toggle("active", i === active);
      });
    }, { passive: true });

    dots.forEach(dot => {
      dot.addEventListener("click", () => {
        goToSlide(Number(dot.dataset.galleryIndex));
      });
    });

    let touchStartX = 0;

    gallery.addEventListener("touchstart", event => {
      touchStartX = event.changedTouches[0].screenX;
    }, { passive: true });

    gallery.addEventListener("touchend", event => {
      const delta = event.changedTouches[0].screenX - touchStartX;

      if (Math.abs(delta) < 40) return;

      const galleryLeft = gallery.getBoundingClientRect().left;
      let current = 0;
      let distance = Infinity;

      slides.forEach((slide, i) => {
        const d = Math.abs(slide.getBoundingClientRect().left - galleryLeft);
        if (d < distance) {
          distance = d;
          current = i;
        }
      });

      goToSlide(current + (delta < 0 ? 1 : -1));
    }, { passive: true });
  }

  modal.style.display = "block";
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;",
    '"': "&quot;", "'": "&#39;"
  }[char]));
}

function selectProductSize(button, sizeId) {
  document.querySelectorAll(".size-option").forEach(item =>
    item.classList.remove("selected")
  );

  button.classList.add("selected");
  selectedSizeId = sizeId;

  document.getElementById("selected-size").textContent =
    "Выбран размер: " + button.textContent;
}

async function addToCart() {
  const message = document.getElementById("cart-message");

  if (!selectedSizeId) {
    message.textContent = "Сначала выберите размер";
    return;
  }

  try {
    await apiFetch("/cart", {
      method: "POST",
      body: JSON.stringify({
        size_id: selectedSizeId,
        quantity: 1
      })
    });

    message.textContent = "Товар добавлен в корзину";
  } catch (error) {
    message.textContent = error.message;
  }
}
