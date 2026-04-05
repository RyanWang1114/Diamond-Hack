(function () {
  const FLOW_KEY = "atlasLaneFlowV2";
  const SESSION_KEY = "atlasLaneSessionIdV1";
  const API_BASE_KEY = "atlasLaneApiBaseV1";
  const REQUEST_TIMEOUT_MS = 15000;
  const API_BASE = detectApiBase();

  function defaultFlowState() {
    return {
      sessionId: ensureSessionId(),
      searchWindow: null,
      trip: null,
      suggestions: [],
      acceptedSuggestionNames: [],
      planPayload: null,
      selectedDetail: null,
      memorySnapshot: null,
      georgeMessages: [],
      georgePackingList: [],
    };
  }

  function readFlowState() {
    try {
      const raw = localStorage.getItem(FLOW_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return {
        ...defaultFlowState(),
        ...parsed,
        sessionId: ensureSessionId(),
        acceptedSuggestionNames: Array.isArray(parsed.acceptedSuggestionNames) ? parsed.acceptedSuggestionNames : [],
        suggestions: Array.isArray(parsed.suggestions) ? parsed.suggestions : [],
        georgeMessages: Array.isArray(parsed.georgeMessages) ? parsed.georgeMessages : [],
        georgePackingList: Array.isArray(parsed.georgePackingList) ? parsed.georgePackingList : [],
      };
    } catch (error) {
      return defaultFlowState();
    }
  }

  function writeFlowState(nextState) {
    localStorage.setItem(FLOW_KEY, JSON.stringify(nextState));
    return nextState;
  }

  function updateFlowState(updater) {
    const current = readFlowState();
    const next = typeof updater === "function" ? updater(current) : { ...current, ...updater };
    return writeFlowState(next);
  }

  function ensureSessionId() {
    const existing = localStorage.getItem(SESSION_KEY);
    if (existing) {
      return existing;
    }
    const generated =
      "atlas-" + Math.random().toString(36).slice(2, 10) + "-" + Date.now().toString(36);
    localStorage.setItem(SESSION_KEY, generated);
    return generated;
  }

  async function apiPost(path, payload) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(apiUrl(path), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        signal: controller.signal,
        body: JSON.stringify({
          sessionId: ensureSessionId(),
          ...payload,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Request failed for ${path}`);
      }

      return response.json();
    } catch (error) {
      if (error && error.name === "AbortError") {
        throw new Error("The backend took too long to respond. Please try again.");
      }
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function detectApiBase() {
    const stored = window.localStorage.getItem(API_BASE_KEY);
    const explicit = typeof window.ATLAS_LANE_API_BASE === "string" ? window.ATLAS_LANE_API_BASE : stored;
    if (explicit && explicit.trim()) {
      return explicit.trim().replace(/\/+$/, "");
    }
    if (window.location.protocol === "file:") {
      return "http://127.0.0.1:8000";
    }
    return "";
  }

  function apiUrl(path) {
    return API_BASE ? `${API_BASE}${path}` : path;
  }

  async function bootstrapMemory() {
    try {
      const data = await apiPost("/api/bootstrap", {});
      if (data.memorySnapshot) {
        updateFlowState((state) => ({
          ...state,
          memorySnapshot: data.memorySnapshot,
        }));
      }
      return data;
    } catch (error) {
      return null;
    }
  }

  async function recordFeedback(eventType, entityValue, delta = 1, extra = {}) {
    try {
      const data = await apiPost("/api/feedback", {
        eventType,
        entityValue,
        delta,
        ...extra,
      });
      if (data.memorySnapshot) {
        updateFlowState((state) => ({ ...state, memorySnapshot: data.memorySnapshot }));
      }
      return data;
    } catch (error) {
      return null;
    }
  }

  async function flagPlatform(platform, reason) {
    const data = await apiPost("/api/platform/flag", { platform, reason });
    if (data.memorySnapshot) {
      updateFlowState((state) => ({ ...state, memorySnapshot: data.memorySnapshot }));
    }
    return data;
  }

  function setSelectedDetail(detail) {
    updateFlowState((state) => ({
      ...state,
      selectedDetail: detail,
    }));
  }

  function readSelectedDetail() {
    return readFlowState().selectedDetail;
  }

  function clearFlowResults() {
    updateFlowState((state) => ({
      ...state,
      suggestions: [],
      acceptedSuggestionNames: [],
      planPayload: null,
      selectedDetail: null,
    }));
  }

  function resetWholeFlow() {
    const fresh = defaultFlowState();
    writeFlowState(fresh);
    return fresh;
  }

  function startFreshSearchFlow() {
    const current = readFlowState();
    const next = {
      ...defaultFlowState(),
      sessionId: current.sessionId,
      memorySnapshot: current.memorySnapshot,
      georgeMessages: [
        {
          role: "assistant",
          content: "I’m George. I can answer simple questions, explain trip results, and help with packing without changing the page.",
          timestamp: timestampLabel(),
        },
      ],
      georgePackingList: [],
    };
    writeFlowState(next);
    return next;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatCurrency(value) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(Number(value || 0));
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(`${value}T12:00:00`));
  }

  function slugify(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function unique(values) {
    return Array.from(new Set(values.filter(Boolean)));
  }

  function createForecastSeries(basePrice, seed) {
    const rng = createRng(`${seed}:detail`);
    const history = [];
    let price = Math.max(15, basePrice * (0.9 + rng() * 0.08));
    for (let day = -20; day <= 0; day += 1) {
      price = Math.max(15, price * (1 + (rng() - 0.45) * 0.08));
      history.push({
        day,
        price: Math.round(price),
      });
    }
    const returns = history.slice(1).map((point, index) => Math.log(point.price / history[index].price));
    const drift = average(returns);
    const volatility = Math.max(0.01, standardDeviation(returns));
    const lastPrice = history[history.length - 1].price;
    const projected = [];
    for (let day = 1; day <= 7; day += 1) {
      const simulations = [];
      for (let simulation = 0; simulation < 140; simulation += 1) {
        const localRng = createRng(`${seed}:${day}:${simulation}`);
        const move = drift + (localRng() - 0.5) * volatility * 2;
        simulations.push(Math.max(15, lastPrice * Math.exp(move * day)));
      }
      simulations.sort((a, b) => a - b);
      projected.push({
        day,
        mean: Math.round(average(simulations)),
        low: Math.round(percentile(simulations, 0.1)),
        high: Math.round(percentile(simulations, 0.9)),
      });
    }
    const lastProjection = projected[projected.length - 1];
    const trend =
      lastProjection.mean > lastPrice + 8 ? "up" : lastProjection.mean < lastPrice - 8 ? "down" : "flat";
    const confidence = Math.max(
      52,
      Math.min(89, Math.round(100 - ((lastProjection.high - lastProjection.low) / Math.max(lastProjection.mean, 1)) * 100))
    );
    return {
      history,
      forecast: {
        projected,
        trend,
        confidence,
      },
    };
  }

  function drawForecastChart(canvas, history, forecast) {
    const ctx = canvas.getContext("2d");
    if (!ctx || !Array.isArray(history) || !history.length || !Array.isArray(forecast) || !forecast.length) {
      return;
    }
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const allValues = history.map((point) => point.price).concat(forecast.map((point) => point.low).concat(forecast.map((point) => point.high)));
    const minPrice = Math.min(...allValues) - 10;
    const maxPrice = Math.max(...allValues) + 10;
    const chartLeft = 34;
    const chartTop = 18;
    const chartRight = width - 18;
    const chartBottom = height - 28;
    const chartWidth = chartRight - chartLeft;
    const chartHeight = chartBottom - chartTop;

    ctx.strokeStyle = "rgba(17, 107, 114, 0.14)";
    ctx.lineWidth = 1;
    for (let i = 0; i < 4; i += 1) {
      const y = chartTop + (chartHeight / 3) * i;
      ctx.beginPath();
      ctx.moveTo(chartLeft, y);
      ctx.lineTo(chartRight, y);
      ctx.stroke();
    }

    const fullSeries = history.concat(forecast.map((point) => ({ price: point.mean })));
    const xForIndex = (index) => chartLeft + (chartWidth / Math.max(fullSeries.length - 1, 1)) * index;
    const yForPrice = (price) => chartBottom - ((price - minPrice) / Math.max(maxPrice - minPrice, 1)) * chartHeight;

    ctx.fillStyle = "rgba(217, 110, 66, 0.14)";
    ctx.beginPath();
    forecast.forEach((point, index) => {
      const x = xForIndex(index + history.length - 1);
      const y = yForPrice(point.high);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    for (let index = forecast.length - 1; index >= 0; index -= 1) {
      const point = forecast[index];
      const x = xForIndex(index + history.length - 1);
      const y = yForPrice(point.low);
      ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "#116b72";
    ctx.lineWidth = 3;
    ctx.beginPath();
    history.forEach((point, index) => {
      const x = xForIndex(index);
      const y = yForPrice(point.price);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();

    ctx.strokeStyle = "#d96e42";
    ctx.setLineDash([8, 7]);
    ctx.beginPath();
    forecast.forEach((point, index) => {
      const x = xForIndex(index + history.length - 1);
      const y = yForPrice(point.mean);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = "#21323c";
    ctx.font = '12px "Avenir Next", sans-serif';
    ctx.fillText("History", chartLeft, height - 8);
    ctx.fillStyle = "#d96e42";
    ctx.fillText("7-day forecast", chartLeft + 68, height - 8);
  }

  function createRng(seedString) {
    let seed = hashCode(seedString);
    return function () {
      seed |= 0;
      seed = (seed + 0x6d2b79f5) | 0;
      let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashCode(value) {
    let hash = 0;
    for (let index = 0; index < String(value).length; index += 1) {
      hash = (hash << 5) - hash + String(value).charCodeAt(index);
      hash |= 0;
    }
    return hash;
  }

  function average(values) {
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  }

  function standardDeviation(values) {
    if (!values.length) {
      return 0;
    }
    const mean = average(values);
    return Math.sqrt(average(values.map((value) => Math.pow(value - mean, 2))));
  }

  function percentile(values, amount) {
    const index = Math.max(0, Math.min(values.length - 1, Math.floor(values.length * amount)));
    return values[index];
  }

  function bindGeorge(contextProvider) {
    const toggle = document.getElementById("georgeToggle");
    const panel = document.getElementById("georgePanel");
    if (!toggle || !panel) {
      return;
    }

    const close = document.getElementById("closeGeorge");
    const messages = document.getElementById("georgeMessages");
    const form = document.getElementById("georgeForm");
    const input = document.getElementById("georgeInput");
    const packingPanel = document.getElementById("packingListPanel");
    const packingItems = document.getElementById("packingListItems");
    const chips = Array.from(document.querySelectorAll(".chip-button"));

    const flow = readFlowState();
    if (!flow.georgeMessages.length) {
      flow.georgeMessages = [
        {
          role: "assistant",
          content: "I’m George. I can explain plans, unpack pricing, answer simple questions, and build packing lists even if your message has a typo.",
          timestamp: timestampLabel(),
        },
      ];
      writeFlowState(flow);
    }

    renderGeorgeMessages();
    renderGeorgePacking();

    toggle.addEventListener("click", () => {
      panel.classList.toggle("hidden");
    });

    if (close) {
      close.addEventListener("click", () => {
        panel.classList.add("hidden");
      });
    }

    chips.forEach((chip) => {
      chip.addEventListener("click", async () => {
        const prompt = chip.dataset.prompt;
        if (!prompt) {
          return;
        }
        await submitGeorgePrompt(prompt);
      });
    });

    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const prompt = input.value.trim();
        if (!prompt) {
          return;
        }
        input.value = "";
        await submitGeorgePrompt(prompt);
      });
    }

    if (packingItems) {
      packingItems.addEventListener("change", async (event) => {
        const checkbox = event.target;
        if (!(checkbox instanceof HTMLInputElement)) {
          return;
        }
        const item = checkbox.dataset.item;
        if (!item) {
          return;
        }
        await recordFeedback("packing_item", item, checkbox.checked ? 1 : -1, {
          checked: checkbox.checked,
        });
      });
    }

    async function submitGeorgePrompt(prompt) {
      pushGeorgeMessage("user", prompt);
      try {
        const context = typeof contextProvider === "function" ? contextProvider() : {};
        const flowState = readFlowState();
        const data = await apiPost("/api/george/chat", context ? { prompt, conversation: flowState.georgeMessages.slice(-8), ...context } : { prompt, conversation: flowState.georgeMessages.slice(-8) });
        pushGeorgeMessage("assistant", decorateGeorgeResponse(data));
        if (Array.isArray(data.packingList)) {
          updateFlowState((state) => ({
            ...state,
            georgePackingList: data.packingList,
            memorySnapshot: data.memorySnapshot || state.memorySnapshot,
          }));
          renderGeorgePacking();
        }
      } catch (error) {
        pushGeorgeMessage(
          "assistant",
          readErrorMessage(error, "I couldn’t reach the backend right now, but I can still help once the local server is running.")
        );
      }
    }

    function pushGeorgeMessage(role, content) {
      updateFlowState((state) => ({
        ...state,
        georgeMessages: state.georgeMessages.concat({
          role,
          content,
          timestamp: timestampLabel(),
        }).slice(-14),
      }));
      renderGeorgeMessages();
    }

    function renderGeorgeMessages() {
      const flowState = readFlowState();
      messages.innerHTML = flowState.georgeMessages
        .map(
          (message) => `
            <div class="message ${message.role}">
              <div class="message-meta">${message.role === "assistant" ? "George" : "You"} · ${escapeHtml(message.timestamp)}</div>
              <div>${escapeHtml(message.content)}</div>
            </div>
          `
        )
        .join("");
      messages.scrollTop = messages.scrollHeight;
    }

    function renderGeorgePacking() {
      const flowState = readFlowState();
      const items = flowState.georgePackingList || [];
      if (!packingPanel || !packingItems) {
        return;
      }
      if (!items.length) {
        packingPanel.classList.add("hidden");
        return;
      }
      packingPanel.classList.remove("hidden");
      const memory = flowState.memorySnapshot || {};
      const packingMemory = (memory.profile && memory.profile.packingItems) || {};
      packingItems.innerHTML = items
        .map(
          (item) => `
            <div class="packing-item">
              <label>
                <input type="checkbox" data-item="${escapeHtml(item.name)}" ${packingMemory[item.name] > 0 ? "checked" : ""} />
                <strong>${escapeHtml(item.name)}</strong>
              </label>
              <p class="summary-note">${escapeHtml(item.detail)}</p>
            </div>
          `
        )
        .join("");
    }
  }

  function decorateGeorgeResponse(data) {
    if (!data || !data.message) {
      return "I’m here to help with the route, results, and simple questions.";
    }
    if (!Array.isArray(data.sources) || !data.sources.length) {
      return data.message;
    }
    const labels = data.sources
      .slice(0, 2)
      .map((source) => source.label || source.title || source.url)
      .filter(Boolean);
    return labels.length ? `${data.message} Sources: ${labels.join(", ")}.` : data.message;
  }

  function timestampLabel() {
    return new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function readErrorMessage(error, fallback = "Something went wrong.") {
    if (error && typeof error.message === "string" && error.message.trim()) {
      return error.message.trim();
    }
    return fallback;
  }

  window.AtlasLane = {
    apiPost,
    bindGeorge,
    bootstrapMemory,
    clearFlowResults,
    createForecastSeries,
    drawForecastChart,
    escapeHtml,
    flagPlatform,
    formatCurrency,
    formatDate,
    readFlowState,
    readSelectedDetail,
    readErrorMessage,
    recordFeedback,
    resetWholeFlow,
    startFreshSearchFlow,
    setSelectedDetail,
    slugify,
    unique,
    updateFlowState,
    writeFlowState,
    apiBase: API_BASE,
  };
})();
