(function () {
  const atlas = window.AtlasLane;
  const form = document.getElementById("tripDetailsForm");
  if (!form) {
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

  const flow = atlas.readFlowState();
  const searchWindow = flow.searchWindow || {};
  const seededTrip = flow.trip || {};
  const formMessage = document.getElementById("detailsStatus");

  document.getElementById("origin").value = seededTrip.origin || "";
  document.getElementById("returnDestination").value = seededTrip.returnDestination || seededTrip.origin || "";
  document.getElementById("destinations").value = Array.isArray(seededTrip.destinations) ? seededTrip.destinations.join(", ") : "";
  document.getElementById("startDate").value = seededTrip.startDate || searchWindow.startDate || "";
  document.getElementById("endDate").value = seededTrip.endDate || searchWindow.endDate || "";
  document.getElementById("tripDays").value = seededTrip.tripDays || searchWindow.tripDays || "";
  document.getElementById("specificPlaces").value = Array.isArray(seededTrip.specificPlaces) ? seededTrip.specificPlaces.join(", ") : "";
  document.getElementById("bagCount").value = seededTrip.bagCount ?? 1;
  document.getElementById("bagDimensions").value = seededTrip.bagDimensions || '22" x 14" x 9"';
  document.getElementById("bagWeight").value = seededTrip.bagWeight || "18 lb";
  document.getElementById("transportPriority").value = seededTrip.transportPriority || "Cheapest";
  document.getElementById("flightInfo").value = seededTrip.flightInfo || "Show";

  document.querySelectorAll('input[name="attractionType"]').forEach((input) => {
    input.checked = Array.isArray(seededTrip.attractionTypes) && seededTrip.attractionTypes.includes(input.value);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const trip = collectTripData();
    if (!trip) {
      return;
    }

    formMessage.textContent = "Finding suggestions and building your results page...";

    try {
      const suggestionData = await atlas.apiPost("/api/suggestions", { trip });
      const planData = await atlas.apiPost("/api/plan", {
        trip: suggestionData.trip,
        acceptedSuggestions: [],
      });

      atlas.writeFlowState({
        ...atlas.readFlowState(),
        searchWindow: {
          startDate: suggestionData.trip.startDate,
          endDate: suggestionData.trip.endDate,
          tripDays: suggestionData.trip.tripDays,
        },
        trip: suggestionData.trip,
        suggestions: suggestionData.suggestions || [],
        acceptedSuggestionNames: [],
        planPayload: planData,
        memorySnapshot: planData.memorySnapshot || suggestionData.memorySnapshot || atlas.readFlowState().memorySnapshot,
        selectedDetail: null,
      });
      window.location.href = "./results.html";
    } catch (error) {
      formMessage.textContent = atlas.readErrorMessage(
        error,
        "The backend did not respond. Start the local server and try again."
      );
    }
  });

  function collectTripData() {
    const origin = field("origin");
    const returnDestination = field("returnDestination") || origin;
    const destinations = parseList(field("destinations"));
    const startDate = field("startDate");
    const endDate = field("endDate");
    const tripDays = Number(document.getElementById("tripDays").value || 0);
    const attractionTypes = Array.from(document.querySelectorAll('input[name="attractionType"]:checked')).map((input) => input.value);
    const specificPlaces = parseList(field("specificPlaces"));
    const bagCount = Number(document.getElementById("bagCount").value || 0);
    const bagDimensions = field("bagDimensions");
    const bagWeight = field("bagWeight");
    const transportPriority = document.getElementById("transportPriority").value;
    const flightInfo = document.getElementById("flightInfo").value;

    if (!origin || !startDate || !endDate || !tripDays) {
      formMessage.textContent = "Origin, travel window, and total travel days are required.";
      return null;
    }

    if (!destinations.length && returnDestination === origin) {
      formMessage.textContent = "Add at least one destination, or set a different final destination for a direct trip.";
      return null;
    }

    const availableDays =
      Math.round((new Date(`${endDate}T12:00:00`) - new Date(`${startDate}T12:00:00`)) / (24 * 60 * 60 * 1000)) + 1;
    if (availableDays < tripDays) {
      formMessage.textContent = "The selected date window is shorter than the trip length.";
      return null;
    }

    return {
      origin,
      returnDestination,
      destinations,
      startDate,
      endDate,
      tripDays,
      attractionTypes,
      specificPlaces,
      bagCount,
      bagDimensions,
      bagWeight,
      transportPriority,
      flightInfo,
    };
  }

  function field(id) {
    return document.getElementById(id).value.trim();
  }

  function parseList(value) {
    return value
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
})();
