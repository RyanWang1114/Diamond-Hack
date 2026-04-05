(function () {
  const STORAGE_KEY = "atlasLaneMemoryV1";
  const CLIENT_SESSION_KEY = "atlasLaneSessionIdV1";
  const DAY_MS = 24 * 60 * 60 * 1000;

  const PLATFORM_LIBRARY = {
    SkyBridge: { trusted: true, score: 93, categories: ["flight"] },
    TripNest: { trusted: true, score: 89, categories: ["flight", "hotel", "attraction", "ground"] },
    OrbitCart: { trusted: true, score: 86, categories: ["flight"] },
    StayHarbor: { trusted: true, score: 92, categories: ["hotel"] },
    TicketMint: { trusted: true, score: 88, categories: ["attraction"] },
    RailCanvas: { trusted: true, score: 90, categories: ["ground"] },
    GetGoBus: { trusted: true, score: 84, categories: ["ground"] },
    FlashFare: {
      trusted: false,
      score: 22,
      categories: ["flight", "hotel"],
      reason: "Chargeback complaints and hidden-fee patterns",
    },
    BargainRoost: {
      trusted: false,
      score: 18,
      categories: ["hotel"],
      reason: "Bait pricing and refund dispute complaints",
    },
    TicketBlitz: {
      trusted: false,
      score: 26,
      categories: ["attraction"],
      reason: "Poor fulfillment and cancellation handling",
    },
  };

  const AIRLINES = [
    {
      name: "Aurora Atlantic",
      aircraft: ["Boeing 787-9", "Airbus A350-900"],
      baseChecked: 1,
      carryOn: "1 cabin bag + personal item",
      pace: 0.94,
    },
    {
      name: "Cinder Air",
      aircraft: ["Airbus A330-900neo", "Boeing 777-300ER"],
      baseChecked: 1,
      carryOn: "1 carry-on",
      pace: 0.92,
    },
    {
      name: "North Arrow",
      aircraft: ["Boeing 737 MAX 8", "Airbus A321neo"],
      baseChecked: 0,
      carryOn: "Personal item only",
      pace: 1.03,
    },
    {
      name: "Lumen Sky",
      aircraft: ["Airbus A320neo", "Boeing 787-8"],
      baseChecked: 1,
      carryOn: "1 cabin bag",
      pace: 0.99,
    },
    {
      name: "Meridian One",
      aircraft: ["Boeing 767-300ER", "Airbus A321LR"],
      baseChecked: 2,
      carryOn: "1 cabin bag + personal item",
      pace: 0.96,
    },
  ];

  const GROUND_OPERATORS = {
    train: ["RailCanvas", "TripNest"],
    coach: ["GetGoBus", "TripNest"],
    ferry: ["TripNest", "RailCanvas"],
  };

  const CITY_LIBRARY = {
    "San Francisco": {
      name: "San Francisco",
      country: "United States",
      region: "North America",
      airport: "SFO",
      lat: 37.7749,
      lon: -122.4194,
      types: ["Food and cuisine", "Modern architecture", "Natural landscapes", "Cultural sites"],
      climate: "cool coastal microclimates",
      geography: "steep urban hills on the Pacific edge",
      buffer: 92,
      attractions: [
        {
          name: "Golden Gate Bridge",
          type: "Modern architecture",
          cost: 0,
          hours: "Open all day",
        },
        {
          name: "Ferry Building Marketplace",
          type: "Food and cuisine",
          cost: 24,
          hours: "10:00-18:00",
        },
        {
          name: "Lands End Trail",
          type: "Natural landscapes",
          cost: 0,
          hours: "06:00-21:00",
        },
      ],
      hotels: [
        { name: "Harbor Ledger Hotel", area: "Embarcadero", rate: 278, fits: ["Food and cuisine", "Modern architecture"] },
        { name: "Juniper Mission House", area: "Mission District", rate: 234, fits: ["Food and cuisine", "Cultural sites"] },
        { name: "Cliffline Suites", area: "Presidio", rate: 312, fits: ["Natural landscapes"] },
      ],
      neighborhoods: [
        { name: "Embarcadero", risk: "low", x: 26, y: 26, w: 110, h: 72 },
        { name: "North Beach", risk: "medium", x: 130, y: 38, w: 104, h: 70 },
        { name: "Mission", risk: "medium", x: 90, y: 124, w: 114, h: 72 },
        { name: "Presidio", risk: "low", x: 18, y: 112, w: 94, h: 74 },
        { name: "Tenderloin", risk: "high", x: 140, y: 102, w: 90, h: 58 },
      ],
      compliance: {
        destination: [
          "Unlicensed fireworks, switchblades, and undeclared fresh produce can trigger enforcement issues.",
          "Drone flights near protected landmarks and airport corridors require permission before launch.",
          "Prescription medicine should stay in original containers for inspection if requested.",
        ],
        sources: [
          { label: "U.S. Customs and Border Protection", url: "https://www.cbp.gov/" },
          { label: "TSA prohibited items", url: "https://www.tsa.gov/travel/security-screening/whatcanibring/all-list" },
        ],
      },
    },
    Rome: {
      name: "Rome",
      country: "Italy",
      region: "Europe",
      airport: "FCO",
      lat: 41.9028,
      lon: 12.4964,
      types: ["Historical monuments", "Food and cuisine", "Cultural sites"],
      climate: "warm Mediterranean with dry afternoons",
      geography: "historic core spread across seven hills",
      buffer: 74,
      attractions: [
        {
          name: "Colosseum",
          type: "Historical monuments",
          cost: 26,
          hours: "08:30-19:15",
        },
        {
          name: "Roman Forum",
          type: "Historical monuments",
          cost: 18,
          hours: "09:00-19:00",
        },
        {
          name: "Trastevere food walk",
          type: "Food and cuisine",
          cost: 42,
          hours: "17:30-22:00",
        },
      ],
      hotels: [
        { name: "Palazzo Nova", area: "Monti", rate: 218, fits: ["Historical monuments", "Food and cuisine"] },
        { name: "Campo Aureo", area: "Centro Storico", rate: 248, fits: ["Historical monuments", "Cultural sites"] },
        { name: "Tiber Atelier Hotel", area: "Trastevere", rate: 194, fits: ["Food and cuisine", "Cultural sites"] },
      ],
      neighborhoods: [
        { name: "Centro Storico", risk: "low", x: 28, y: 26, w: 108, h: 68 },
        { name: "Monti", risk: "low", x: 140, y: 34, w: 98, h: 70 },
        { name: "Trastevere", risk: "medium", x: 54, y: 116, w: 114, h: 76 },
        { name: "Termini", risk: "high", x: 176, y: 118, w: 84, h: 62 },
        { name: "Prati", risk: "medium", x: 14, y: 106, w: 88, h: 60 },
      ],
      compliance: {
        destination: [
          "Pepper spray strength, knives, and aerosol paint can be restricted around archaeological sites.",
          "Drone operations near monuments and Vatican-adjacent zones require formal authorization.",
          "Fresh meats, dairy, and plant products may require customs declaration when entering Italy.",
        ],
        sources: [
          { label: "Italian Customs and Monopolies Agency", url: "https://www.adm.gov.it/portale/en/web/english" },
          { label: "ENAC drone rules", url: "https://www.enac.gov.it/en/safety-security/drone" },
        ],
      },
    },
    Florence: {
      name: "Florence",
      country: "Italy",
      region: "Europe",
      airport: "FLR",
      lat: 43.7696,
      lon: 11.2558,
      types: ["Historical monuments", "Cultural sites", "Food and cuisine"],
      climate: "sunny inland heat with cooler evenings",
      geography: "compact Renaissance core beside the Arno",
      buffer: 70,
      attractions: [
        { name: "Uffizi Gallery", type: "Cultural sites", cost: 29, hours: "08:15-18:30" },
        { name: "Duomo terraces", type: "Historical monuments", cost: 30, hours: "10:15-16:45" },
        { name: "Oltrarno artisan tasting", type: "Food and cuisine", cost: 38, hours: "16:30-21:00" },
      ],
      hotels: [
        { name: "Arno Ledger", area: "Santa Croce", rate: 186, fits: ["Cultural sites", "Food and cuisine"] },
        { name: "Lantern Ponte Suites", area: "Oltrarno", rate: 208, fits: ["Food and cuisine", "Historical monuments"] },
        { name: "Duomo Court", area: "Duomo", rate: 244, fits: ["Historical monuments"] },
      ],
      neighborhoods: [
        { name: "Duomo", risk: "low", x: 52, y: 30, w: 96, h: 60 },
        { name: "Santa Croce", risk: "low", x: 152, y: 38, w: 98, h: 68 },
        { name: "Oltrarno", risk: "medium", x: 70, y: 116, w: 120, h: 74 },
        { name: "Santa Maria Novella", risk: "medium", x: 14, y: 44, w: 92, h: 72 },
        { name: "Peretola corridor", risk: "high", x: 10, y: 138, w: 88, h: 56 },
      ],
      compliance: {
        destination: [
          "Historic churches and museums may prohibit large backpacks, tripods, and food inside.",
          "Blade tools and certain aerosols can trigger confiscation in crowded heritage zones.",
          "Drone photography over the UNESCO historic center requires prior authorization.",
        ],
        sources: [
          { label: "Italian Customs and Monopolies Agency", url: "https://www.adm.gov.it/portale/en/web/english" },
          { label: "ENAC drone rules", url: "https://www.enac.gov.it/en/safety-security/drone" },
        ],
      },
    },
    Venice: {
      name: "Venice",
      country: "Italy",
      region: "Europe",
      airport: "VCE",
      lat: 45.4408,
      lon: 12.3155,
      types: ["Cultural sites", "Historical monuments", "Food and cuisine"],
      climate: "humid lagoon weather with evening breezes",
      geography: "island canals connected by bridges and vaporetto lines",
      buffer: 76,
      attractions: [
        { name: "Doge's Palace", type: "Historical monuments", cost: 31, hours: "09:00-19:00" },
        { name: "Grand Canal vaporetto pass", type: "Cultural sites", cost: 25, hours: "Open all day" },
        { name: "Cannaregio cicchetti crawl", type: "Food and cuisine", cost: 34, hours: "18:00-22:00" },
      ],
      hotels: [
        { name: "Laguna Mercato", area: "Cannaregio", rate: 232, fits: ["Food and cuisine", "Cultural sites"] },
        { name: "Arsenale Thread", area: "Castello", rate: 218, fits: ["Historical monuments"] },
        { name: "Sestieri House", area: "San Polo", rate: 248, fits: ["Cultural sites", "Food and cuisine"] },
      ],
      neighborhoods: [
        { name: "San Marco", risk: "medium", x: 54, y: 54, w: 96, h: 62 },
        { name: "Cannaregio", risk: "low", x: 10, y: 28, w: 96, h: 70 },
        { name: "Castello", risk: "low", x: 152, y: 46, w: 104, h: 66 },
        { name: "Santa Lucia terminal", risk: "high", x: 18, y: 132, w: 96, h: 56 },
        { name: "San Polo", risk: "medium", x: 114, y: 128, w: 90, h: 56 },
      ],
      compliance: {
        destination: [
          "Swimming in canals, open-flame cooking devices, and unauthorized drones are restricted.",
          "Large wheeled luggage may be limited on certain historic bridges and waterbus boarding points.",
          "Glass, knives, and picnic gear can be restricted during major civic events in central squares.",
        ],
        sources: [
          { label: "City of Venice visitor rules", url: "https://www.comune.venezia.it/en" },
          { label: "Italian Customs and Monopolies Agency", url: "https://www.adm.gov.it/portale/en/web/english" },
        ],
      },
    },
    Barcelona: {
      name: "Barcelona",
      country: "Spain",
      region: "Europe",
      airport: "BCN",
      lat: 41.3874,
      lon: 2.1686,
      types: ["Food and cuisine", "Modern architecture", "Cultural sites", "Natural landscapes"],
      climate: "sunny coast with warm sea air",
      geography: "beachfront city backed by hills",
      buffer: 78,
      attractions: [
        { name: "Sagrada Familia", type: "Modern architecture", cost: 38, hours: "09:00-19:00" },
        { name: "La Boqueria tasting route", type: "Food and cuisine", cost: 26, hours: "10:00-17:00" },
        { name: "Montjuic cable car", type: "Natural landscapes", cost: 18, hours: "10:00-21:00" },
      ],
      hotels: [
        { name: "Rambla Canvas", area: "El Born", rate: 226, fits: ["Food and cuisine", "Cultural sites"] },
        { name: "Gaudi Frame Hotel", area: "Eixample", rate: 244, fits: ["Modern architecture"] },
        { name: "Bogatell Tide House", area: "Poblenou", rate: 198, fits: ["Natural landscapes", "Food and cuisine"] },
      ],
      neighborhoods: [
        { name: "Eixample", risk: "low", x: 84, y: 34, w: 116, h: 76 },
        { name: "El Born", risk: "low", x: 18, y: 34, w: 92, h: 74 },
        { name: "Barceloneta", risk: "medium", x: 182, y: 108, w: 86, h: 64 },
        { name: "Raval", risk: "high", x: 78, y: 124, w: 96, h: 64 },
        { name: "Poblenou", risk: "medium", x: 182, y: 36, w: 88, h: 62 },
      ],
      compliance: {
        destination: [
          "Beach glass containers, open flames, and some loudspeaker devices can be restricted in public spaces.",
          "Knives, pepper spray, and unauthorized drone use may trigger fines or confiscation.",
          "Agricultural products and high-value cash can require declaration when crossing the border.",
        ],
        sources: [
          { label: "Spanish Tax Agency customs", url: "https://sede.agenciatributaria.gob.es/" },
          { label: "AESA drone guidance", url: "https://www.seguridadaerea.gob.es/en/ambitos/drones" },
        ],
      },
    },
    Lisbon: {
      name: "Lisbon",
      country: "Portugal",
      region: "Europe",
      airport: "LIS",
      lat: 38.7223,
      lon: -9.1393,
      types: ["Food and cuisine", "Cultural sites", "Historical monuments", "Natural landscapes"],
      climate: "bright Atlantic sunshine with coastal wind",
      geography: "riverfront hills and tiled neighborhoods",
      buffer: 72,
      attractions: [
        { name: "Jeronimos Monastery", type: "Historical monuments", cost: 18, hours: "10:00-17:30" },
        { name: "Alfama fado evening", type: "Cultural sites", cost: 33, hours: "19:00-23:00" },
        { name: "Time Out Market tasting flight", type: "Food and cuisine", cost: 28, hours: "12:00-22:00" },
      ],
      hotels: [
        { name: "Tagus Ledger", area: "Baixa", rate: 182, fits: ["Cultural sites", "Food and cuisine"] },
        { name: "Azulejo Rise", area: "Alfama", rate: 208, fits: ["Historical monuments", "Cultural sites"] },
        { name: "Belém Drift", area: "Belém", rate: 194, fits: ["Natural landscapes", "Historical monuments"] },
      ],
      neighborhoods: [
        { name: "Baixa", risk: "low", x: 60, y: 52, w: 90, h: 60 },
        { name: "Chiado", risk: "low", x: 144, y: 48, w: 94, h: 64 },
        { name: "Alfama", risk: "medium", x: 38, y: 126, w: 94, h: 66 },
        { name: "Belém", risk: "low", x: 164, y: 124, w: 90, h: 60 },
        { name: "Cais do Sodré late-night strip", risk: "high", x: 94, y: 136, w: 102, h: 56 },
      ],
      compliance: {
        destination: [
          "Historic tram and monument areas may reject oversized bags, glass bottles, and open alcohol containers.",
          "Drone flights over dense heritage districts need advance permission and airspace clearance.",
          "Certain plant products, animal goods, and large cash amounts require declaration.",
        ],
        sources: [
          { label: "Portuguese Tax and Customs Authority", url: "https://info-aduaneiro.portaldasfinancas.gov.pt/" },
          { label: "Portuguese civil aviation drone guidance", url: "https://www.anac.pt/" },
        ],
      },
    },
    Paris: {
      name: "Paris",
      country: "France",
      region: "Europe",
      airport: "CDG",
      lat: 48.8566,
      lon: 2.3522,
      types: ["Historical monuments", "Food and cuisine", "Cultural sites", "Modern architecture"],
      climate: "mild city weather with occasional showers",
      geography: "dense urban districts straddling the Seine",
      buffer: 88,
      attractions: [
        { name: "Louvre Museum", type: "Cultural sites", cost: 23, hours: "09:00-18:00" },
        { name: "Eiffel Tower summit", type: "Modern architecture", cost: 36, hours: "09:30-23:45" },
        { name: "Marais pastry circuit", type: "Food and cuisine", cost: 32, hours: "11:00-18:30" },
      ],
      hotels: [
        { name: "Seine Ledger", area: "Saint-Germain", rate: 296, fits: ["Cultural sites", "Food and cuisine"] },
        { name: "Atelier République", area: "Le Marais", rate: 258, fits: ["Food and cuisine", "Modern architecture"] },
        { name: "Left Bank Glasshouse", area: "7th arrondissement", rate: 320, fits: ["Historical monuments"] },
      ],
      neighborhoods: [
        { name: "Le Marais", risk: "low", x: 20, y: 40, w: 92, h: 62 },
        { name: "Saint-Germain", risk: "low", x: 122, y: 44, w: 102, h: 64 },
        { name: "Montmartre", risk: "medium", x: 42, y: 128, w: 94, h: 62 },
        { name: "Chatelet transport hub", risk: "high", x: 142, y: 126, w: 100, h: 58 },
        { name: "Canal Saint-Martin", risk: "medium", x: 182, y: 36, w: 84, h: 60 },
      ],
      compliance: {
        destination: [
          "Switchblades, pepper spray, and fireworks can trigger police intervention and confiscation.",
          "Drones are highly restricted in Paris without formal authorization and geofencing compliance.",
          "Fresh meats, dairy, and undeclared luxury purchases may require customs attention.",
        ],
        sources: [
          { label: "French Customs", url: "https://www.douane.gouv.fr/" },
          { label: "French civil aviation drone rules", url: "https://www.ecologie.gouv.fr/politiques-publiques/drones-loisir-professionnel" },
        ],
      },
    },
    Prague: {
      name: "Prague",
      country: "Czech Republic",
      region: "Europe",
      airport: "PRG",
      lat: 50.0755,
      lon: 14.4378,
      types: ["Historical monuments", "Cultural sites", "Food and cuisine"],
      climate: "cooler continental weather with crisp evenings",
      geography: "river city of bridges and castle hills",
      buffer: 62,
      attractions: [
        { name: "Prague Castle circuit", type: "Historical monuments", cost: 24, hours: "09:00-17:00" },
        { name: "Old Town astronomy walk", type: "Cultural sites", cost: 16, hours: "10:00-20:00" },
        { name: "Riverside beer tasting", type: "Food and cuisine", cost: 22, hours: "17:00-22:00" },
      ],
      hotels: [
        { name: "Charles Bridge Ledger", area: "Mala Strana", rate: 164, fits: ["Historical monuments"] },
        { name: "Astronomical House", area: "Old Town", rate: 176, fits: ["Cultural sites"] },
        { name: "Vltava Table Hotel", area: "Nove Mesto", rate: 152, fits: ["Food and cuisine"] },
      ],
      neighborhoods: [
        { name: "Old Town", risk: "low", x: 48, y: 44, w: 96, h: 64 },
        { name: "Mala Strana", risk: "low", x: 148, y: 48, w: 98, h: 62 },
        { name: "Nove Mesto", risk: "medium", x: 86, y: 126, w: 112, h: 64 },
        { name: "Main station zone", risk: "high", x: 8, y: 132, w: 86, h: 58 },
        { name: "Vinohrady", risk: "low", x: 186, y: 126, w: 84, h: 58 },
      ],
      compliance: {
        destination: [
          "Pyrotechnics, some knives, and drone launches in the historic core can be restricted.",
          "Protected heritage interiors may reject large bags, tripods, or open drinks.",
          "Customs declaration applies to certain food products, tobacco quantities, and large cash transport.",
        ],
        sources: [
          { label: "Czech Customs Administration", url: "https://www.celnisprava.cz/en/" },
          { label: "Civil Aviation Authority drone guidance", url: "https://www.caa.cz/en/" },
        ],
      },
    },
    Vienna: {
      name: "Vienna",
      country: "Austria",
      region: "Europe",
      airport: "VIE",
      lat: 48.2082,
      lon: 16.3738,
      types: ["Historical monuments", "Cultural sites", "Food and cuisine", "Modern architecture"],
      climate: "mild continental weather with cooler mornings",
      geography: "imperial boulevards and museum districts",
      buffer: 74,
      attractions: [
        { name: "Schonbrunn Palace", type: "Historical monuments", cost: 32, hours: "08:30-17:30" },
        { name: "MuseumQuartier circuit", type: "Cultural sites", cost: 21, hours: "10:00-19:00" },
        { name: "Naschmarkt tasting trail", type: "Food and cuisine", cost: 24, hours: "11:00-18:00" },
      ],
      hotels: [
        { name: "Ringstrasse Hall", area: "Innere Stadt", rate: 204, fits: ["Historical monuments", "Cultural sites"] },
        { name: "Quartier Bloom", area: "Neubau", rate: 188, fits: ["Modern architecture", "Food and cuisine"] },
        { name: "Belvedere Chapter", area: "Landstrasse", rate: 174, fits: ["Historical monuments"] },
      ],
      neighborhoods: [
        { name: "Innere Stadt", risk: "low", x: 46, y: 42, w: 102, h: 64 },
        { name: "Neubau", risk: "low", x: 154, y: 44, w: 92, h: 62 },
        { name: "Leopoldstadt", risk: "medium", x: 20, y: 124, w: 92, h: 60 },
        { name: "Prater edge", risk: "medium", x: 178, y: 126, w: 86, h: 58 },
        { name: "Transit belt near Hauptbahnhof", risk: "high", x: 96, y: 132, w: 96, h: 58 },
      ],
      compliance: {
        destination: [
          "Weapons, pepper spray, fireworks, and unauthorized drones can be restricted or require permits.",
          "Major museums may prohibit large bags, selfie sticks, and outside food in galleries.",
          "Certain food imports, animal products, and high-value purchases may require declaration.",
        ],
        sources: [
          { label: "Austrian customs", url: "https://www.bmf.gv.at/en/topics/customs.html" },
          { label: "Austro Control drone guidance", url: "https://www.dronespace.at/en/" },
        ],
      },
    },
    Tokyo: {
      name: "Tokyo",
      country: "Japan",
      region: "Asia",
      airport: "HND",
      lat: 35.6762,
      lon: 139.6503,
      types: ["Food and cuisine", "Modern architecture", "Cultural sites"],
      climate: "humid urban weather with strong seasonal swings",
      geography: "dense mega-city of rail hubs and waterfront districts",
      buffer: 84,
      attractions: [
        { name: "TeamLab Borderless", type: "Modern architecture", cost: 27, hours: "09:00-21:00" },
        { name: "Tsukiji food crawl", type: "Food and cuisine", cost: 31, hours: "07:00-13:00" },
        { name: "Asakusa temple circuit", type: "Cultural sites", cost: 12, hours: "06:00-17:00" },
      ],
      hotels: [
        { name: "Shibuya Current", area: "Shibuya", rate: 214, fits: ["Modern architecture", "Food and cuisine"] },
        { name: "Asakusa Lantern Inn", area: "Asakusa", rate: 186, fits: ["Cultural sites"] },
        { name: "Ginza Fieldnote", area: "Ginza", rate: 248, fits: ["Food and cuisine", "Modern architecture"] },
      ],
      neighborhoods: [
        { name: "Ginza", risk: "low", x: 42, y: 36, w: 96, h: 64 },
        { name: "Shibuya", risk: "medium", x: 152, y: 46, w: 96, h: 72 },
        { name: "Asakusa", risk: "low", x: 20, y: 126, w: 92, h: 60 },
        { name: "Kabukicho", risk: "high", x: 122, y: 130, w: 90, h: 58 },
        { name: "Toyosu waterfront", risk: "medium", x: 194, y: 122, w: 84, h: 58 },
      ],
      compliance: {
        destination: [
          "Certain over-the-counter medicines, firearms, and stimulants face strict controls or outright bans.",
          "Drones are heavily regulated in dense urban airspace and near government or rail infrastructure.",
          "Fresh food, meat products, and plant matter may require declaration or be prohibited at entry.",
        ],
        sources: [
          { label: "Japan Customs prohibited items", url: "https://www.customs.go.jp/english/summary/prohibit.htm" },
          { label: "Japan MLIT drone rules", url: "https://www.mlit.go.jp/koku/drone/en/" },
        ],
      },
    },
    Kyoto: {
      name: "Kyoto",
      country: "Japan",
      region: "Asia",
      airport: "KIX",
      lat: 35.0116,
      lon: 135.7681,
      types: ["Cultural sites", "Historical monuments", "Food and cuisine", "Natural landscapes"],
      climate: "seasonal valley weather with humid summers",
      geography: "temple basin ringed by forested hills",
      buffer: 68,
      attractions: [
        { name: "Fushimi Inari sunrise walk", type: "Natural landscapes", cost: 0, hours: "Open all day" },
        { name: "Kiyomizu-dera", type: "Historical monuments", cost: 8, hours: "06:00-18:00" },
        { name: "Nishiki Market tasting strip", type: "Food and cuisine", cost: 22, hours: "10:00-17:00" },
      ],
      hotels: [
        { name: "Machiya Ledger", area: "Gion", rate: 194, fits: ["Cultural sites", "Historical monuments"] },
        { name: "Philosopher's Rest", area: "Higashiyama", rate: 176, fits: ["Natural landscapes", "Cultural sites"] },
        { name: "Nishiki Thread", area: "Downtown Kyoto", rate: 188, fits: ["Food and cuisine"] },
      ],
      neighborhoods: [
        { name: "Gion", risk: "low", x: 52, y: 42, w: 96, h: 62 },
        { name: "Higashiyama", risk: "low", x: 150, y: 42, w: 98, h: 68 },
        { name: "Downtown Kyoto", risk: "medium", x: 50, y: 126, w: 112, h: 62 },
        { name: "Kyoto Station zone", risk: "medium", x: 170, y: 126, w: 92, h: 58 },
        { name: "Entertainment lanes late at night", risk: "high", x: 18, y: 132, w: 86, h: 56 },
      ],
      compliance: {
        destination: [
          "Temple complexes may prohibit drones, tripods, or oversized luggage inside heritage grounds.",
          "Certain medicines, pepper spray, and weapons face strict Japanese import controls.",
          "Fresh produce, seeds, and animal products may be banned or require inspection at entry.",
        ],
        sources: [
          { label: "Japan Customs prohibited items", url: "https://www.customs.go.jp/english/summary/prohibit.htm" },
          { label: "Japan MLIT drone rules", url: "https://www.mlit.go.jp/koku/drone/en/" },
        ],
      },
    },
    Seoul: {
      name: "Seoul",
      country: "South Korea",
      region: "Asia",
      airport: "ICN",
      lat: 37.5665,
      lon: 126.978,
      types: ["Food and cuisine", "Cultural sites", "Modern architecture"],
      climate: "four-season weather with humid summers and dry winters",
      geography: "high-rise districts divided by river and mountain ridges",
      buffer: 72,
      attractions: [
        { name: "Gyeongbokgung Palace", type: "Historical monuments", cost: 6, hours: "09:00-18:00" },
        { name: "Dongdaemun design circuit", type: "Modern architecture", cost: 14, hours: "10:00-20:00" },
        { name: "Gwangjang market tasting run", type: "Food and cuisine", cost: 20, hours: "10:00-22:00" },
      ],
      hotels: [
        { name: "Han River Ledger", area: "Mapo", rate: 172, fits: ["Food and cuisine", "Modern architecture"] },
        { name: "Palace Courtyard", area: "Jongno", rate: 188, fits: ["Cultural sites"] },
        { name: "Design District Loft", area: "Dongdaemun", rate: 196, fits: ["Modern architecture"] },
      ],
      neighborhoods: [
        { name: "Jongno", risk: "low", x: 44, y: 36, w: 96, h: 64 },
        { name: "Mapo", risk: "low", x: 154, y: 36, w: 94, h: 62 },
        { name: "Dongdaemun", risk: "medium", x: 88, y: 122, w: 102, h: 64 },
        { name: "Itaewon late-night zone", risk: "high", x: 18, y: 128, w: 86, h: 58 },
        { name: "Gangnam", risk: "medium", x: 192, y: 122, w: 86, h: 60 },
      ],
      compliance: {
        destination: [
          "Some medications, drones, pepper spray, and food imports are controlled or require declaration.",
          "Palaces and museums may prohibit selfie sticks, large bags, and tripods inside galleries.",
          "Plant products, meat, and high-value purchases may require customs documentation.",
        ],
        sources: [
          { label: "Korea Customs Service", url: "https://www.customs.go.kr/english/main.do" },
          { label: "Korea aviation drone portal", url: "https://drone.onestop.go.kr/" },
        ],
      },
    },
    Vancouver: {
      name: "Vancouver",
      country: "Canada",
      region: "North America",
      airport: "YVR",
      lat: 49.2827,
      lon: -123.1207,
      types: ["Natural landscapes", "Food and cuisine", "Cultural sites"],
      climate: "temperate coastal rain with mountain air",
      geography: "harbor city between sea and forested peaks",
      buffer: 86,
      attractions: [
        { name: "Stanley Park cycle loop", type: "Natural landscapes", cost: 18, hours: "06:00-22:00" },
        { name: "Granville Island market", type: "Food and cuisine", cost: 22, hours: "09:00-19:00" },
        { name: "Museum of Anthropology", type: "Cultural sites", cost: 19, hours: "10:00-17:00" },
      ],
      hotels: [
        { name: "Coal Harbour Ledger", area: "Coal Harbour", rate: 268, fits: ["Natural landscapes"] },
        { name: "Gastown Current", area: "Gastown", rate: 214, fits: ["Cultural sites", "Food and cuisine"] },
        { name: "False Creek House", area: "Olympic Village", rate: 226, fits: ["Natural landscapes", "Food and cuisine"] },
      ],
      neighborhoods: [
        { name: "Coal Harbour", risk: "low", x: 18, y: 34, w: 96, h: 62 },
        { name: "Olympic Village", risk: "low", x: 142, y: 42, w: 100, h: 64 },
        { name: "Gastown", risk: "medium", x: 62, y: 120, w: 98, h: 60 },
        { name: "Downtown Eastside edge", risk: "high", x: 168, y: 126, w: 92, h: 58 },
        { name: "West End", risk: "low", x: 190, y: 34, w: 84, h: 56 },
      ],
      compliance: {
        destination: [
          "Firearms, bear spray, and certain knives face strict transport and import controls.",
          "Fresh food, cannabis cross-border transport, and wildlife products can trigger customs issues.",
          "Drone flights in controlled airspace or parks require compliance with Canadian regulations.",
        ],
        sources: [
          { label: "Canada Border Services Agency", url: "https://www.cbsa-asfc.gc.ca/travel-voyage/menu-eng.html" },
          { label: "Transport Canada drone rules", url: "https://tc.canada.ca/en/aviation/drone-safety" },
        ],
      },
    },
    Istanbul: {
      name: "Istanbul",
      country: "Turkey",
      region: "Europe",
      airport: "IST",
      lat: 41.0082,
      lon: 28.9784,
      types: ["Historical monuments", "Food and cuisine", "Cultural sites"],
      climate: "sea-influenced weather with warm afternoons",
      geography: "cross-continental city divided by waterways and hills",
      buffer: 66,
      attractions: [
        { name: "Hagia Sophia", type: "Historical monuments", cost: 28, hours: "09:00-19:30" },
        { name: "Bosphorus ferry", type: "Natural landscapes", cost: 8, hours: "10:00-21:00" },
        { name: "Kadikoy market grazing", type: "Food and cuisine", cost: 20, hours: "11:00-20:00" },
      ],
      hotels: [
        { name: "Golden Horn Ledger", area: "Karakoy", rate: 166, fits: ["Food and cuisine", "Cultural sites"] },
        { name: "Blue Mosque Residence", area: "Sultanahmet", rate: 194, fits: ["Historical monuments"] },
        { name: "Moda Current", area: "Kadikoy", rate: 158, fits: ["Food and cuisine"] },
      ],
      neighborhoods: [
        { name: "Sultanahmet", risk: "low", x: 38, y: 40, w: 104, h: 66 },
        { name: "Karakoy", risk: "medium", x: 156, y: 40, w: 94, h: 62 },
        { name: "Kadikoy", risk: "low", x: 182, y: 126, w: 90, h: 60 },
        { name: "Taksim late-night zone", risk: "high", x: 62, y: 126, w: 106, h: 60 },
        { name: "Besiktas", risk: "medium", x: 10, y: 126, w: 82, h: 60 },
      ],
      compliance: {
        destination: [
          "Drones, certain medicines, religious-site attire items, and some aerosol products may face controls.",
          "Historic mosques may prohibit large bags, tripods, and disruptive photography accessories.",
          "Customs attention can apply to alcohol, tobacco, cash, and certain electronics quantities.",
        ],
        sources: [
          { label: "Republic of Türkiye Trade Ministry customs", url: "https://ticaret.gov.tr/" },
          { label: "Turkish civil aviation drone rules", url: "https://web.shgm.gov.tr/en/s/2929-drones" },
        ],
      },
    },
  };

  const DEMO_TRIP = {
    origin: "San Francisco",
    returnDestination: "San Francisco",
    destinations: ["Rome", "Florence", "Barcelona"],
    startDate: "2026-06-10",
    endDate: "2026-06-26",
    tripDays: 11,
    attractionTypes: ["Historical monuments", "Food and cuisine", "Cultural sites"],
    specificPlaces: ["Colosseum", "Uffizi Gallery", "La Boqueria"],
    bagCount: 1,
    bagDimensions: '22" x 14" x 9"',
    bagWeight: "18 lb",
    transportPriority: "Cheapest",
    flightInfo: "Show",
  };

  const state = {
    trip: null,
    suggestions: [],
    acceptedSuggestions: [],
    legs: [],
    plans: [],
    selectedHotels: {},
    savedAttractions: {},
    packingList: [],
    georgeOpen: false,
    georgeMessages: [],
    mapStates: {},
    compliancePlanId: null,
  };

  let memory = loadMemory();
  const sessionId = getClientSessionId();

  const elements = {
    tripForm: document.getElementById("tripForm"),
    formMessage: document.getElementById("formMessage"),
    suggestionSection: document.getElementById("suggestionSection"),
    suggestionCards: document.getElementById("suggestionCards"),
    generatePlans: document.getElementById("generatePlans"),
    transportSection: document.getElementById("transportSection"),
    transportContent: document.getElementById("transportContent"),
    plansSection: document.getElementById("plansSection"),
    plansContent: document.getElementById("plansContent"),
    routeSummary: document.getElementById("routeSummary"),
    learningSummary: document.getElementById("learningSummary"),
    trustSummary: document.getElementById("trustSummary"),
    statusPills: document.getElementById("statusPills"),
    georgeToggle: document.getElementById("georgeToggle"),
    georgePanel: document.getElementById("georgePanel"),
    closeGeorge: document.getElementById("closeGeorge"),
    georgeMessages: document.getElementById("georgeMessages"),
    georgeForm: document.getElementById("georgeForm"),
    georgeInput: document.getElementById("georgeInput"),
    packingListPanel: document.getElementById("packingListPanel"),
    packingListItems: document.getElementById("packingListItems"),
    complianceModal: document.getElementById("complianceModal"),
    complianceContent: document.getElementById("complianceContent"),
    closeCompliance: document.getElementById("closeCompliance"),
    loadDemo: document.getElementById("loadDemo"),
    resetMemory: document.getElementById("resetMemory"),
  };

  init();

  function init() {
    hydrateForm(memory.lastTrip || null);
    bindEvents();
    renderSummaries();
    void bootstrapFromServer();
    addGeorgeMessage(
      "assistant",
      "I can explain the route logic, turn the current itinerary into a packing list, or help you read the safety and compliance layers."
    );
  }

  function bindEvents() {
    elements.tripForm.addEventListener("submit", handleTripSubmit);
    elements.generatePlans.addEventListener("click", handleGeneratePlans);
    elements.suggestionCards.addEventListener("click", handleSuggestionAction);
    elements.plansContent.addEventListener("click", handlePlanAction);
    elements.transportContent.addEventListener("click", handlePlanAction);
    elements.georgeToggle.addEventListener("click", toggleGeorge);
    elements.closeGeorge.addEventListener("click", closeGeorge);
    elements.georgeForm.addEventListener("submit", handleGeorgeSubmit);
    elements.packingListItems.addEventListener("change", handlePackingToggle);
    elements.closeCompliance.addEventListener("click", closeCompliance);
    elements.complianceModal.addEventListener("click", (event) => {
      if (event.target.dataset.closeModal) {
        closeCompliance();
      }
    });
    elements.loadDemo.addEventListener("click", () => {
      hydrateForm(DEMO_TRIP);
      submitCurrentForm();
    });
    elements.resetMemory.addEventListener("click", resetMemory);
    document.querySelectorAll(".chip-button").forEach((button) => {
      button.addEventListener("click", () => {
        const prompt = button.dataset.prompt;
        addGeorgeMessage("user", prompt);
        void sendGeorgePrompt(prompt);
      });
    });
  }

  async function handleTripSubmit(event) {
    event.preventDefault();
    const trip = collectTripData();
    if (!trip) {
      return;
    }

    state.trip = trip;
    state.legs = [];
    state.plans = [];
    state.acceptedSuggestions = [];
    state.mapStates = {};
    elements.transportSection.classList.add("hidden");
    elements.plansSection.classList.add("hidden");

    elements.formMessage.textContent = "Finding route-compatible city suggestions...";

    try {
      const data = await apiPost("/api/suggestions", { trip });
      state.trip = data.trip || trip;
      state.suggestions = data.suggestions || [];
      syncMemory(data.memorySnapshot);
      elements.formMessage.textContent = `${state.suggestions.length} optional city suggestion${state.suggestions.length === 1 ? "" : "s"} prepared.`;
      renderSuggestions();
      renderSummaries();
      addGeorgeMessage(
        "assistant",
        `I mapped ${state.trip.destinations.length} requested stop${state.trip.destinations.length === 1 ? "" : "s"} and found ${state.suggestions.length} compatible optional city addition${state.suggestions.length === 1 ? "" : "s"}.`
      );
      return;
    } catch (error) {
      elements.formMessage.textContent = "Backend unavailable, using the local planner fallback.";
    }

    rememberTripInputs(trip);
    memory.lastTrip = trip;
    state.suggestions = suggestCities(trip);
    elements.formMessage.textContent = `${state.suggestions.length} optional city suggestion${state.suggestions.length === 1 ? "" : "s"} prepared.`;
    renderSuggestions();
    renderSummaries();
    addGeorgeMessage(
      "assistant",
      `I mapped ${trip.destinations.length} requested stop${trip.destinations.length === 1 ? "" : "s"} and found ${state.suggestions.length} compatible optional city addition${state.suggestions.length === 1 ? "" : "s"}.`
    );
    saveMemory();
  }

  async function handleGeneratePlans() {
    if (!state.trip) {
      elements.formMessage.textContent = "Start by collecting a trip brief first.";
      return;
    }

    const route = buildFinalRoute();
    if (route.length < 3) {
      elements.formMessage.textContent = "Add at least one destination before generating plans.";
      return;
    }

    elements.formMessage.textContent = "Building itineraries, transport, and price forecasts...";

    try {
      await refreshPlansFromBackend();
      elements.formMessage.textContent = "Itineraries refreshed from the backend planner.";
      addGeorgeMessage(
        "assistant",
        "Three itinerary styles are ready. I also updated baggage-aware flights, public transport alternatives, and a 7-day price forecast for each route leg."
      );
      return;
    } catch (error) {
      elements.formMessage.textContent = "Backend unavailable, using the local planner fallback.";
    }

    state.legs = buildTransport(route, state.trip);
    state.plans = buildPlans(route, state.trip, state.legs);
    renderTransport();
    renderPlans();
    renderSummaries();
    addGeorgeMessage(
      "assistant",
      `Three itinerary styles are ready. I also updated baggage-aware flights, public transport alternatives, and a 7-day price forecast for each route leg.`
    );
  }

  async function handleSuggestionAction(event) {
    const button = event.target.closest("button[data-suggestion-name]");
    if (!button) {
      return;
    }

    const cityName = button.dataset.suggestionName;
    const action = button.dataset.action;
    const suggestion = state.suggestions.find((item) => item.name === cityName);
    if (!suggestion) {
      return;
    }

    if (action === "accept") {
      const cityCount = state.trip.destinations.length + state.acceptedSuggestions.length + 1;
      if (cityCount >= state.trip.tripDays) {
        elements.formMessage.textContent = "That extra stop would make the itinerary too compressed for the selected number of days.";
        return;
      }
      if (!state.acceptedSuggestions.some((item) => item.name === cityName)) {
        state.acceptedSuggestions.push(suggestion);
        suggestion.declined = false;
        incrementCounter(memory.profile.addedCities, cityName);
        incrementCounter(memory.globalSignals.addedCities, cityName);
        elements.formMessage.textContent = `${cityName} added to the route.`;
        await syncFeedback("city_add", cityName, 1, { cityName });
      }
    }

    if (action === "decline") {
      state.acceptedSuggestions = state.acceptedSuggestions.filter((item) => item.name !== cityName);
      incrementCounter(memory.profile.skippedCities, cityName);
      suggestion.declined = true;
      elements.formMessage.textContent = `${cityName} skipped for this trip.`;
      await syncFeedback("city_skip", cityName, 1, { cityName });
    }

    saveMemory();
    renderSuggestions();
    renderSummaries();
  }

  async function handlePlanAction(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }

    const action = button.dataset.action;

    if (action === "flag-platform") {
      const platform = button.dataset.platform;
      if (platform) {
        memory.flaggedPlatforms[platform] = {
          source: "user",
          reason: "User marked as suspicious",
          flaggedAt: new Date().toISOString(),
        };
        addGeorgeMessage("assistant", `${platform} is now excluded from future results in this browser profile.`);
        try {
          const data = await apiPost("/api/platform/flag", {
            platform,
            reason: "User marked as suspicious",
          });
          syncMemory(data.memorySnapshot);
        } catch (error) {
          saveMemory();
        }
        if (state.trip && state.legs.length) {
          try {
            await refreshPlansFromBackend();
          } catch (error) {
            const route = buildFinalRoute();
            state.legs = buildTransport(route, state.trip);
            state.plans = buildPlans(route, state.trip, state.legs);
            renderTransport();
            renderPlans();
          }
        }
        renderSummaries();
      }
      return;
    }

    if (action === "book-hotel") {
      const key = `${button.dataset.planId}:${button.dataset.city}`;
      state.selectedHotels[key] = button.dataset.hotel;
      incrementCounter(memory.profile.hotels, button.dataset.hotel);
      incrementCounter(memory.globalSignals.hotels, button.dataset.hotel);
      await syncFeedback("hotel_hold", button.dataset.hotel, 1, {
        city: button.dataset.city,
        planId: button.dataset.planId,
      });
      saveMemory();
      renderPlans();
      renderSummaries();
      return;
    }

    if (action === "save-attraction") {
      const key = `${button.dataset.planId}:${button.dataset.city}:${button.dataset.attraction}`;
      state.savedAttractions[key] = true;
      incrementCounter(memory.profile.savedAttractions, button.dataset.attraction);
      incrementCounter(memory.globalSignals.savedAttractions, button.dataset.attraction);
      await syncFeedback("attraction_save", button.dataset.attraction, 1, {
        city: button.dataset.city,
        planId: button.dataset.planId,
      });
      saveMemory();
      renderPlans();
      renderSummaries();
      return;
    }

    if (action === "open-compliance") {
      await openCompliance(button.dataset.planId);
      return;
    }

    if (action.startsWith("map-")) {
      updateMapState(button.dataset.mapId, action);
      renderPlans();
    }
  }

  async function handleGeorgeSubmit(event) {
    event.preventDefault();
    const prompt = elements.georgeInput.value.trim();
    if (!prompt) {
      return;
    }
    addGeorgeMessage("user", prompt);
    elements.georgeInput.value = "";
    await sendGeorgePrompt(prompt);
  }

  async function handlePackingToggle(event) {
    const checkbox = event.target;
    if (!(checkbox instanceof HTMLInputElement)) {
      return;
    }
    const item = checkbox.dataset.item;
    if (!item) {
      return;
    }
    incrementCounter(memory.profile.packingItems, item, checkbox.checked ? 1 : -1);
    await syncFeedback("packing_item", item, checkbox.checked ? 1 : -1, {
      checked: checkbox.checked,
    });
    saveMemory();
    renderSummaries();
  }

  function toggleGeorge() {
    state.georgeOpen = !state.georgeOpen;
    elements.georgePanel.classList.toggle("hidden", !state.georgeOpen);
  }

  function closeGeorge() {
    state.georgeOpen = false;
    elements.georgePanel.classList.add("hidden");
  }

  async function openCompliance(planId) {
    state.compliancePlanId = planId;
    const plan = state.plans.find((item) => item.id === planId);
    if (!plan) {
      return;
    }
    elements.complianceModal.classList.remove("hidden");
    elements.complianceContent.innerHTML = `
      <div class="compliance-card">
        <h3>Refreshing restrictions</h3>
        <p class="summary-note">Checking destination and transport guidance...</p>
      </div>
    `;
    try {
      const data = await apiPost("/api/compliance", {
        cities: plan.cities.map((city) => ({
          name: city.name,
          country: city.profile.country,
          geography: city.profile.geography,
        })),
        transportModes: collectTransportModes(plan),
      });
      elements.complianceContent.innerHTML = renderComplianceModalFromService(plan, data);
      return;
    } catch (error) {
      elements.complianceContent.innerHTML = renderComplianceModal(plan);
    }
  }

  function closeCompliance() {
    elements.complianceModal.classList.add("hidden");
  }

  function submitCurrentForm() {
    elements.tripForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  }

  function collectTripData() {
    const origin = getFieldValue("origin");
    const returnDestination = getFieldValue("returnDestination") || origin;
    const destinations = parseList(getFieldValue("destinations"));
    const startDate = getFieldValue("startDate");
    const endDate = getFieldValue("endDate");
    const tripDays = Number(document.getElementById("tripDays").value || 0);
    const attractionTypes = Array.from(document.querySelectorAll('input[name="attractionType"]:checked')).map((input) => input.value);
    const specificPlaces = parseList(getFieldValue("specificPlaces"));
    const bagCount = Number(document.getElementById("bagCount").value || 0);
    const bagDimensions = getFieldValue("bagDimensions");
    const bagWeight = getFieldValue("bagWeight");
    const transportPriority = document.getElementById("transportPriority").value;
    const flightInfo = document.getElementById("flightInfo").value;

    if (!origin || !destinations.length || !startDate || !endDate || !tripDays) {
      elements.formMessage.textContent = "Origin, destinations, date range, and total travel days are all required.";
      return null;
    }

    const availableDays = diffDays(startDate, endDate) + 1;
    if (availableDays < tripDays) {
      elements.formMessage.textContent = "The selected date range is shorter than the requested trip duration.";
      return null;
    }

    if (tripDays < destinations.length) {
      elements.formMessage.textContent = "The trip duration should be at least one day per destination.";
      return null;
    }

    if (new Date(startDate).getTime() > new Date(endDate).getTime()) {
      elements.formMessage.textContent = "The start date must be on or before the end date.";
      return null;
    }

    return {
      origin,
      returnDestination,
      destinations: unique(destinations),
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

  function rememberTripInputs(trip) {
    incrementCounter(memory.profile.transportPriority, trip.transportPriority);
    incrementCounter(memory.globalSignals.transportPriority, trip.transportPriority);
    trip.attractionTypes.forEach((type) => {
      incrementCounter(memory.profile.attractionTypes, type);
      incrementCounter(memory.globalSignals.attractionTypes, type);
    });
    trip.destinations.forEach((city) => {
      incrementCounter(memory.profile.destinations, city);
      incrementCounter(memory.globalSignals.destinations, city);
    });
  }

  function suggestCities(trip) {
    const route = [trip.origin].concat(trip.destinations, [trip.returnDestination]);
    const routeProfiles = route.map((city) => getCityProfile(city));
    const candidates = Object.values(CITY_LIBRARY).filter((city) => !route.includes(city.name));
    const preferredTypes = trip.attractionTypes.length ? trip.attractionTypes : topKeys(memory.profile.attractionTypes, 2);

    const ranked = candidates
      .map((city) => {
        let bestSegmentScore = -Infinity;
        let bestSegmentIndex = 0;

        routeProfiles.slice(0, -1).forEach((profile, index) => {
          const next = routeProfiles[index + 1];
          const routeScore = scoreRouteFit(profile, next, city);
          if (routeScore > bestSegmentScore) {
            bestSegmentScore = routeScore;
            bestSegmentIndex = index;
          }
        });

        const typeOverlap = countOverlap(city.types, preferredTypes);
        const learnedBoost =
          getCount(memory.profile.destinations, city.name) * 5 +
          getCount(memory.profile.addedCities, city.name) * 6 +
          getCount(memory.globalSignals.addedCities, city.name) * 2 -
          getCount(memory.profile.skippedCities, city.name) * 7;

        const score = bestSegmentScore + typeOverlap * 16 + learnedBoost;
        return {
          name: city.name,
          score,
          segmentIndex: bestSegmentIndex,
          profile: city,
          matchingTags: city.types.filter((type) => preferredTypes.includes(type)).slice(0, 3),
        };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 2);

    return ranked.map((item) => ({
      ...item,
      reason: buildSuggestionReason(item, route[item.segmentIndex], route[item.segmentIndex + 1]),
      declined: false,
    }));
  }

  function buildFinalRoute() {
    const baseRoute = [state.trip.origin].concat(state.trip.destinations, [state.trip.returnDestination]);
    const finalRoute = [baseRoute[0]];

    baseRoute.slice(0, -1).forEach((city, index) => {
      state.acceptedSuggestions
        .filter((item) => item.segmentIndex === index)
        .sort((a, b) => b.score - a.score)
        .forEach((suggestion) => {
          if (!finalRoute.includes(suggestion.name)) {
            finalRoute.push(suggestion.name);
          }
        });

      const nextCity = baseRoute[index + 1];
      if (!finalRoute.includes(nextCity) || nextCity === state.trip.returnDestination) {
        finalRoute.push(nextCity);
      }
    });

    return finalRoute;
  }

  function buildTransport(route, trip) {
    return route.slice(0, -1).map((from, index) => {
      const to = route[index + 1];
      const leg = createLeg(from, to, index, trip);
      const flightOptions = generateFlightOptions(leg, trip);
      const groundOptions = generateGroundOptions(leg, trip);
      const history = generatePriceHistory(flightOptions[0]?.bestOffer?.price || leg.baseFare, leg.seed);
      const forecast = forecastPrices(history);

      return {
        ...leg,
        flightOptions,
        groundOptions,
        history,
        forecast,
      };
    });
  }

  function createLeg(fromName, toName, index, trip) {
    const from = getCityProfile(fromName);
    const to = getCityProfile(toName);
    const distanceKm = haversine(from.lat, from.lon, to.lat, to.lon);
    const seed = `${fromName}-${toName}-${trip.startDate}-${trip.transportPriority}`;
    const rng = createRng(seed);
    const baseFare = Math.round(120 + distanceKm * 0.16 + rng() * 80);
    return {
      id: `${slugify(fromName)}-${slugify(toName)}-${index}`,
      index,
      from,
      to,
      fromName,
      toName,
      distanceKm,
      seed,
      baseFare,
    };
  }

  function generateFlightOptions(leg, trip) {
    const rng = createRng(`${leg.seed}:flight`);
    const requiredBagWeight = extractNumber(trip.bagWeight);

    return AIRLINES.map((airline, index) => {
      const aircraft = airline.aircraft[Math.floor(rng() * airline.aircraft.length)];
      const stops = leg.distanceKm > 2600 ? Math.floor(rng() * 2) : Math.floor(rng() * 2);
      const baggageAllowance = Math.max(0, airline.baseChecked + (rng() > 0.76 ? 1 : 0));
      const bagShortfall = Math.max(0, trip.bagCount - baggageAllowance);
      const baggageFee = bagShortfall * (48 + Math.max(0, requiredBagWeight - 20) * 2);
      const durationHours = Number(((leg.distanceKm / 820) * airline.pace + stops * 1.35 + 1.1 + rng()).toFixed(1));
      const fare = Math.round(leg.baseFare * (0.84 + index * 0.07 + rng() * 0.08));
      const offers = generateOffers("flight", fare + baggageFee, leg, airline.name);
      const bestOffer = selectBestTrustedOffer("flight", offers, {
        airline: airline.name,
        from: leg.fromName,
        to: leg.toName,
      });
      const baggageStatus = bagShortfall === 0 ? "good" : bagShortfall === 1 ? "warn" : "alert";

      return {
        airline: airline.name,
        aircraft,
        durationHours,
        stops,
        checkedAllowance: baggageAllowance,
        carryOn: airline.carryOn,
        baggageFee,
        bagShortfall,
        basePrice: fare,
        bestOffer,
        offers,
        baggageStatus,
      };
    })
      .sort((a, b) => compareByPriority(a, b, trip.transportPriority))
      .slice(0, 3);
  }

  function generateGroundOptions(leg, trip) {
    if (leg.distanceKm > 1450 || leg.from.region !== leg.to.region) {
      return [];
    }

    const rng = createRng(`${leg.seed}:ground`);
    const modes = ["train", "coach"];
    if (leg.from.geography.includes("coast") || leg.to.geography.includes("lagoon")) {
      modes.push("ferry");
    }

    return modes
      .slice(0, 3)
      .map((mode, index) => {
        const durationMultiplier = mode === "train" ? 0.012 : mode === "coach" ? 0.018 : 0.015;
        const durationHours = Number((2.2 + leg.distanceKm * durationMultiplier + rng() * 1.1).toFixed(1));
        const cost = Math.round(22 + leg.distanceKm * (mode === "coach" ? 0.08 : mode === "ferry" ? 0.11 : 0.12) + rng() * 24);
        const operator = mode === "train" ? "RailCanvas" : mode === "coach" ? "GetGoBus" : "TripNest";
        const offers = generateOffers("ground", cost, leg, operator);
        const bestOffer = selectBestTrustedOffer("ground", offers, {
          from: leg.fromName,
          to: leg.toName,
          operator,
        });
        return {
          mode,
          operator,
          durationHours,
          cost,
          bestOffer,
          scenic: mode !== "coach" || index === 0,
        };
      })
      .sort((a, b) => {
        if (trip.transportPriority === "Cheapest") {
          return a.cost - b.cost || a.durationHours - b.durationHours;
        }
        if (trip.transportPriority === "Fastest") {
          return a.durationHours - b.durationHours || a.cost - b.cost;
        }
        return a.durationHours - b.durationHours;
      });
  }

  function buildPlans(route, trip, legs) {
    const cityStops = route.slice(1, -1);
    const assignedSpecificPlaces = assignSpecificPlaces(cityStops, trip.specificPlaces);
    const themes = [
      {
        id: "balanced",
        name: "Balanced Explorer",
        description: "Good pacing, central hotels, and equal weight across landmarks, food, and rest.",
        emphasis: trip.attractionTypes.length ? trip.attractionTypes : ["Historical monuments", "Food and cuisine", "Cultural sites"],
      },
      {
        id: "iconic",
        name: "Landmark Sprint",
        description: "Front-loads major sights and faster transfers for travelers who want iconic coverage.",
        emphasis: ["Historical monuments", "Modern architecture", "Cultural sites"],
      },
      {
        id: "immersive",
        name: "Cuisine and Culture Drift",
        description: "Longer neighborhood stays, slower mornings, and more food-first recommendations.",
        emphasis: ["Food and cuisine", "Cultural sites", "Natural landscapes"],
      },
    ];

    return themes.map((theme, planIndex) => {
      const dayAllocation = allocateDays(cityStops, trip.tripDays, theme.emphasis);
      const startOffset = Math.min(planIndex, diffDays(trip.startDate, trip.endDate) + 1 - trip.tripDays);
      let cursor = addDays(trip.startDate, Math.max(0, startOffset));

      const cities = cityStops.map((cityName, cityIndex) => {
        const cityProfile = getCityProfile(cityName);
        const days = dayAllocation[cityIndex];
        const checkIn = cursor;
        const checkOut = addDays(cursor, Math.max(1, days - 1));
        cursor = addDays(checkOut, 1);

        const hotels = pickHotels(cityProfile, days, theme, trip);
        const attractions = pickAttractions(cityProfile, theme, trip, assignedSpecificPlaces[cityName] || []);
        const mapId = `${theme.id}-${slugify(cityName)}`;
        if (!state.mapStates[mapId]) {
          state.mapStates[mapId] = { scale: 1, x: 0, y: 0 };
        }

        return {
          name: cityName,
          profile: cityProfile,
          days,
          checkIn,
          checkOut,
          nights: Math.max(1, days - 1),
          hotels,
          attractions,
          mapId,
        };
      });

      const flightCost = legs.reduce((sum, leg) => sum + (leg.flightOptions[0]?.bestOffer?.price || 0), 0);
      const hotelCost = cities.reduce((sum, city) => sum + city.hotels[0].totalCost, 0);
      const attractionCost = cities.reduce((sum, city) => sum + city.attractions.slice(0, 2).reduce((subtotal, attraction) => subtotal + attraction.cost, 0), 0);
      const groundCost =
        legs.reduce((sum, leg) => sum + (leg.groundOptions[0]?.bestOffer?.price || 0), 0) +
        cities.reduce((sum, city) => sum + Math.round(city.profile.buffer * 0.16), 0);
      const buffer = Math.round(cityStops.reduce((sum, cityName) => sum + getCityProfile(cityName).buffer, 0) / cityStops.length) * trip.tripDays;

      return {
        id: theme.id,
        name: theme.name,
        description: theme.description,
        route,
        startDate: addDays(trip.startDate, Math.max(0, startOffset)),
        endDate: addDays(addDays(trip.startDate, Math.max(0, startOffset)), trip.tripDays - 1),
        theme,
        legs,
        cities,
        costBreakdown: {
          flights: flightCost,
          accommodation: hotelCost,
          ground: groundCost,
          attractions: attractionCost,
          buffer,
        },
        totalCost: flightCost + hotelCost + groundCost + attractionCost + buffer,
      };
    });
  }

  function allocateDays(cityStops, tripDays, emphasis) {
    const weights = cityStops.map((cityName) => {
      const city = getCityProfile(cityName);
      return (
        1 +
        countOverlap(city.types, emphasis) * 1.8 +
        getCount(memory.profile.destinations, cityName) * 0.8 +
        getCount(memory.profile.addedCities, cityName) * 1.2
      );
    });

    const days = new Array(cityStops.length).fill(1);
    let remaining = tripDays - cityStops.length;

    while (remaining > 0) {
      const scores = weights.map((weight, index) => weight / (days[index] + 0.75));
      const bestIndex = scores.indexOf(Math.max.apply(null, scores));
      days[bestIndex] += 1;
      remaining -= 1;
    }

    return days;
  }

  function pickHotels(cityProfile, days, theme, trip) {
    const nights = Math.max(1, days - 1);
    return cityProfile.hotels
      .map((hotel) => {
        const themeFit = countOverlap(hotel.fits, theme.emphasis) + countOverlap(hotel.fits, trip.attractionTypes);
        const learnedBoost = getCount(memory.profile.hotels, hotel.name);
        const offers = generateOffers("hotel", Math.round(hotel.rate * nights), { fromName: cityProfile.name, toName: cityProfile.name }, hotel.name);
        const bestOffer = selectBestTrustedOffer("hotel", offers, {
          city: cityProfile.name,
          hotel: hotel.name,
        });
        return {
          ...hotel,
          nightlyRate: hotel.rate,
          totalCost: Math.round(hotel.rate * nights),
          bestOffer,
          score: themeFit * 4 + learnedBoost,
        };
      })
      .sort((a, b) => b.score - a.score || a.nightlyRate - b.nightlyRate)
      .slice(0, 3);
  }

  function pickAttractions(cityProfile, theme, trip, mustSee) {
    const mustSeeEntries = mustSee.map((place) => createSpecificPlaceEntry(place, cityProfile));
    const curated = cityProfile.attractions
      .map((attraction) => {
        const score =
          countOverlap([attraction.type], theme.emphasis) * 8 +
          countOverlap([attraction.type], trip.attractionTypes) * 5 +
          getCount(memory.profile.savedAttractions, attraction.name) * 2;
        const offers = generateOffers("attraction", attraction.cost, { fromName: cityProfile.name, toName: cityProfile.name }, attraction.name);
        const bestOffer = selectBestTrustedOffer("attraction", offers, {
          city: cityProfile.name,
          attraction: attraction.name,
        });
        return {
          ...attraction,
          mustSee: false,
          bestOffer,
          score,
        };
      })
      .sort((a, b) => b.score - a.score || a.cost - b.cost);

    const merged = mustSeeEntries.concat(curated.filter((attraction) => !mustSee.some((place) => sameText(place, attraction.name))));
    return merged.slice(0, 4);
  }

  function createSpecificPlaceEntry(place, cityProfile) {
    const inferredType = cityProfile.types[0] || "Cultural sites";
    const estimatedCost = 18 + (hashCode(place) % 28);
    const offers = generateOffers("attraction", estimatedCost, { fromName: cityProfile.name, toName: cityProfile.name }, place);
    return {
      name: place,
      type: inferredType,
      cost: estimatedCost,
      hours: "Check venue schedule",
      mustSee: true,
      bestOffer: selectBestTrustedOffer("attraction", offers, {
        city: cityProfile.name,
        attraction: place,
      }),
    };
  }

  function assignSpecificPlaces(cityStops, places) {
    const assigned = {};
    cityStops.forEach((cityName) => {
      assigned[cityName] = [];
    });

    places.forEach((place, index) => {
      let matchedCity = cityStops.find((cityName) => {
        const profile = getCityProfile(cityName);
        return (
          sameText(cityName, place) ||
          profile.attractions.some((attraction) => sameText(attraction.name, place)) ||
          place.toLowerCase().includes(cityName.toLowerCase())
        );
      });

      if (!matchedCity) {
        matchedCity = cityStops[index % cityStops.length];
      }
      assigned[matchedCity].push(place);
    });

    return assigned;
  }

  function generateOffers(category, basePrice, context, label) {
    const rng = createRng(`${category}:${label}:${JSON.stringify(context)}`);
    const platforms = Object.keys(PLATFORM_LIBRARY).filter((name) => PLATFORM_LIBRARY[name].categories.includes(category));

    return platforms.map((platform) => {
      const variance = PLATFORM_LIBRARY[platform].trusted ? 0.08 : -0.1;
      const price = Math.max(0, Math.round(basePrice * (1 + variance + (rng() - 0.5) * 0.1)));
      return {
        platform,
        price,
        url: buildBookingUrl(category, context, platform, label),
      };
    });
  }

  function selectBestTrustedOffer(category, offers, context) {
    const trustedOffers = offers
      .filter((offer) => {
        const platform = PLATFORM_LIBRARY[offer.platform];
        return platform && platform.trusted && !memory.flaggedPlatforms[offer.platform];
      })
      .sort((a, b) => a.price - b.price);

    if (trustedOffers.length) {
      return trustedOffers[0];
    }

    const fallbackPlatform = category === "flight" ? `${context.airline || "Carrier"} direct` : "Direct booking";
    return {
      platform: fallbackPlatform,
      price: offers[0]?.price || 0,
      url: buildBookingUrl(category, context, fallbackPlatform, context.hotel || context.attraction || context.airline || context.operator || ""),
    };
  }

  function generatePriceHistory(basePrice, seed) {
    const rng = createRng(`${seed}:history`);
    const history = [];
    let price = basePrice * (0.88 + rng() * 0.12);

    for (let day = -20; day <= 0; day += 1) {
      price = Math.max(60, price * (1 + (rng() - 0.45) * 0.08));
      history.push({
        label: `${Math.abs(day)}d`,
        day,
        price: Math.round(price),
      });
    }

    return history;
  }

  function forecastPrices(history) {
    const returns = history.slice(1).map((point, index) => Math.log(point.price / history[index].price));
    const drift = average(returns);
    const volatility = Math.max(0.01, standardDeviation(returns));
    const simulations = 160;
    const lastPrice = history[history.length - 1].price;
    const projected = [];

    for (let day = 1; day <= 7; day += 1) {
      const simulated = [];
      for (let sim = 0; sim < simulations; sim += 1) {
        const rng = createRng(`${lastPrice}:${day}:${sim}`);
        const move = drift + (rng() - 0.5) * volatility * 2;
        const next = Math.max(55, lastPrice * Math.exp(move * day));
        simulated.push(next);
      }
      simulated.sort((a, b) => a - b);
      projected.push({
        day,
        mean: Math.round(average(simulated)),
        low: Math.round(percentile(simulated, 0.1)),
        high: Math.round(percentile(simulated, 0.9)),
      });
    }

    const finalProjection = projected[projected.length - 1];
    const trend = finalProjection.mean > lastPrice + 8 ? "up" : finalProjection.mean < lastPrice - 8 ? "down" : "flat";
    const confidence = Math.max(52, Math.min(89, Math.round(100 - ((finalProjection.high - finalProjection.low) / finalProjection.mean) * 100)));

    return { projected, trend, confidence };
  }

  function respondAsGeorge(prompt) {
    const lowered = prompt.toLowerCase();

    if (lowered.includes("packing")) {
      if (!state.trip || !state.plans.length) {
        addGeorgeMessage("assistant", "Build at least one itinerary first and I’ll tailor a packing list to dates, weather cues, transport modes, and activities.");
        return;
      }
      state.packingList = buildPackingList();
      renderPackingList();
      addGeorgeMessage("assistant", "I drafted a packing list below using your climate, activity, transport, and document needs.");
      return;
    }

    if (lowered.includes("city") || lowered.includes("suggest")) {
      const response = state.suggestions.length
        ? state.suggestions
            .map((suggestion) => `${suggestion.name} fits because it keeps the route efficient and overlaps with ${suggestion.matchingTags.join(", ").toLowerCase() || "your recent behavior"}.`)
            .join(" ")
        : "Once you enter a route, I’ll score optional stopovers by geography fit, attraction overlap, and what you usually keep or skip.";
      addGeorgeMessage("assistant", response);
      return;
    }

    if (lowered.includes("compliance") || lowered.includes("prohibited")) {
      addGeorgeMessage(
        "assistant",
        "Use the Prohibited items button inside any plan card. The panel separates destination-level concerns from transport-level restrictions and links out to official sources that should be wired to live refresh in production."
      );
      return;
    }

    if (lowered.includes("how") || lowered.includes("use")) {
      addGeorgeMessage(
        "assistant",
        "Start with the trip brief on the left, accept or decline optional city additions, then generate itineraries. The sidebar tracks what the planner has learned from your choices, and you can flag suspicious booking platforms at any time."
      );
      return;
    }

    if (lowered.includes("why") && state.plans.length) {
      const topPlan = state.plans[0];
      addGeorgeMessage(
        "assistant",
        `${topPlan.name} is currently the most balanced option: it spreads ${state.trip.tripDays} days across ${topPlan.cities.length} cities, keeps hotels close to your top attraction types, and uses trusted lowest-price booking platforms.`
      );
      return;
    }

    addGeorgeMessage(
      "assistant",
      "I can keep it practical: ask me for a packing list, an explanation of route suggestions, or help reading the transport and compliance panels."
    );
  }

  function buildPackingList() {
    const routeCities = state.plans[0]?.cities || [];
    const activityTypes = unique(routeCities.flatMap((city) => city.attractions.map((attraction) => attraction.type)));
    const transportModes = unique(state.legs.flatMap((leg) => [leg.flightOptions.length ? "flight" : "", leg.groundOptions[0]?.mode || ""]).filter(Boolean));
    const items = [];

    routeCities.forEach((city) => {
      items.push({
        name: `${city.profile.name}: layers for ${city.profile.climate}`,
        detail: `Weather cue: ${city.profile.climate}. Geography: ${city.profile.geography}.`,
      });
    });

    if (activityTypes.includes("Natural landscapes")) {
      items.push({ name: "Trail-ready shoes", detail: "Useful for scenic walks, hill districts, or waterfront routes." });
    }
    if (activityTypes.includes("Historical monuments") || activityTypes.includes("Cultural sites")) {
      items.push({ name: "Lightweight day bag", detail: "Keeps museum-day essentials close without overpacking." });
    }
    if (activityTypes.includes("Food and cuisine")) {
      items.push({ name: "Fold-flat tote", detail: "Helpful for markets, bakery runs, and snack stops." });
    }
    if (transportModes.includes("flight")) {
      items.push({ name: "Compression pouch and eye mask", detail: "Makes long-haul or overnight flights easier." });
    }
    if (transportModes.some((mode) => ["train", "coach", "ferry"].includes(mode))) {
      items.push({ name: "Portable power bank", detail: "Useful for intercity transfers and mobile tickets." });
    }

    items.push({ name: "Passport", detail: "Required for international travel and border checks." });
    items.push({ name: "Visa confirmation if needed", detail: "Check requirements for each destination before departure." });
    items.push({ name: "Travel insurance details", detail: "Keep policy number and emergency contact accessible." });
    items.push({ name: "Vaccination or health records if required", detail: "Only for destinations or entry rules that request them." });

    const uniqueItems = uniqueBy(items, "name");
    return uniqueItems;
  }

  function renderPackingList() {
    if (!state.packingList.length) {
      elements.packingListPanel.classList.add("hidden");
      return;
    }

    elements.packingListPanel.classList.remove("hidden");
    elements.packingListItems.innerHTML = state.packingList
      .map((item) => {
        const checked = getCount(memory.profile.packingItems, item.name) > 0;
        return `
          <div class="packing-item">
            <label>
              <input type="checkbox" data-item="${escapeHtml(item.name)}" ${checked ? "checked" : ""} />
              <strong>${escapeHtml(item.name)}</strong>
            </label>
            <p class="summary-note">${escapeHtml(item.detail)}</p>
          </div>
        `;
      })
      .join("");
  }

  function renderSuggestions() {
    if (!state.trip) {
      elements.suggestionSection.classList.add("hidden");
      return;
    }

    elements.suggestionSection.classList.remove("hidden");
    elements.suggestionCards.innerHTML = state.suggestions.length
      ? state.suggestions
          .map((suggestion) => {
            const accepted = state.acceptedSuggestions.some((item) => item.name === suggestion.name);
            return `
              <article class="suggestion-card">
                <div>
                  <div class="transport-topline">
                    <h3>${escapeHtml(suggestion.name)}</h3>
                    <span class="metric-badge ${accepted ? "good" : suggestion.declined ? "alert" : "warn"}">
                      ${accepted ? "Accepted" : suggestion.declined ? "Declined" : "Optional"}
                    </span>
                  </div>
                  <p class="summary-note">${escapeHtml(suggestion.reason)}</p>
                </div>
                <div class="quick-prompts">
                  ${suggestion.matchingTags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
                </div>
                <div class="plan-actions">
                  <button class="ghost-button" type="button" data-action="accept" data-suggestion-name="${escapeHtml(suggestion.name)}">Add city</button>
                  <button class="ghost-button" type="button" data-action="decline" data-suggestion-name="${escapeHtml(suggestion.name)}">Skip for now</button>
                </div>
              </article>
            `;
          })
          .join("")
      : `<div class="summary-card"><h3>No extra city matched strongly enough</h3><p class="summary-note">The route already looks tight, or the geography is too stretched for a helpful intermediate stop.</p></div>`;
  }

  function renderTransport() {
    if (!state.legs.length) {
      elements.transportSection.classList.add("hidden");
      return;
    }

    elements.transportSection.classList.remove("hidden");
    elements.transportContent.innerHTML = state.legs
      .map(
        (leg) => `
          <article class="transport-card">
            <div class="transport-topline">
              <div>
                <h3>${escapeHtml(leg.fromName)} to ${escapeHtml(leg.toName)}</h3>
                <p class="summary-note">${Math.round(leg.distanceKm)} km · ${escapeHtml(leg.from.airport)} to ${escapeHtml(leg.to.airport)}</p>
              </div>
              <div class="quick-prompts">
                <span class="status-pill">Forecast ${leg.forecast.trend}</span>
                <span class="status-pill">${leg.forecast.confidence}% confidence</span>
              </div>
            </div>

            <div class="flight-list">
              ${leg.flightOptions
                .map(
                  (option) => `
                    <div class="flight-row">
                      <div class="flight-meta">
                        <div>
                          <strong>${escapeHtml(option.airline)}</strong>
                          <p class="summary-note">${escapeHtml(option.aircraft)} · ${option.durationHours}h · ${option.stops} stop${option.stops === 1 ? "" : "s"}</p>
                        </div>
                        <div class="quick-prompts">
                          <span class="metric-badge ${option.baggageStatus}">${option.checkedAllowance} checked</span>
                          <span class="tag">${escapeHtml(option.carryOn)}</span>
                          <span class="platform-pill">${escapeHtml(option.bestOffer.platform)}</span>
                        </div>
                      </div>
                      <div class="link-row">
                        <p class="summary-note">
                          ${formatCurrency(option.bestOffer.price)} total
                          ${option.baggageFee ? `· includes ${formatCurrency(option.baggageFee)} baggage adjustment` : "· baggage fit is clean"}
                        </p>
                        <div class="plan-actions">
                          <a class="deep-link" href="${option.bestOffer.url}" target="_blank" rel="noreferrer">Purchase link</a>
                          ${
                            PLATFORM_LIBRARY[option.bestOffer.platform]
                              ? `<button class="ghost-button" type="button" data-action="flag-platform" data-platform="${escapeHtml(option.bestOffer.platform)}">Flag platform</button>`
                              : ""
                          }
                        </div>
                      </div>
                    </div>
                  `
                )
                .join("")}
            </div>

            <div class="ground-list">
              ${
                leg.groundOptions.length
                  ? leg.groundOptions
                      .map(
                        (option) => `
                          <div class="ground-row">
                            <div class="ground-meta">
                              <div>
                                <strong>${titleCase(option.mode)}</strong>
                                <p class="summary-note">${option.durationHours}h · ${formatCurrency(option.bestOffer.price)} · booked via ${escapeHtml(option.bestOffer.platform)}</p>
                              </div>
                              <span class="tag">${option.scenic ? "Scenic-worthy" : "Utility transfer"}</span>
                            </div>
                          </div>
                        `
                      )
                      .join("")
                  : `<div class="ground-row"><strong>No practical public surface connection</strong><p class="summary-note">This leg is better handled by air for the selected date window.</p></div>`
              }
            </div>

            <canvas class="forecast-chart" id="chart-${leg.id}" width="800" height="220"></canvas>
            <p class="disclaimer">Prototype note: chart uses seeded historical pricing and a Monte Carlo style 7-day forecast so the planning flow works offline.</p>
          </article>
        `
      )
      .join("");

    requestAnimationFrame(() => {
      state.legs.forEach((leg) => {
        const canvas = document.getElementById(`chart-${leg.id}`);
        if (canvas) {
          drawForecastChart(canvas, leg.history, leg.forecast.projected);
        }
      });
    });
  }

  function renderPlans() {
    if (!state.plans.length) {
      elements.plansSection.classList.add("hidden");
      return;
    }

    elements.plansSection.classList.remove("hidden");
    elements.plansContent.innerHTML = state.plans
      .map((plan) => {
        const breakdown = plan.costBreakdown;
        return `
          <article class="plan-card">
            <div class="plan-topline">
              <div>
                <h3>${escapeHtml(plan.name)}</h3>
                <p class="summary-note">${escapeHtml(plan.description)}</p>
              </div>
              <div class="quick-prompts">
                <span class="status-pill">${formatDate(plan.startDate)} to ${formatDate(plan.endDate)}</span>
                <span class="status-pill">${formatCurrency(plan.totalCost)} est. total</span>
              </div>
            </div>

            <div class="cost-grid">
              ${renderCostCell("Flights", breakdown.flights)}
              ${renderCostCell("Accommodation", breakdown.accommodation)}
              ${renderCostCell("Ground", breakdown.ground)}
              ${renderCostCell("Attractions", breakdown.attractions)}
              ${renderCostCell("Meals + incidentals", breakdown.buffer)}
            </div>

            <div class="flight-list">
              ${plan.legs
                .map(
                  (leg) => `
                    <div class="flight-row">
                      <div class="flight-meta">
                        <div>
                          <strong>${escapeHtml(leg.fromName)} to ${escapeHtml(leg.toName)}</strong>
                          <p class="summary-note">${Math.round(leg.distanceKm)} km · ${leg.flightOptions.length} curated ticket options</p>
                        </div>
                        <span class="tag">Cheapest trusted link surfaced</span>
                      </div>
                      <div class="flight-list">
                        ${leg.flightOptions
                          .map(
                            (option) => `
                              <div class="hotel-card">
                                <div class="hotel-meta">
                                  <div>
                                    <strong>${escapeHtml(option.airline)}</strong>
                                    <p class="summary-note">${escapeHtml(option.aircraft)} · ${option.durationHours}h · ${option.stops} stop${option.stops === 1 ? "" : "s"}</p>
                                  </div>
                                  <span class="metric-badge ${option.baggageStatus}">${option.checkedAllowance} checked</span>
                                </div>
                                <p class="summary-note">${escapeHtml(option.carryOn)} · ${escapeHtml(option.bestOffer.platform)} · ${formatCurrency(option.bestOffer.price)}</p>
                                <div class="link-row">
                                  <a class="deep-link" href="${option.bestOffer.url}" target="_blank" rel="noreferrer">Deep-link to buy</a>
                                  ${
                                    PLATFORM_LIBRARY[option.bestOffer.platform]
                                      ? `<button class="ghost-button" type="button" data-action="flag-platform" data-platform="${escapeHtml(option.bestOffer.platform)}">Flag platform</button>`
                                      : ""
                                  }
                                </div>
                              </div>
                            `
                          )
                          .join("")}
                      </div>
                    </div>
                  `
                )
                .join("")}
            </div>

            <div class="city-grid">
              ${plan.cities
                .map(
                  (city) => `
                    <article class="city-card">
                      <div class="city-topline">
                        <div>
                          <h4>${escapeHtml(city.name)}</h4>
                          <p class="summary-note">${formatDate(city.checkIn)} to ${formatDate(city.checkOut)} · ${city.days} day${city.days === 1 ? "" : "s"} · ${city.profile.climate}</p>
                        </div>
                        <div class="quick-prompts">
                          ${city.profile.types.slice(0, 3).map((type) => `<span class="tag">${escapeHtml(type)}</span>`).join("")}
                        </div>
                      </div>

                      <div class="hotel-grid">
                        ${city.hotels
                          .map((hotel) => {
                            const isSelected = state.selectedHotels[`${plan.id}:${city.name}`] === hotel.name;
                            return `
                              <div class="hotel-card">
                                <h5>${escapeHtml(hotel.name)}</h5>
                                <p class="summary-note">${escapeHtml(hotel.area)} · ${formatCurrency(hotel.nightlyRate)}/night · ${formatCurrency(hotel.totalCost)} total</p>
                                <p class="summary-note">Best trusted rate via ${escapeHtml(hotel.bestOffer.platform)}</p>
                                <div class="link-row">
                                  <a class="deep-link" href="${hotel.bestOffer.url}" target="_blank" rel="noreferrer">Hotel link</a>
                                  <button class="ghost-button" type="button" data-action="book-hotel" data-plan-id="${plan.id}" data-city="${escapeHtml(city.name)}" data-hotel="${escapeHtml(hotel.name)}">${isSelected ? "Held" : "Hold room"}</button>
                                </div>
                              </div>
                            `;
                          })
                          .join("")}
                      </div>

                      <div class="attraction-grid">
                        ${city.attractions
                          .map((attraction) => {
                            const isSaved = Boolean(state.savedAttractions[`${plan.id}:${city.name}:${attraction.name}`]);
                            return `
                              <div class="attraction-card">
                                <h5>${escapeHtml(attraction.name)} ${attraction.mustSee ? '<span class="tag">Must-see</span>' : ""}</h5>
                                <p class="summary-note">${escapeHtml(attraction.type)} · ${formatCurrency(attraction.cost)} · ${escapeHtml(attraction.hours)}</p>
                                <div class="link-row">
                                  <a class="deep-link" href="${attraction.bestOffer.url}" target="_blank" rel="noreferrer">Ticket link</a>
                                  <button class="ghost-button" type="button" data-action="save-attraction" data-plan-id="${plan.id}" data-city="${escapeHtml(city.name)}" data-attraction="${escapeHtml(attraction.name)}">${isSaved ? "Saved" : "Save activity"}</button>
                                </div>
                              </div>
                            `;
                          })
                          .join("")}
                      </div>

                      <div class="map-card">
                        <div class="transport-topline">
                          <h5>Interactive safety map</h5>
                          <div class="map-toolbar">
                            <button class="map-button" type="button" data-action="map-zoom-in" data-map-id="${city.mapId}">+</button>
                            <button class="map-button" type="button" data-action="map-zoom-out" data-map-id="${city.mapId}">-</button>
                            <button class="map-button" type="button" data-action="map-left" data-map-id="${city.mapId}">←</button>
                            <button class="map-button" type="button" data-action="map-right" data-map-id="${city.mapId}">→</button>
                            <button class="map-button" type="button" data-action="map-up" data-map-id="${city.mapId}">↑</button>
                            <button class="map-button" type="button" data-action="map-down" data-map-id="${city.mapId}">↓</button>
                          </div>
                        </div>
                        ${renderSafetyMap(city)}
                        <div class="legend">
                          <span class="safety-pill low">Green · low risk</span>
                          <span class="safety-pill medium">Yellow · moderate</span>
                          <span class="safety-pill high">Red · elevated</span>
                        </div>
                      </div>
                    </article>
                  `
                )
                .join("")}
            </div>

            <div class="plan-actions">
              <button class="primary-button" type="button" data-action="open-compliance" data-plan-id="${plan.id}">Open prohibited items panel</button>
            </div>
            <p class="disclaimer">Prototype note: safety layers, platform trust, and compliance data are modeled for demo use in this offline build and should be connected to live feeds before production booking.</p>
          </article>
        `;
      })
      .join("");
  }

  function renderSummaries() {
    renderStatusPills();
    renderRouteSummary();
    renderLearningSummary();
    renderTrustSummary();
  }

  function renderStatusPills() {
    const learnedCities = Object.keys(memory.profile.destinations).length;
    const flaggedCount = Object.keys(memory.flaggedPlatforms).length;
    const acceptedCount = state.acceptedSuggestions.length;
    const packingSignals = Object.values(memory.profile.packingItems).filter((value) => value > 0).length;

    elements.statusPills.innerHTML = `
      <span class="status-pill">${learnedCities} learned cities</span>
      <span class="status-pill">${flaggedCount} flagged platforms</span>
      <span class="status-pill">${acceptedCount} added stop${acceptedCount === 1 ? "" : "s"}</span>
      <span class="status-pill">${packingSignals} packing signals</span>
    `;
  }

  function renderRouteSummary() {
    if (!state.trip) {
      elements.routeSummary.innerHTML = `
        <div class="summary-card">
          <h3>Route snapshot</h3>
          <p class="summary-note">Enter an origin, destinations, date range, and trip duration to unlock suggestions and itineraries.</p>
        </div>
      `;
      return;
    }

    const route = buildFinalRoute();
    elements.routeSummary.innerHTML = `
      <div class="summary-card">
        <h3>Current route</h3>
        <div class="route-flow">
          ${route
            .map(
              (city, index) => `
                <div class="route-chip">
                  <strong>${index === 0 ? "Origin" : index === route.length - 1 ? "Return" : "Stop " + index}</strong>
                  <span>${escapeHtml(city)}</span>
                </div>
              `
            )
            .join("")}
        </div>
        <p class="summary-note">${state.trip.tripDays} travel days inside ${formatDate(state.trip.startDate)} to ${formatDate(state.trip.endDate)}.</p>
      </div>
      <div class="summary-card">
        <h3>Preference profile in this trip</h3>
        <div class="quick-prompts">
          ${state.trip.attractionTypes.length ? state.trip.attractionTypes.map((type) => `<span class="tag">${escapeHtml(type)}</span>`).join("") : '<span class="tag">Open preference mix</span>'}
        </div>
        <p class="summary-note">Transport priority: ${escapeHtml(state.trip.transportPriority)} · Bags: ${state.trip.bagCount} at ${escapeHtml(state.trip.bagWeight)} each.</p>
      </div>
    `;
  }

  function renderLearningSummary() {
    const topTypes = topKeys(memory.profile.attractionTypes, 3);
    const topCities = topKeys(memory.profile.destinations, 4);
    const topHotels = topKeys(memory.profile.hotels, 2);

    elements.learningSummary.innerHTML = `
      <div class="summary-card">
        <h3>Personal learning layer</h3>
        <p class="summary-note">Future city and attraction ranking gets weighted by what you choose, skip, save, and hold.</p>
        <div class="quick-prompts">
          ${(topTypes.length ? topTypes : ["No preferences learned yet"]).map((type) => `<span class="tag">${escapeHtml(type)}</span>`).join("")}
        </div>
      </div>
      <div class="summary-card">
        <h3>Top learned cities</h3>
        <p class="summary-note">${topCities.length ? topCities.map((city) => escapeHtml(city)).join(", ") : "No city choices recorded yet."}</p>
      </div>
      <div class="summary-card">
        <h3>Hotel lean</h3>
        <p class="summary-note">${topHotels.length ? topHotels.map((hotel) => escapeHtml(hotel)).join(", ") : "Hold a room in a plan to teach the hotel selector."}</p>
      </div>
    `;
  }

  function renderTrustSummary() {
    const flagged = Object.entries(memory.flaggedPlatforms);
    const trustedLive = Object.entries(PLATFORM_LIBRARY)
      .filter(([, platform]) => platform.trusted)
      .map(([name]) => name);

    elements.trustSummary.innerHTML = `
      <div class="trust-card">
        <h3>Trust database</h3>
        <p class="summary-note">Only the cheapest verified trusted platform is surfaced for flights, hotels, attractions, and ground transport.</p>
        <div class="trust-stack">
          <div>
            <strong>Trusted pool</strong>
            <p class="summary-note">${trustedLive.join(", ")}</p>
          </div>
          <div>
            <strong>Excluded platforms</strong>
            <p class="summary-note">${flagged.length ? flagged.map(([name, details]) => `${name} (${details.reason})`).join(", ") : "None flagged yet."}</p>
          </div>
        </div>
      </div>
    `;
  }

  function renderComplianceModal(plan) {
    const transportRestrictions = unique(
      plan.legs.flatMap((leg) => {
        const items = [
          "Compressed gas, fireworks, and large lithium battery packs can be rejected by air carriers.",
          "Sharp objects, replica weapons, and some sporting gear may need checked handling or may be refused.",
        ];
        if (leg.groundOptions.length) {
          items.push("Hazardous chemicals, fuel canisters, and oversized battery devices may be banned on rail and coach operators.");
        }
        return items;
      })
    );

    return `
      <div class="compliance-card">
        <h3>${escapeHtml(plan.name)}</h3>
        <p class="summary-note">Advisory prototype. Connect live regulation feeds before production use, and confirm details directly with carriers and official customs sources.</p>
      </div>
      ${plan.cities
        .map(
          (city) => `
            <section class="compliance-card">
              <div class="compliance-columns">
                <div>
                  <h3>${escapeHtml(city.name)}</h3>
                  <p class="summary-note">${escapeHtml(city.profile.geography)}</p>
                </div>
                <span class="tag">${escapeHtml(city.profile.country)}</span>
              </div>
              <ul>
                ${city.profile.compliance.destination.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
              </ul>
              <p class="summary-note">Sources: ${city.profile.compliance.sources.map((source) => `<a class="deep-link" href="${source.url}" target="_blank" rel="noreferrer">${escapeHtml(source.label)}</a>`).join(" · ")}</p>
            </section>
          `
        )
        .join("")}
      <section class="compliance-card">
        <h3>Transport mode restrictions</h3>
        <ul>
          ${transportRestrictions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
        <p class="summary-note">Sources: <a class="deep-link" href="https://www.tsa.gov/travel/security-screening/whatcanibring/all-list" target="_blank" rel="noreferrer">TSA prohibited items</a> · <a class="deep-link" href="https://www.iata.org/en/programs/cargo/dgr/" target="_blank" rel="noreferrer">IATA dangerous goods guidance</a></p>
      </section>
    `;
  }

  function renderComplianceModalFromService(plan, compliance) {
    const destinationPanels = Array.isArray(compliance.destinationPanels) ? compliance.destinationPanels : [];
    const transportPanel = compliance.transportPanel || { items: [], sources: [] };
    return `
      <div class="compliance-card">
        <h3>${escapeHtml(plan.name)}</h3>
        <p class="summary-note">
          ${compliance.live ? "Live refresh completed using current official web sources when available." : "Using the seeded restrictions fallback because live refresh is unavailable."}
        </p>
      </div>
      ${destinationPanels
        .map(
          (panel) => `
            <section class="compliance-card">
              <div class="compliance-columns">
                <div>
                  <h3>${escapeHtml(panel.city)}</h3>
                  <p class="summary-note">${escapeHtml(panel.country)}</p>
                </div>
                <span class="tag">Destination rules</span>
              </div>
              <ul>
                ${(panel.items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
              </ul>
              <p class="summary-note">
                Sources:
                ${(panel.sources || [])
                  .map((source) => `<a class="deep-link" href="${source.url}" target="_blank" rel="noreferrer">${escapeHtml(source.label || source.title || source.url)}</a>`)
                  .join(" · ")}
              </p>
            </section>
          `
        )
        .join("")}
      <section class="compliance-card">
        <h3>Transport mode restrictions</h3>
        <ul>
          ${(transportPanel.items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
        <p class="summary-note">
          Sources:
          ${(transportPanel.sources || [])
            .map((source) => `<a class="deep-link" href="${source.url}" target="_blank" rel="noreferrer">${escapeHtml(source.label || source.title || source.url)}</a>`)
            .join(" · ")}
        </p>
      </section>
    `;
  }

  function renderSafetyMap(city) {
    const mapState = state.mapStates[city.mapId] || { scale: 1, x: 0, y: 0 };
    const transform = `translate(${mapState.x}px, ${mapState.y}px) scale(${mapState.scale})`;
    return `
      <div class="map-viewport">
        <div class="map-scene" style="transform:${transform}">
          ${city.profile.neighborhoods
            .map(
              (area) => `
                <div class="map-cell ${riskClass(area.risk)}" style="left:${area.x}px; top:${area.y}px; width:${area.w}px; height:${area.h}px;">
                  <strong>${escapeHtml(area.name)}</strong>
                  <small>${riskLabel(area.risk)}</small>
                </div>
              `
            )
            .join("")}
        </div>
      </div>
    `;
  }

  function updateMapState(mapId, action) {
    const current = state.mapStates[mapId] || { scale: 1, x: 0, y: 0 };
    const next = { ...current };

    if (action === "map-zoom-in") {
      next.scale = Math.min(1.9, current.scale + 0.15);
    }
    if (action === "map-zoom-out") {
      next.scale = Math.max(0.8, current.scale - 0.15);
    }
    if (action === "map-left") {
      next.x -= 18;
    }
    if (action === "map-right") {
      next.x += 18;
    }
    if (action === "map-up") {
      next.y -= 18;
    }
    if (action === "map-down") {
      next.y += 18;
    }

    state.mapStates[mapId] = next;
  }

  function drawForecastChart(canvas, history, forecast) {
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const allValues = history.map((point) => point.price).concat(forecast.flatMap((point) => [point.low, point.high]));
    const minPrice = Math.min.apply(null, allValues) - 15;
    const maxPrice = Math.max.apply(null, allValues) + 15;
    const chartLeft = 34;
    const chartRight = width - 18;
    const chartTop = 18;
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

    const series = history.concat(
      forecast.map((point) => ({
        price: point.mean,
      }))
    );

    const xForIndex = (index, length) => chartLeft + (chartWidth / (length - 1)) * index;
    const yForPrice = (price) => chartBottom - ((price - minPrice) / (maxPrice - minPrice)) * chartHeight;

    ctx.fillStyle = "rgba(217, 110, 66, 0.15)";
    ctx.beginPath();
    forecast.forEach((point, index) => {
      const x = xForIndex(index + history.length - 1, series.length);
      const y = yForPrice(point.high);
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    for (let index = forecast.length - 1; index >= 0; index -= 1) {
      const point = forecast[index];
      const x = xForIndex(index + history.length - 1, series.length);
      const y = yForPrice(point.low);
      ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "#116b72";
    ctx.lineWidth = 3;
    ctx.beginPath();
    history.forEach((point, index) => {
      const x = xForIndex(index, series.length);
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
      const x = xForIndex(index + history.length - 1, series.length);
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
    ctx.fillText(`History`, chartLeft, height - 8);
    ctx.fillStyle = "#d96e42";
    ctx.fillText(`7-day forecast`, chartLeft + 72, height - 8);
  }

  function hydrateForm(trip) {
    const source = trip || {
      origin: "",
      returnDestination: "",
      destinations: "",
      startDate: "",
      endDate: "",
      tripDays: "",
      attractionTypes: [],
      specificPlaces: [],
      bagCount: 1,
      bagDimensions: '22" x 14" x 9"',
      bagWeight: "18 lb",
      transportPriority: "Cheapest",
      flightInfo: "Show",
    };

    document.getElementById("origin").value = source.origin || "";
    document.getElementById("returnDestination").value = source.returnDestination || "";
    document.getElementById("destinations").value = Array.isArray(source.destinations) ? source.destinations.join(", ") : source.destinations || "";
    document.getElementById("startDate").value = source.startDate || "";
    document.getElementById("endDate").value = source.endDate || "";
    document.getElementById("tripDays").value = source.tripDays || "";
    document.getElementById("specificPlaces").value = Array.isArray(source.specificPlaces) ? source.specificPlaces.join(", ") : source.specificPlaces || "";
    document.getElementById("bagCount").value = source.bagCount ?? 1;
    document.getElementById("bagDimensions").value = source.bagDimensions || '22" x 14" x 9"';
    document.getElementById("bagWeight").value = source.bagWeight || "18 lb";
    document.getElementById("transportPriority").value = source.transportPriority || "Cheapest";
    document.getElementById("flightInfo").value = source.flightInfo || "Show";

    document.querySelectorAll('input[name="attractionType"]').forEach((input) => {
      input.checked = Array.isArray(source.attractionTypes) && source.attractionTypes.includes(input.value);
    });
  }

  async function resetMemory() {
    if (!window.confirm("Reset learned preferences, flagged platforms, and saved trip memory for this workspace?")) {
      return;
    }
    try {
      const data = await apiPost("/api/reset", {});
      syncMemory(data.memorySnapshot);
    } catch (error) {
      localStorage.removeItem(STORAGE_KEY);
      memory = loadMemory();
    }
    state.trip = null;
    state.suggestions = [];
    state.acceptedSuggestions = [];
    state.legs = [];
    state.plans = [];
    state.selectedHotels = {};
    state.savedAttractions = {};
    state.packingList = [];
    elements.suggestionSection.classList.add("hidden");
    elements.transportSection.classList.add("hidden");
    elements.plansSection.classList.add("hidden");
    elements.packingListPanel.classList.add("hidden");
    elements.formMessage.textContent = "Learned memory reset.";
    hydrateForm(null);
    renderSummaries();
    addGeorgeMessage("assistant", "Memory reset. New route decisions will start a fresh preference profile.");
  }

  async function bootstrapFromServer() {
    try {
      const data = await apiPost("/api/bootstrap", {});
      syncMemory(data.memorySnapshot);
      if (memory.lastTrip) {
        hydrateForm(memory.lastTrip);
      }
      renderSummaries();
    } catch (error) {
      saveMemory();
    }
  }

  async function refreshPlansFromBackend() {
    const data = await apiPost("/api/plan", {
      trip: state.trip,
      acceptedSuggestions: state.acceptedSuggestions.map((item) => item.name),
    });
    state.trip = data.trip || state.trip;
    state.acceptedSuggestions = data.acceptedSuggestions || state.acceptedSuggestions;
    state.legs = data.legs || [];
    state.plans = data.plans || [];
    syncMemory(data.memorySnapshot);
    renderTransport();
    renderPlans();
    renderSummaries();
  }

  async function syncFeedback(eventType, entityValue, delta = 1, extra = {}) {
    try {
      const data = await apiPost("/api/feedback", {
        eventType,
        entityValue,
        delta,
        ...extra,
      });
      syncMemory(data.memorySnapshot);
    } catch (error) {
      saveMemory();
    }
  }

  async function sendGeorgePrompt(prompt) {
    try {
      const data = await apiPost("/api/george/chat", {
        prompt,
        trip: state.trip,
        legs: state.legs,
        plans: state.plans,
      });
      if (Array.isArray(data.packingList)) {
        state.packingList = data.packingList;
        renderPackingList();
      }
      addGeorgeMessage("assistant", formatGeorgeResponse(data));
      return;
    } catch (error) {
      respondAsGeorge(prompt);
    }
  }

  async function apiPost(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sessionId,
        ...payload,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Request failed for ${path}`);
    }
    return response.json();
  }

  function syncMemory(snapshot) {
    if (!snapshot) {
      return;
    }
    memory = snapshot;
    saveMemory();
  }

  function getClientSessionId() {
    const existing = localStorage.getItem(CLIENT_SESSION_KEY);
    if (existing) {
      return existing;
    }
    const generated =
      "atlas-" +
      Math.random().toString(36).slice(2, 10) +
      "-" +
      Date.now().toString(36);
    localStorage.setItem(CLIENT_SESSION_KEY, generated);
    return generated;
  }

  function collectTransportModes(plan) {
    const modes = ["flight"];
    plan.legs.forEach((leg) => {
      leg.groundOptions.forEach((option) => {
        modes.push(option.mode);
      });
    });
    return unique(modes);
  }

  function formatGeorgeResponse(data) {
    if (!data || !data.message) {
      return "I can help with route logic, packing, and compliance details.";
    }
    if (!Array.isArray(data.sources) || !data.sources.length) {
      return data.message;
    }
    const sourceText = data.sources
      .slice(0, 2)
      .map((source) => source.label || source.title || source.url)
      .filter(Boolean)
      .join(", ");
    return `${data.message} Sources: ${sourceText}.`;
  }

  function loadMemory() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return {
        flaggedPlatforms: {
          FlashFare: {
            source: "seed",
            reason: PLATFORM_LIBRARY.FlashFare.reason,
          },
          BargainRoost: {
            source: "seed",
            reason: PLATFORM_LIBRARY.BargainRoost.reason,
          },
          TicketBlitz: {
            source: "seed",
            reason: PLATFORM_LIBRARY.TicketBlitz.reason,
          },
          ...(parsed.flaggedPlatforms || {}),
        },
        profile: {
          attractionTypes: {},
          destinations: {},
          transportPriority: {},
          hotels: {},
          savedAttractions: {},
          addedCities: {},
          skippedCities: {},
          packingItems: {},
          ...(parsed.profile || {}),
        },
        globalSignals: {
          attractionTypes: {},
          destinations: {},
          transportPriority: {},
          hotels: {},
          savedAttractions: {},
          addedCities: {},
          ...(parsed.globalSignals || {}),
        },
        lastTrip: parsed.lastTrip || null,
      };
    } catch (error) {
      return {
        flaggedPlatforms: {
          FlashFare: {
            source: "seed",
            reason: PLATFORM_LIBRARY.FlashFare.reason,
          },
          BargainRoost: {
            source: "seed",
            reason: PLATFORM_LIBRARY.BargainRoost.reason,
          },
          TicketBlitz: {
            source: "seed",
            reason: PLATFORM_LIBRARY.TicketBlitz.reason,
          },
        },
        profile: {
          attractionTypes: {},
          destinations: {},
          transportPriority: {},
          hotels: {},
          savedAttractions: {},
          addedCities: {},
          skippedCities: {},
          packingItems: {},
        },
        globalSignals: {
          attractionTypes: {},
          destinations: {},
          transportPriority: {},
          hotels: {},
          savedAttractions: {},
          addedCities: {},
        },
        lastTrip: null,
      };
    }
  }

  function saveMemory() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(memory));
  }

  function addGeorgeMessage(role, content) {
    state.georgeMessages.push({
      role,
      content,
      timestamp: new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }),
    });
    elements.georgeMessages.innerHTML = state.georgeMessages
      .slice(-10)
      .map(
        (message) => `
          <div class="message ${message.role}">
            <div class="message-meta">${message.role === "assistant" ? "George" : "You"} · ${message.timestamp}</div>
            <div>${escapeHtml(message.content)}</div>
          </div>
        `
      )
      .join("");
    elements.georgeMessages.scrollTop = elements.georgeMessages.scrollHeight;
  }

  function getCityProfile(name) {
    if (CITY_LIBRARY[name]) {
      return CITY_LIBRARY[name];
    }

    const seed = Math.abs(hashCode(name));
    const fallback = {
      name,
      country: "Custom route",
      region: "Flexible",
      airport: name.slice(0, 3).toUpperCase(),
      lat: 20 + (seed % 50),
      lon: -30 + ((seed >> 3) % 120),
      types: ["Cultural sites", "Food and cuisine", "Historical monuments"],
      climate: "variable seasonal weather",
      geography: "mixed urban surroundings",
      buffer: 70,
      attractions: [
        { name: `${name} Old Quarter`, type: "Historical monuments", cost: 20, hours: "09:00-18:00" },
        { name: `${name} Central Market`, type: "Food and cuisine", cost: 18, hours: "10:00-21:00" },
        { name: `${name} Waterfront Walk`, type: "Cultural sites", cost: 0, hours: "Open all day" },
      ],
      hotels: [
        { name: `${name} Atlas House`, area: "Central district", rate: 190, fits: ["Cultural sites"] },
        { name: `${name} Current Hotel`, area: "Old town", rate: 176, fits: ["Historical monuments"] },
        { name: `${name} Table Inn`, area: "Market quarter", rate: 164, fits: ["Food and cuisine"] },
      ],
      neighborhoods: [
        { name: "Old town", risk: "low", x: 40, y: 40, w: 100, h: 70 },
        { name: "Museum quarter", risk: "low", x: 150, y: 46, w: 96, h: 66 },
        { name: "Transit belt", risk: "high", x: 86, y: 132, w: 102, h: 58 },
        { name: "Market district", risk: "medium", x: 20, y: 128, w: 86, h: 56 },
        { name: "Riverfront", risk: "medium", x: 194, y: 126, w: 86, h: 56 },
      ],
      compliance: {
        destination: [
          "Check customs, medication, food import, and drone rules for this destination before travel.",
          "Historic venues often restrict large bags, tripods, or sharp items inside.",
          "Transport operators may reject hazardous materials, oversized batteries, or fuel canisters.",
        ],
        sources: [
          { label: "Official customs lookup", url: "https://www.iatatravelcentre.com/" },
        ],
      },
    };

    CITY_LIBRARY[name] = fallback;
    return fallback;
  }

  function buildSuggestionReason(suggestion, from, to) {
    const tagText = suggestion.matchingTags.length ? suggestion.matchingTags.join(", ").toLowerCase() : "your learned travel pattern";
    return `${suggestion.name} sits neatly between ${from} and ${to}, while also matching ${tagText}.`;
  }

  function scoreRouteFit(from, to, candidate) {
    const fromDistance = haversine(from.lat, from.lon, candidate.lat, candidate.lon);
    const toDistance = haversine(to.lat, to.lon, candidate.lat, candidate.lon);
    const sameRegionBoost = from.region === candidate.region || to.region === candidate.region ? 24 : 0;
    return sameRegionBoost + 1400 / (fromDistance + 120) + 1400 / (toDistance + 120);
  }

  function compareByPriority(a, b, priority) {
    if (priority === "Cheapest") {
      return a.bestOffer.price - b.bestOffer.price || a.durationHours - b.durationHours;
    }
    if (priority === "Fastest") {
      return a.durationHours - b.durationHours || a.bestOffer.price - b.bestOffer.price;
    }
    return a.durationHours - b.durationHours || a.bestOffer.price - b.bestOffer.price;
  }

  function renderCostCell(label, value) {
    return `
      <div class="cost-cell">
        <span class="summary-note">${label}</span>
        <strong>${formatCurrency(value)}</strong>
      </div>
    `;
  }

  function buildBookingUrl(category, context, platform, label) {
    const queryParts = [platform, category];
    if (context.from) queryParts.push(`${context.from} to ${context.to}`);
    if (context.fromName) queryParts.push(`${context.fromName} to ${context.toName}`);
    if (context.city) queryParts.push(context.city);
    if (context.hotel) queryParts.push(context.hotel);
    if (context.attraction) queryParts.push(context.attraction);
    if (label) queryParts.push(label);
    return `https://www.google.com/search?q=${encodeURIComponent(queryParts.join(" "))}`;
  }

  function addDays(dateString, amount) {
    const date = new Date(`${dateString}T12:00:00`);
    date.setDate(date.getDate() + amount);
    return date.toISOString().slice(0, 10);
  }

  function diffDays(start, end) {
    return Math.round((new Date(`${end}T12:00:00`) - new Date(`${start}T12:00:00`)) / DAY_MS);
  }

  function haversine(lat1, lon1, lat2, lon2) {
    const toRad = (value) => (value * Math.PI) / 180;
    const earth = 6371;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return earth * c;
  }

  function createRng(seedString) {
    let seed = hashCode(seedString);
    return function () {
      seed |= 0;
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashCode(value) {
    let hash = 0;
    for (let index = 0; index < value.length; index += 1) {
      hash = (hash << 5) - hash + value.charCodeAt(index);
      hash |= 0;
    }
    return hash;
  }

  function average(values) {
    if (!values.length) return 0;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }

  function percentile(values, amount) {
    const index = Math.max(0, Math.min(values.length - 1, Math.floor(values.length * amount)));
    return values[index];
  }

  function standardDeviation(values) {
    if (!values.length) return 0;
    const mean = average(values);
    return Math.sqrt(average(values.map((value) => Math.pow(value - mean, 2))));
  }

  function titleCase(value) {
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  function formatCurrency(value) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(value || 0);
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    }).format(new Date(`${value}T12:00:00`));
  }

  function parseList(value) {
    return value
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function unique(values) {
    return Array.from(new Set(values));
  }

  function uniqueBy(values, key) {
    const seen = new Set();
    return values.filter((item) => {
      const value = item[key];
      if (seen.has(value)) {
        return false;
      }
      seen.add(value);
      return true;
    });
  }

  function sameText(a, b) {
    return a.trim().toLowerCase() === b.trim().toLowerCase();
  }

  function countOverlap(a, b) {
    return a.filter((value) => b.includes(value)).length;
  }

  function getFieldValue(id) {
    return document.getElementById(id).value.trim();
  }

  function getCount(source, key) {
    return Number(source[key] || 0);
  }

  function incrementCounter(source, key, step = 1) {
    source[key] = Math.max(0, Number(source[key] || 0) + step);
  }

  function topKeys(source, limit) {
    return Object.entries(source)
      .filter(([, value]) => value > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([key]) => key);
  }

  function extractNumber(value) {
    const match = String(value).match(/(\d+(\.\d+)?)/);
    return match ? Number(match[1]) : 0;
  }

  function slugify(value) {
    return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  }

  function riskClass(risk) {
    return risk === "low" ? "low" : risk === "medium" ? "medium" : "high";
  }

  function riskLabel(risk) {
    return risk === "low" ? "low risk" : risk === "medium" ? "moderate" : "elevated";
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }
})();
