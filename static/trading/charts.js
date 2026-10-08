/* TradingView lightweight-charts helpers */
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

  function makeChart(el, height) {
    const chart = LightweightCharts.createChart(el, {
      ...theme,
      width: el.clientWidth,
      height: height || 360,
    });
    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth });
    });
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
          title: "Price",
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

    async loadWatch(el, symbol, days) {
      if (!el) return;
      el.classList.add("chart-loading");
      try {
        const res = await fetch(`/api/ohlc/?symbol=${encodeURIComponent(symbol)}&days=${days || 90}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "chart failed");
        this.candles(el, data.candles, data.markers);
        const label = document.querySelector("[data-watch-label]");
        if (label) label.textContent = data.symbol;
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
  });
})();
