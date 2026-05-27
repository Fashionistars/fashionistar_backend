(function () {
  function formatNgn(value) {
    return new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency: "NGN",
      minimumFractionDigits: 2,
    }).format(value || 0);
  }

  function readPayload() {
    const node = document.getElementById("fashionistar-admin-dashboard-data");
    if (!node) return null;
    try {
      return JSON.parse(node.textContent || "{}");
    } catch (_error) {
      return null;
    }
  }

  function renderChart(id, labels, data, label, color) {
    const canvas = document.getElementById(id);
    if (!canvas || typeof Chart === "undefined") return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [{
          label,
          data,
          borderColor: color,
          backgroundColor: color + "22",
          fill: true,
          tension: 0.35,
          pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: { grid: { display: false } },
          y: { grid: { color: "#ECE6D6" } },
        },
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const payload = readPayload();
    if (!payload) return;

    const revenueTotal = (payload.daily_revenue || []).reduce((sum, value) => sum + Number(value || 0), 0);
    const vendorTotal = (payload.new_vendors || []).reduce((sum, value) => sum + Number(value || 0), 0);

    const revenueNode = document.getElementById("fsn-daily-revenue-total");
    const vendorNode = document.getElementById("fsn-new-vendors-total");
    const lowStockNode = document.getElementById("fsn-low-stock-count");
    const kycNode = document.getElementById("fsn-kyc-pending-count");
    const lowStockList = document.getElementById("fsn-low-stock-list");

    if (revenueNode) revenueNode.textContent = formatNgn(revenueTotal);
    if (vendorNode) vendorNode.textContent = String(vendorTotal);
    if (lowStockNode) lowStockNode.textContent = String(payload.low_stock_count || 0);
    if (kycNode) kycNode.textContent = String(payload.kyc_pending_count || 0);

    if (lowStockList) {
      lowStockList.innerHTML = "";
      const items = payload.low_stock_items || [];
      if (!items.length) {
        lowStockList.innerHTML = "<li>No low-stock alerts right now.</li>";
      } else {
        items.forEach(function (item) {
          const li = document.createElement("li");
          li.textContent = `${item.title} · ${item.stock_qty} left${item.vendor ? ` · ${item.vendor}` : ""}`;
          lowStockList.appendChild(li);
        });
      }
    }

    renderChart(
      "fsnDailyRevenueChart",
      payload.chart_labels || [],
      payload.daily_revenue || [],
      "Daily Revenue",
      "#01454A"
    );
    renderChart(
      "fsnNewVendorsChart",
      payload.chart_labels || [],
      payload.new_vendors || [],
      "New Vendors",
      "#FDA600"
    );
  });
})();
