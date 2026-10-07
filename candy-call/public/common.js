// Live connection to the Candy Call server, shared by the booth and team pages.
window.CandyCall = (function () {
  let offset = 0; // server clock minus this device's clock, in ms

  function now() { return Date.now() + offset; }

  function connect(onState, onConnection) {
    let es;
    let retry;
    function open() {
      es = new EventSource("/events");
      es.onopen = () => onConnection(true);
      es.onmessage = (e) => {
        const s = JSON.parse(e.data);
        offset = s.now * 1000 - Date.now();
        onState(s);
      };
      es.onerror = () => {
        onConnection(false);
        // Browsers retry on their own, but a phone waking from sleep can leave
        // the stream closed for good; reopen it ourselves in that case.
        if (es.readyState === EventSource.CLOSED) {
          clearTimeout(retry);
          retry = setTimeout(open, 3000);
        }
      };
    }
    open();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && es.readyState === EventSource.CLOSED) open();
    });
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
    return data;
  }

  function ago(ts) {
    if (!ts) return "";
    const s = Math.max(0, Math.floor((now() - ts * 1000) / 1000));
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60);
    return m < 60 ? m + "m" : Math.floor(m / 60) + "h " + (m % 60) + "m";
  }

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) { return null; }
  }

  async function keepAwake() {
    try {
      if (!navigator.wakeLock) return;
      await navigator.wakeLock.request("screen");
      document.addEventListener("visibilitychange", async () => {
        if (document.visibilityState === "visible") {
          try { await navigator.wakeLock.request("screen"); } catch (e) {}
        }
      });
    } catch (e) {}
  }

  return { connect, post, now, ago, store, keepAwake };
})();
