(function () {
  const atlas = window.AtlasLane;
  const form = document.getElementById("searchWindowForm");
  if (!form) {
    return;
  }

  atlas.bootstrapMemory();
  atlas.startFreshSearchFlow();
  atlas.bindGeorge(() => {
    const flow = atlas.readFlowState();
    return {
      trip: flow.trip,
      plans: flow.planPayload ? flow.planPayload.plans || [] : [],
      legs: flow.planPayload ? flow.planPayload.legs || [] : [],
    };
  });

  const startDate = document.getElementById("windowStartDate");
  const endDate = document.getElementById("windowEndDate");
  const tripDays = document.getElementById("windowTripDays");
  const status = document.getElementById("windowStatus");
  clearSearchInputs();

  window.addEventListener("pageshow", () => {
    atlas.startFreshSearchFlow();
    clearSearchInputs();
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const payload = {
      startDate: startDate.value,
      endDate: endDate.value,
      tripDays: Number(tripDays.value || 0),
    };

    if (!payload.startDate || !payload.endDate || !payload.tripDays) {
      status.textContent = "Pick a travel window and the number of travel days first.";
      return;
    }

    const availableDays =
      Math.round((new Date(`${payload.endDate}T12:00:00`) - new Date(`${payload.startDate}T12:00:00`)) / (24 * 60 * 60 * 1000)) + 1;
    if (availableDays < payload.tripDays) {
      status.textContent = "The travel window needs to be at least as long as the trip.";
      return;
    }

    atlas.updateFlowState((state) => ({
      ...state,
      searchWindow: payload,
      trip: state.trip
        ? {
            ...state.trip,
            startDate: payload.startDate,
            endDate: payload.endDate,
            tripDays: payload.tripDays,
          }
        : state.trip,
      suggestions: [],
      acceptedSuggestionNames: [],
      planPayload: null,
      selectedDetail: null,
    }));
    window.location.href = "./trip-details.html";
  });

  function clearSearchInputs() {
    startDate.value = "";
    endDate.value = "";
    tripDays.value = "";
    status.textContent = "";
  }
})();
