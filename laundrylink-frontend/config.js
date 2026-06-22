// config.js
// Edit this file for each shop deployment
const CONFIG = {
  PI_BASE_URL: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? 'http://localhost:5000' 
    : window.location.origin,
  LOCATION_ID: "local",
  SHOP_NAME: "LaundryLink",
};
