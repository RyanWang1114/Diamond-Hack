(function () {
  const atlas = window.AtlasLane;
  const root = document.getElementById("resultsRoot");
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

  const complianceModal = document.getElementById("complianceModal");
  const complianceContent = document.getElementById("complianceContent");
  const closeCompliance = document.getElementById("closeCompliance");
  const refreshButton = document.getElementById("refreshResultsButton");
  const suggestionCards = document.getElementById("suggestionCards");
  const status = document.getElementById("resultsStatus");

  if (closeCompliance) {
    closeCompliance.addEventListener("click", () => complianceModal.classList.add("hidden"));
  }
  if (complianceModal) {
    complianceModal.addEventListener("click", (event) => {
      if (event.target.dataset.closeModal) {
        complianceModal.classList.add("hidden");
      }
    });
  }

  if (refreshButton) {
    refreshButton.addEventListener("click", refreshResults);
  }

  if (suggestionCards) {
    suggestionCards.addEventListener("click", async (event) => {
      const suggestionButton = event.target.closest("button[data-suggestion-name]");
      if (!suggestionButton) {
        return;
      }
      const cityName = suggestionButton.dataset.suggestionName;
      const action = suggestionButton.dataset.action;
      toggleSuggestion(cityName, action);
      render();
    });
  }

  root.addEventListener("click", async (event) => {
    const suggestionButton = event.target.closest("button[data-suggestion-name]");
    if (suggestionButton) {
      const cityName = suggestionButton.dataset.suggestionName;
      const action = suggestionButton.dataset.action;
      toggleSuggestion(cityName, action);
      render();
      return;
    }

    const detailButton = event.target.closest("button[data-open-detail]");
    if (detailButton) {
      openDetailFromDataset(detailButton.dataset);
      return;
    }

    const complianceButton = event.target.closest("button[data-open-compliance]");
    if (complianceButton) {
      await openCompliance(complianceButton.dataset.planId);
      return;
    }

    const flagButton = event.target.closest("button[data-flag-platform]");
    if (flagButton) {
      const platform = flagButton.dataset.flagPlatform;
      if (platform) {
        await atlas.flagPlatform(platform, "User marked as suspicious");
        status.textContent = `${platform} is now excluded from future results.`;
        await refreshResults();
      }
    }
  });

  render();

  async function refreshResults() {
    const flow = atlas.readFlowState();
    if (!flow.trip) {
      window.location.href = "./trip-details.html";
      return;
    }
    status.textContent = "Refreshing plans...";
    try {
      const data = await atlas.apiPost("/api/plan", {
        trip: flow.trip,
        acceptedSuggestions: flow.acceptedSuggestionNames,
      });
      atlas.updateFlowState((state) => ({
        ...state,
        trip: data.trip || state.trip,
        planPayload: data,
        memorySnapshot: data.memorySnapshot || state.memorySnapshot,
      }));
      status.textContent = "Results refreshed.";
      render();
    } catch (error) {
      status.textContent = atlas.readErrorMessage(
        error,
        "Could not refresh results. Make sure the backend is running."
      );
    }
  }

  async function openCompliance(planId) {
    const flow = atlas.readFlowState();
    const plan = (flow.planPayload && flow.planPayload.plans || []).find((item) => item.id === planId);
    if (!plan) {
      return;
    }
    complianceModal.classList.remove("hidden");
    complianceContent.innerHTML = `
      <div class="compliance-card">
        <h3>Refreshing restrictions</h3>
        <p class="summary-note">Checking destination and transport guidance...</p>
      </div>
    `;
    try {
      const data = await atlas.apiPost("/api/compliance", {
        cities: plan.cities.map((city) => ({
          name: city.name,
          country: city.profile.country,
          geography: city.profile.geography,
        })),
        transportModes: collectTransportModes(plan),
      });
      complianceContent.innerHTML = renderCompliance(plan, data);
    } catch (error) {
      complianceContent.innerHTML = `
        <div class="compliance-card">
          <h3>Restrictions unavailable</h3>
          <p class="summary-note">${atlas.escapeHtml(
            atlas.readErrorMessage(error, "The compliance service did not respond right now.")
          )}</p>
        </div>
      `;
    }
  }

  function toggleSuggestion(cityName, action) {
    atlas.updateFlowState((state) => {
      const accepted = new Set(state.acceptedSuggestionNames || []);
      if (action === "accept") {
        accepted.add(cityName);
        atlas.recordFeedback("city_add", cityName, 1, { cityName });
      }
      if (action === "decline") {
        accepted.delete(cityName);
        atlas.recordFeedback("city_skip", cityName, 1, { cityName });
      }
      return {
        ...state,
        acceptedSuggestionNames: Array.from(accepted),
        suggestions: (state.suggestions || []).map((suggestion) =>
          suggestion.name === cityName
            ? {
                ...suggestion,
                declined: action === "decline",
              }
            : suggestion
        ),
      };
    });
  }

  function render() {
    const flow = atlas.readFlowState();
    if (!flow.trip || !flow.planPayload) {
      window.location.href = "./trip-details.html";
      return;
    }

    const trip = flow.trip;
    const plans = flow.planPayload.plans || [];
    const acceptedNames = new Set(flow.acceptedSuggestionNames || []);
    document.getElementById("resultsRouteSummary").innerHTML = `
      <div class="summary-card">
        <h3>Search results for ${atlas.escapeHtml(trip.origin)}</h3>
        <p class="summary-note">${atlas.formatDate(trip.startDate)} to ${atlas.formatDate(trip.endDate)} · ${trip.tripDays} day${trip.tripDays === 1 ? "" : "s"} · ${atlas.escapeHtml(trip.transportPriority)}</p>
      </div>
    `;

    document.getElementById("suggestionCards").innerHTML = (flow.suggestions || []).length
      ? flow.suggestions
          .map((suggestion) => {
            const accepted = acceptedNames.has(suggestion.name);
            return `
              <article class="suggestion-card">
                <div class="transport-topline">
                  <h3>${atlas.escapeHtml(suggestion.name)}</h3>
                  <span class="metric-badge ${accepted ? "good" : suggestion.declined ? "alert" : "warn"}">
                    ${accepted ? "Selected" : suggestion.declined ? "Skipped" : "Optional"}
                  </span>
                </div>
                <p class="summary-note">${atlas.escapeHtml(suggestion.reason)}</p>
                <div class="quick-prompts">
                  ${(suggestion.matchingTags || []).map((tag) => `<span class="tag">${atlas.escapeHtml(tag)}</span>`).join("")}
                </div>
                <div class="plan-actions">
                  <button class="ghost-button" type="button" data-action="accept" data-suggestion-name="${atlas.escapeHtml(suggestion.name)}">Use this city</button>
                  <button class="ghost-button" type="button" data-action="decline" data-suggestion-name="${atlas.escapeHtml(suggestion.name)}">Skip</button>
                </div>
              </article>
            `;
          })
          .join("")
      : `<div class="summary-card"><h3>No extra city suggestions</h3><p class="summary-note">This route is already fairly direct.</p></div>`;

    root.innerHTML = plans.map(renderPlanCard).join("");
    document.querySelectorAll("canvas[data-forecast-detail]").forEach((canvas) => {
      const plan = plans.find((item) => item.id === canvas.dataset.planId);
      if (!plan) {
        return;
      }
      const leg = plan.legs[Number(canvas.dataset.legIndex)];
      if (!leg) {
        return;
      }
      atlas.drawForecastChart(canvas, leg.history, leg.forecast.projected);
    });
  }

  function renderPlanCard(plan) {
    return `
      <article class="plan-card">
        <div class="plan-topline">
          <div>
            <h3>${atlas.escapeHtml(plan.name)}</h3>
            <p class="summary-note">${atlas.escapeHtml(plan.description)}</p>
          </div>
          <div class="quick-prompts">
            <span class="status-pill">${atlas.formatDate(plan.startDate)} to ${atlas.formatDate(plan.endDate)}</span>
            <span class="status-pill">${atlas.formatCurrency(plan.totalCost)} total</span>
          </div>
        </div>

        <div class="cost-grid">
          ${costCell("Flights", plan.costBreakdown.flights)}
          ${costCell("Hotels", plan.costBreakdown.accommodation)}
          ${costCell("Ground", plan.costBreakdown.ground)}
          ${costCell("Tours", plan.costBreakdown.attractions)}
          ${costCell("Meals + buffer", plan.costBreakdown.buffer)}
        </div>

        <details class="accordion" open>
          <summary>Transportation</summary>
          <div class="accordion-body">
            ${plan.legs.map((leg, legIndex) => renderLeg(plan, leg, legIndex)).join("")}
          </div>
        </details>

        <details class="accordion">
          <summary>Hotels</summary>
          <div class="accordion-body">
            ${plan.cities.map((city, cityIndex) => renderHotels(plan, city, cityIndex)).join("")}
          </div>
        </details>

        <details class="accordion">
          <summary>Tour places</summary>
          <div class="accordion-body">
            ${plan.cities.map((city, cityIndex) => renderAttractions(plan, city, cityIndex)).join("")}
          </div>
        </details>

        <div class="plan-actions">
          <button class="primary-button" type="button" data-open-compliance="true" data-plan-id="${plan.id}">Open prohibited items panel</button>
        </div>
      </article>
    `;
  }

  function renderLeg(plan, leg, legIndex) {
    const liveFlightOptions = (leg.flightOptions || [])
      .map((option, sourceIndex) => ({ option, sourceIndex }))
      .filter((entry) => entry.option.bestOffer && entry.option.bestOffer.url);
    return `
      <section class="result-group">
        <div class="result-group-header">
          <div>
            <h4>${atlas.escapeHtml(leg.fromName)} to ${atlas.escapeHtml(leg.toName)}</h4>
            <p class="summary-note">${Math.round(leg.distanceKm)} km · ${atlas.escapeHtml(leg.from.airport)} to ${atlas.escapeHtml(leg.to.airport)}</p>
          </div>
          <span class="tag">${atlas.escapeHtml(leg.forecast.trend)} trend</span>
        </div>
        <div class="result-list">
          ${liveFlightOptions.length
            ? liveFlightOptions
            .map(
              ({ option, sourceIndex }) => `
                <button class="result-link" type="button" data-open-detail="true" data-kind="flight" data-plan-id="${plan.id}" data-leg-index="${legIndex}" data-option-index="${sourceIndex}">
                  <div>
                    <strong>${atlas.escapeHtml(option.airline)}</strong>
                    <p class="summary-note">${atlas.escapeHtml(option.aircraft)} · ${option.durationHours}h · ${option.stops} stop${option.stops === 1 ? "" : "s"} · ${option.checkedAllowance} free checked bag${option.checkedAllowance === 1 ? "" : "s"}</p>
                  </div>
                  <div class="result-link-meta">
                    <strong>${atlas.formatCurrency(option.bestOffer.price)}</strong>
                    <small>${atlas.escapeHtml(option.bestOffer.platform)}</small>
                  </div>
                </button>
              `
            )
            .join("")
            : `<div class="summary-card"><h4>No live flight purchase links</h4><p class="summary-note">The current flight provider key did not return bookable deeplinks for this leg, so Atlas Lane is hiding estimated-only flight options instead of showing fake listings.</p></div>`}
          ${leg.groundOptions
            .map(
              (option, optionIndex) => `
                <button class="result-link" type="button" data-open-detail="true" data-kind="ground" data-plan-id="${plan.id}" data-leg-index="${legIndex}" data-option-index="${optionIndex}">
                  <div>
                    <strong>${atlas.escapeHtml(option.mode[0].toUpperCase() + option.mode.slice(1))}</strong>
                    <p class="summary-note">${option.durationHours}h · ${atlas.escapeHtml(option.operator)} · free baggage depends on operator</p>
                  </div>
                  <div class="result-link-meta">
                    <strong>${atlas.formatCurrency(option.bestOffer.price)}</strong>
                    <small>${atlas.escapeHtml(option.bestOffer.platform)}</small>
                  </div>
                </button>
              `
            )
            .join("")}
        </div>
        <canvas class="forecast-chart compact-chart" width="760" height="180" data-forecast-detail="true" data-plan-id="${plan.id}" data-leg-index="${legIndex}"></canvas>
      </section>
    `;
  }

  function renderHotels(plan, city, cityIndex) {
    return `
      <section class="result-group">
        <div class="result-group-header">
          <div>
            <h4>${atlas.escapeHtml(city.name)}</h4>
            <p class="summary-note">${atlas.formatDate(city.checkIn)} to ${atlas.formatDate(city.checkOut)}</p>
          </div>
        </div>
        ${renderCityLivePanel(city)}
        <div class="result-list">
          ${city.hotels
            .map(
              (hotel, hotelIndex) => `
                <button class="result-link" type="button" data-open-detail="true" data-kind="hotel" data-plan-id="${plan.id}" data-city-index="${cityIndex}" data-item-index="${hotelIndex}">
                  <div>
                    <strong>${atlas.escapeHtml(hotel.name)}</strong>
                    <p class="summary-note">${atlas.escapeHtml(hotel.area)} · ${atlas.formatCurrency(hotel.nightlyRate)}/night · near ${hotel.fits.map(atlas.escapeHtml).join(", ")}${hotel.rating ? ` · ${atlas.escapeHtml(String(hotel.rating))}★` : ""}</p>
                  </div>
                  <div class="result-link-meta">
                    <strong>${atlas.formatCurrency(hotel.totalCost)}</strong>
                    <small>${atlas.escapeHtml(hotel.bestOffer.platform)}</small>
                  </div>
                </button>
              `
            )
            .join("")}
        </div>
      </section>
    `;
  }

  function renderAttractions(plan, city, cityIndex) {
    return `
      <section class="result-group">
        <div class="result-group-header">
          <div>
            <h4>${atlas.escapeHtml(city.name)}</h4>
            <p class="summary-note">${atlas.escapeHtml(city.weather && city.weather.headline ? city.weather.headline : city.profile.climate)}</p>
          </div>
        </div>
        <div class="result-list">
          ${city.attractions
            .map(
              (attraction, attractionIndex) => `
                <button class="result-link" type="button" data-open-detail="true" data-kind="attraction" data-plan-id="${plan.id}" data-city-index="${cityIndex}" data-item-index="${attractionIndex}">
                  <div>
                    <strong>${atlas.escapeHtml(attraction.name)}</strong>
                    <p class="summary-note">${atlas.escapeHtml(attraction.type)} · ${atlas.escapeHtml(attraction.hours)}${attraction.mustSee ? " · must-see" : ""}${attraction.rating ? ` · ${atlas.escapeHtml(String(attraction.rating))}★` : ""}</p>
                  </div>
                  <div class="result-link-meta">
                    <strong>${atlas.formatCurrency(attraction.cost)}</strong>
                    <small>${atlas.escapeHtml(attraction.bestOffer.platform)}</small>
                  </div>
                </button>
              `
            )
            .join("")}
        </div>
      </section>
    `;
  }

  function openDetailFromDataset(dataset) {
    const flow = atlas.readFlowState();
    const plan = (flow.planPayload && flow.planPayload.plans || []).find((item) => item.id === dataset.planId);
    if (!plan) {
      return;
    }

    let detail = null;

    if (dataset.kind === "flight") {
      const leg = plan.legs[Number(dataset.legIndex)];
      const option = leg.flightOptions[Number(dataset.optionIndex)];
      detail = {
        type: "flight",
        title: `${leg.fromName} to ${leg.toName}`,
        subtitle: `${option.airline} · ${option.aircraft}`,
        price: option.bestOffer.price,
        primaryLink: option.bestOffer.url,
        provider: option.bestOffer.platform,
        body: {
          route: `${leg.fromName} to ${leg.toName}`,
          aircraft: option.aircraft,
          airline: option.airline,
          duration: `${option.durationHours} hours`,
          stops: `${option.stops} stop${option.stops === 1 ? "" : "s"}`,
          checkedAllowance: `${option.checkedAllowance} free checked bag${option.checkedAllowance === 1 ? "" : "s"}`,
          carryOn: option.carryOn,
          baggageFee: option.baggageFee ? atlas.formatCurrency(option.baggageFee) : "No extra baggage fee estimated",
        },
        history: leg.history,
        forecast: leg.forecast.projected,
        confidence: leg.forecast.confidence,
        trend: leg.forecast.trend,
        offers: option.offers || [],
      };
    }

    if (dataset.kind === "ground") {
      const leg = plan.legs[Number(dataset.legIndex)];
      const option = leg.groundOptions[Number(dataset.optionIndex)];
      const generated = atlas.createForecastSeries(option.bestOffer.price, `${option.operator}-${leg.id}`);
      detail = {
        type: "ground",
        title: `${leg.fromName} to ${leg.toName}`,
        subtitle: `${option.mode[0].toUpperCase() + option.mode.slice(1)} · ${option.operator}`,
        price: option.bestOffer.price,
        primaryLink: option.bestOffer.url,
        provider: option.bestOffer.platform,
        body: {
          route: `${leg.fromName} to ${leg.toName}`,
          transportType: option.mode,
          operator: option.operator,
          duration: `${option.durationHours} hours`,
          scenic: option.scenic ? "Yes" : "No",
          baggage: "Check operator policy before purchase",
        },
        history: generated.history,
        forecast: generated.forecast.projected,
        confidence: generated.forecast.confidence,
        trend: generated.forecast.trend,
        offers: [],
      };
    }

    if (dataset.kind === "hotel") {
      const city = plan.cities[Number(dataset.cityIndex)];
      const hotel = city.hotels[Number(dataset.itemIndex)];
      const generated = atlas.createForecastSeries(hotel.nightlyRate, `${hotel.name}-${city.name}`);
      detail = {
        type: "hotel",
        title: hotel.name,
        subtitle: `${city.name} · ${hotel.area}`,
        price: hotel.totalCost,
        primaryLink: hotel.bestOffer.url,
        provider: hotel.bestOffer.platform,
        body: {
          city: city.name,
          area: hotel.area,
          nightlyRate: atlas.formatCurrency(hotel.nightlyRate),
          totalCost: atlas.formatCurrency(hotel.totalCost),
          fit: hotel.fits.join(", "),
          stayWindow: `${atlas.formatDate(city.checkIn)} to ${atlas.formatDate(city.checkOut)}`,
          address: hotel.address || "Address not available",
          rating: hotel.rating ? `${hotel.rating} from ${hotel.reviewCount || 0} reviews` : "Rating not available",
          source: hotel.source || hotel.bestOffer.platform,
          openingInfo: hotel.hours || "See booking link for current hours and contact info",
        },
        history: generated.history,
        forecast: generated.forecast.projected,
        confidence: generated.forecast.confidence,
        trend: generated.forecast.trend,
        offers: [],
        imageUrl: city.profile.mapImageUrl || "",
      };
      atlas.recordFeedback("hotel_hold", hotel.name, 1, { city: city.name, planId: plan.id });
    }

    if (dataset.kind === "attraction") {
      const city = plan.cities[Number(dataset.cityIndex)];
      const attraction = city.attractions[Number(dataset.itemIndex)];
      const generated = atlas.createForecastSeries(attraction.cost, `${attraction.name}-${city.name}`);
      detail = {
        type: "attraction",
        title: attraction.name,
        subtitle: `${city.name} · ${attraction.type}`,
        price: attraction.cost,
        primaryLink: attraction.bestOffer.url,
        provider: attraction.bestOffer.platform,
        body: {
          city: city.name,
          category: attraction.type,
          hours: attraction.hours,
          cost: atlas.formatCurrency(attraction.cost),
          priority: attraction.mustSee ? "Requested by traveler" : "Recommended by planner",
          address: attraction.address || "Address not available",
          rating: attraction.rating ? `${attraction.rating} from ${attraction.reviewCount || 0} reviews` : "Rating not available",
          source: attraction.source || attraction.bestOffer.platform,
        },
        history: generated.history,
        forecast: generated.forecast.projected,
        confidence: generated.forecast.confidence,
        trend: generated.forecast.trend,
        offers: [],
        imageUrl: city.profile.mapImageUrl || "",
      };
      atlas.recordFeedback("attraction_save", attraction.name, 1, { city: city.name, planId: plan.id });
    }

    if (!detail) {
      return;
    }

    atlas.setSelectedDetail(detail);
    window.location.href = "./item-detail.html";
  }

  function renderCompliance(plan, data) {
    return `
      <div class="compliance-card">
        <h3>${atlas.escapeHtml(plan.name)}</h3>
        <p class="summary-note">${data.live ? "Live refresh completed using official web sources where available." : "Using fallback restrictions because live refresh is unavailable."}</p>
      </div>
      ${(data.destinationPanels || [])
        .map(
          (panel) => `
            <section class="compliance-card">
              <div class="compliance-columns">
                <div>
                  <h3>${atlas.escapeHtml(panel.city)}</h3>
                  <p class="summary-note">${atlas.escapeHtml(panel.country)}</p>
                </div>
                <span class="tag">Destination rules</span>
              </div>
              <ul>
                ${(panel.items || []).map((item) => `<li>${atlas.escapeHtml(item)}</li>`).join("")}
              </ul>
              <p class="summary-note">
                Sources:
                ${(panel.sources || [])
                  .map((source) => `<a class="deep-link" href="${source.url}" target="_blank" rel="noreferrer">${atlas.escapeHtml(source.label || source.title || source.url)}</a>`)
                  .join(" · ")}
              </p>
            </section>
          `
        )
        .join("")}
      <section class="compliance-card">
        <h3>Transport mode restrictions</h3>
        <ul>
          ${(data.transportPanel && data.transportPanel.items || []).map((item) => `<li>${atlas.escapeHtml(item)}</li>`).join("")}
        </ul>
        <p class="summary-note">
          Sources:
          ${(data.transportPanel && data.transportPanel.sources || [])
            .map((source) => `<a class="deep-link" href="${source.url}" target="_blank" rel="noreferrer">${atlas.escapeHtml(source.label || source.title || source.url)}</a>`)
            .join(" · ")}
        </p>
      </section>
    `;
  }

  function collectTransportModes(plan) {
    const modes = ["flight"];
    plan.legs.forEach((leg) => {
      leg.groundOptions.forEach((option) => modes.push(option.mode));
    });
    return atlas.unique(modes);
  }

  function costCell(label, value) {
    return `
      <div class="cost-cell">
        <span class="summary-note">${label}</span>
        <strong>${atlas.formatCurrency(value)}</strong>
      </div>
    `;
  }

  function renderCityLivePanel(city) {
    const weather = city.weather;
    const weatherMarkup = weather
      ? `
        <div>
          <h5>Live weather</h5>
          <p class="summary-note">${atlas.escapeHtml(weather.headline || "Live weather available")}</p>
          ${weather.note ? `<p class="summary-note">${atlas.escapeHtml(weather.note)}</p>` : ""}
          ${weather.packHint ? `<p class="summary-note">${atlas.escapeHtml(weather.packHint)}</p>` : ""}
        </div>
      `
      : `<div><h5>Weather</h5><p class="summary-note">No live weather feed was available for this city.</p></div>`;

    const mapMarkup = city.profile.mapImageUrl
      ? `<img src="${city.profile.mapImageUrl}" alt="${atlas.escapeHtml(city.name)} map" class="city-map-image" loading="lazy" />`
      : `<div class="summary-card"><p class="summary-note">Map preview unavailable.</p></div>`;

    return `
      <div class="map-card city-live-panel">
        <div class="transport-topline">
          <div>
            <h5>${atlas.escapeHtml(city.name)} snapshot</h5>
            <p class="summary-note">${atlas.escapeHtml(city.profile.displayName || city.profile.geography)}</p>
          </div>
          <div class="legend">
            ${(city.profile.neighborhoods || [])
              .slice(0, 3)
              .map(
                (neighborhood) =>
                  `<span class="safety-pill ${atlas.escapeHtml(neighborhood.risk)}">${atlas.escapeHtml(neighborhood.name)} · ${atlas.escapeHtml(neighborhood.risk)}</span>`
              )
              .join("")}
          </div>
        </div>
        <div class="city-live-grid">
          <div class="map-image-wrap">${mapMarkup}</div>
          ${weatherMarkup}
        </div>
      </div>
    `;
  }
})();
