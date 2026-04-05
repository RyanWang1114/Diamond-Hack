(function () {
  const atlas = window.AtlasLane;
  const root = document.getElementById("itemDetailRoot");
  if (!root) {
    return;
  }

  atlas.bootstrapMemory();
  atlas.bindGeorge(() => {
    const flow = atlas.readFlowState();
    return {
      trip: flow.trip,
      plans: flow.planPayload ? flow.planPayload.plans || [] : [],
      legs: flow.planPayload ? flow.planPayload.legs || [] : [],
    };
  });

  const detail = atlas.readSelectedDetail();
  if (!detail) {
    window.location.href = "./results.html";
    return;
  }

  document.getElementById("detailTitle").textContent = detail.title;
  document.getElementById("detailSubtitle").textContent = detail.subtitle;

  root.innerHTML = `
    <section class="panel stage-panel">
      <div class="detail-topline">
        <div>
          <p class="eyebrow">${atlas.escapeHtml(detail.type)}</p>
          <h2>${atlas.escapeHtml(detail.title)}</h2>
          <p class="summary-note">${atlas.escapeHtml(detail.subtitle)}</p>
        </div>
        <div class="quick-prompts">
          <span class="status-pill">${atlas.formatCurrency(detail.price)}</span>
          <span class="status-pill">${atlas.escapeHtml(detail.provider)}</span>
        </div>
      </div>

      ${
        detail.imageUrl
          ? `
            <div class="map-image-wrap">
              <img src="${detail.imageUrl}" alt="${atlas.escapeHtml(detail.title)} map" class="city-map-image" loading="lazy" />
            </div>
          `
          : ""
      }

      <div class="detail-grid">
        ${Object.entries(detail.body || {})
          .map(
            ([label, value]) => `
              <div class="cost-cell">
                <span class="summary-note">${atlas.escapeHtml(humanize(label))}</span>
                <strong>${atlas.escapeHtml(value)}</strong>
              </div>
            `
          )
          .join("")}
      </div>

      <div class="link-row">
        ${
          detail.primaryLink
            ? `<a class="deep-link" href="${detail.primaryLink}" target="_blank" rel="noreferrer">Open booking or ticket link</a>`
            : `<span class="summary-note">Live purchase link unavailable for this item right now.</span>`
        }
        <button class="ghost-button" type="button" id="backButton">Back</button>
      </div>
    </section>

    <section class="panel stage-panel">
      <div class="transport-topline">
        <div>
          <p class="eyebrow">Price outlook</p>
          <h2>7-day mathematical estimate</h2>
        </div>
        <div class="quick-prompts">
          <span class="metric-badge ${detail.trend === "up" ? "alert" : detail.trend === "down" ? "good" : "warn"}">${atlas.escapeHtml(detail.trend)}</span>
          <span class="tag">${detail.confidence}% confidence</span>
        </div>
      </div>
      <canvas id="detailForecastChart" class="forecast-chart" width="880" height="240"></canvas>
      <p class="summary-note">Estimate built from a stochastic Monte Carlo-style simulation over seeded historical price movement, shown with a 10th-90th percentile confidence band.</p>
    </section>

    ${
      Array.isArray(detail.offers) && detail.offers.filter((offer) => offer && offer.url).length
        ? `
          <section class="panel stage-panel">
            <div class="section-heading compact">
              <div>
                <p class="eyebrow">Offer list</p>
                <h2>Trusted and direct price options</h2>
              </div>
            </div>
            <div class="result-list">
              ${detail.offers
                .filter((offer) => offer && offer.url)
                .map(
                  (offer) => `
                    <a class="result-link result-link-anchor" href="${offer.url}" target="_blank" rel="noreferrer">
                      <div>
                        <strong>${atlas.escapeHtml(offer.platform)}</strong>
                        <p class="summary-note">Open booking search or merchant page</p>
                      </div>
                      <div class="result-link-meta">
                        <strong>${atlas.formatCurrency(offer.price)}</strong>
                      </div>
                    </a>
                  `
                )
                .join("")}
            </div>
          </section>
        `
        : ""
    }
  `;

  const canvas = document.getElementById("detailForecastChart");
  atlas.drawForecastChart(canvas, detail.history || [], detail.forecast || []);

  document.getElementById("backButton").addEventListener("click", () => {
    window.history.back();
  });

  function humanize(value) {
    return String(value)
      .replace(/([A-Z])/g, " $1")
      .replace(/^./, (character) => character.toUpperCase());
  }
})();
