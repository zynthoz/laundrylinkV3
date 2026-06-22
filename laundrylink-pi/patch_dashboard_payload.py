import re

with open("templates/dashboard.html", "r") as f:
    content = f.read()

def replace_func(func_name, new_code):
    global content
    pattern = r"function " + func_name + r"\(\)\s*\{.*?(?=\n\s*function |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_code + "\n\n" + content[match.end():]
        print(f"Replaced {func_name}")
    else:
        print(f"Could not find {func_name}")

new_payload_func = """function buildDashboardJobOrderPayload() {
      const nameEl = document.getElementById('dashboard-jo-customer-name');
      const phoneEl = document.getElementById('dashboard-jo-customer-phone');
      const washEl = document.getElementById('dashboard-jo-wash-qty');
      const dryEl = document.getElementById('dashboard-jo-dry-qty');
      const washModeEl = document.getElementById('dashboard-jo-wash-mode');
      const dryModeEl = document.getElementById('dashboard-jo-dry-mode');
      const gcashEl = document.getElementById('dashboard-jo-paid-by-gcash');
      const promoEl = document.getElementById('dashboard-jo-promo');
      const printReceiptEl = document.getElementById('dashboard-jo-print-receipt');

      if (!nameEl || !phoneEl || !washEl || !dryEl || !washModeEl || !dryModeEl || !gcashEl) {
        return null;
      }

      const customerName = String(nameEl.value || '').trim();
      const phoneDigits = normalizeDigits(phoneEl.value || '');
      const washQty = parseInt(String(washEl.value || '0').trim() || '0', 10);
      const dryQty = parseInt(String(dryEl.value || '0').trim() || '0', 10);
      const productQty = getDashboardJoProductQtyTotal();
      const serviceQty = getDashboardJoServiceQtyTotal();
      const productAmount = getDashboardJoProductAmountTotal();
      const serviceAmount = getDashboardJoServiceAmountTotal();
      const washMode = String(washModeEl.value || 'standard').trim().toLowerCase();
      const dryMode = String(dryModeEl.value || 'standard').trim().toLowerCase();
      const paidByGcash = !!gcashEl.checked;
      const printReceipt = printReceiptEl ? !!printReceiptEl.checked : true;
      const promoId = promoEl ? promoEl.value : null;
      
      let promoName = null;
      if (promoId) {
         const promo = dashboardPromos.find(p => p.id === promoId);
         if (promo) {
             promoName = promo.name;
             if (productQty !== promo.product_qty || serviceQty !== promo.service_qty) {
                 alert(`The selected promo package requires exactly ${promo.product_qty} product(s) and ${promo.service_qty} service(s). You currently have ${productQty} product(s) and ${serviceQty} service(s) selected.`);
                 return null;
             }
         }
      }

      if (!customerName) {
        alert('Customer name is required.');
        return null;
      }
      if (phoneDigits && (phoneDigits.length < 10 || phoneDigits.length > 11)) {
        alert('Customer phone must be 10 to 11 digits.');
        return null;
      }
      if (Number.isNaN(washQty) || Number.isNaN(dryQty) || Number.isNaN(productQty) || washQty < 0 || dryQty < 0 || productQty < 0 || (washQty + dryQty) < 1) {
        alert('Wash/Dry quantities must be whole numbers, and at least one must be greater than zero.');
        return null;
      }

      // Collect items
      const items = [];
      Object.keys(dashboardJoProductQuantities).forEach(id => {
          const qty = parseInt(dashboardJoProductQuantities[id] || 0, 10);
          if (qty > 0) {
              const product = (productCatalog || []).find(p => String(p.id).trim() === id);
              if (product) {
                  items.push({
                      item_type: 'product',
                      item_id: product.id,
                      item_name: product.name,
                      quantity: qty,
                      unit_price: parseInt(product.unit_price || 0, 10),
                      unit_cost: parseInt(product.unit_cost || 0, 10)
                  });
              }
          }
      });
      Object.keys(dashboardJoServiceQuantities).forEach(id => {
          const qty = parseInt(dashboardJoServiceQuantities[id] || 0, 10);
          if (qty > 0) {
              const service = (serviceCatalog || []).find(s => String(s.id).trim() === id);
              if (service) {
                  items.push({
                      item_type: 'service',
                      item_id: service.id,
                      item_name: service.name,
                      quantity: qty,
                      unit_price: parseInt(service.unit_price || 0, 10),
                      unit_cost: parseInt(service.unit_cost || 0, 10)
                  });
              }
          }
      });

      return {
        location_id: currentLocationId,
        customer: {
          name: customerName,
          phone: phoneDigits || null,
        },
        wash_qty: washQty,
        dry_qty: dryQty,
        wash_mode: washMode,
        dry_mode: dryMode,
        product_qty: productQty,
        service_qty: serviceQty,
        product_amount: productAmount,
        service_amount: serviceAmount,
        paid_by_gcash: paidByGcash,
        promo_id: promoId,
        promo_name: promoName,
        print_receipt: printReceipt,
        items: items
      };
    }"""

replace_func("buildDashboardJobOrderPayload", new_payload_func)

with open("templates/dashboard.html", "w") as f:
    f.write(content)

