// Where the app reads from. Data is same-origin on Pages; in dev we read the live Pages data (CORS: *).
export const DATA_BASE: string = import.meta.env.DEV
  ? "https://ishansurdi.github.io/rainsure/data"
  : `${import.meta.env.BASE_URL}data`;
export const API_BASE = "https://rain-trust-api.onrender.com";
export const REPO_URL = "https://github.com/ishansurdi/rainsure";
export const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
// OpenFreeMap style layers that draw country, disputed and admin borders; removed so only our
// Natural Earth India-POV lines are drawn (DECISIONS.md D32, D41; layer ids read from the style on 2026-11-06).
export const HIDDEN_STYLE_LAYERS = ["boundary_2", "boundary_3", "boundary_disputed"];
// Place labels drawn by OpenFreeMap for parts of Jammu & Kashmir and Ladakh administered by Pakistan. Hidden so
// the map follows India's official view (D32, D41). Found by listing every rendered label over Kashmir, Aksai Chin
// and Arunachal Pradesh on 2026-11-06 (D63); variants included.
export const HIDDEN_PLACE_NAMES = ["Azad Kashmir", "Azad Jammu and Kashmir", "Gilgit-Baltistan", "Gilgit Baltistan",
  "Northern Areas", "Aksai Chin", "South Tibet", "Zangnan"];
