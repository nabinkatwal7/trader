(function () {
  const theme = {
    layout: {
      background: { type: "solid", color: "#fbfcfb" },
      textColor: "#5a6b63",
      fontFamily: "IBM Plex Mono, monospace",
    },
    grid: {
      vertLines: { color: "#e4ebe6" },
      horzLines: { color: "#e4ebe6" },
    },
    rightPriceScale: { borderColor: "#c9d5ce" },
    timeScale: { borderColor: "#c9d5ce", timeVisible: false },
    crosshair: { mode: 0 },
  };

  const PALETTE = ["#0f6e56", "#1a7a45", "#9a6700", "#3d6b9a", "#b42318", "#5a6b63", "#2a9d8f", "#6d4c41"];

  function makeChart(el, height) {
    const chart = LightweightCharts.createChart(el, {
      ...theme,
      width: el.clientWidth,
      height: height || 360,
    });
    const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
    ro.observe(el);
    return chart;
  }

  window.PaperCharts = {
    candles(el, candles, markers) {
      if (!el || !window.LightweightCharts) return null;
      el.innerHTML = "";
      const chart = makeChart(el, el.dataset.height ? Number(el.dataset.height) : 380);
      const series = chart.addCandlestickSeries({
        upColor: "#1a7a45",
        downColor: "#b42318",
        borderUpColor: "#1a7a45",
        borderDownColor: "#b42318",
        wickUpColor: "#1a7a45",
        wickDownColor: "#b42318",
      });
      series.setData(candles || []);
      if (markers && markers.length) series.setMarkers(markers);
      chart.timeScale().fitContent();
      return chart;
    },

    equity(el, equity, closes, markers, starting) {
      if (!el || !window.LightweightCharts) return null;
      el.innerHTML = "";
      const chart = makeChart(el, el.dataset.height ? Number(el.dataset.height) : 320);
      const eq = chart.addAreaSeries({
        lineColor: "#0f6e56",
        topColor: "rgba(15, 110, 86, 0.28)",
        bottomColor: "rgba(15, 110, 86, 0.02)",
        lineWidth: 2,
        priceScaleId: "right",
      });
      eq.setData((equity || []).map((d) => ({ time: d.time, value: d.value })));

      if (closes && closes.length) {
        const px = chart.addLineSeries({
          color: "#8aa399",
          lineWidth: 1,
          priceScaleId: "left",
        });
        chart.priceScale("left").applyOptions({ visible: true, borderColor: "#c9d5ce" });
        px.setData(closes);
        if (markers && markers.length) px.setMarkers(markers);
      }

      if (starting) {
        eq.createPriceLine({
          price: starting,
          color: "#9a6700",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "start",
        });
      }
      chart.timeScale().fitContent();
      return chart;
    },

    multiEquity(el, seriesList) {
      if (!el || !window.LightweightCharts || !seriesList) return null;
      el.innerHTML = "";
      const chart = makeChart(el, el.dataset.height ? Number(el.dataset.height) : 360);
      seriesList.forEach((s, i) => {
        const line = chart.addLineSeries({
          color: PALETTE[i % PALETTE.length],
          lineWidth: 2,
          title: s.name,
        });
        line.setData((s.equity || []).map((d) => ({ time: d.time, value: d.value })));
      });
      chart.timeScale().fitContent();
      return chart;
    },

    async loadWatch(el, symbol, days) {
      if (!el) return;
      el.classList.add("chart-loading");
      try {
        const res = await fetch(`/api/ohlc/?symbol=${encodeURIComponent(symbol)}&days=${days || 90}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "chart failed");
        this.candles(el, data.candles, data.markers);
        document.querySelectorAll("[data-watch-label]").forEach((n) => (n.textContent = data.symbol));
        const chg = document.querySelector("[data-watch-change]");
        if (chg && data.last != null) {
          const pct = data.change_pct || 0;
          chg.textContent = `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
          chg.className = "mono " + (pct >= 0 ? "gain" : "loss");
        }
      } catch (err) {
        el.innerHTML = `<p class="chart-error">${err.message}</p>`;
      } finally {
        el.classList.remove("chart-loading");
      }
    },
  };

  document.addEventListener("DOMContentLoaded", () => {
    const watch = document.getElementById("watch-chart");
    if (watch) {
      PaperCharts.loadWatch(watch, watch.dataset.symbol, watch.dataset.days || 90);
    }
    const bt = document.getElementById("backtest-chart");
    if (bt && window.__BACKTEST_CHART__) {
      const d = window.__BACKTEST_CHART__;
      PaperCharts.equity(bt, d.equity, d.closes, d.markers, d.starting);
    }
    const an = document.getElementById("analytics-chart");
    if (an && window.__ANALYTICS_CHART__) {
      const d = window.__ANALYTICS_CHART__;
      PaperCharts.equity(an, d.equity, null, null, d.starting);
    }
    const cmp = document.getElementById("compare-chart");
    if (cmp && window.__COMPARE_CHART__) {
      PaperCharts.multiEquity(cmp, window.__COMPARE_CHART__);
    }

    document.querySelectorAll("[data-range]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const days = btn.getAttribute("data-range");
        const chart = document.getElementById("watch-chart");
        if (!chart || !window.PaperCharts) return;
        chart.dataset.days = days;
        document.querySelectorAll("[data-range]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        PaperCharts.loadWatch(chart, chart.dataset.symbol, days);
      });
    });
  });
})();
