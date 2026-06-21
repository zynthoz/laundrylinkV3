// config.js
// Edit this file for each shop deployment
const CONFIG = {
  PI_BASE_URL: (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:') 
    ? 'http://127.0.0.1:5000/api' 
    : window.location.origin + '/api',
  LOCATION_ID: "local",
  SHOP_NAME: "LaundryLink",
};
