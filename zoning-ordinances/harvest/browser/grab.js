// Chrome-side harvest helper. Paste into the code-host tab (javascript tool or
// DevTools console) after each full page load; defines window.formxGrab.
//
//   await formxGrab.grab(slug, doc, urls)   same-origin fetch of each URL, exact
//                                           bytes -> sink (eCode360, American
//                                           Legal, municipal.codes: server-rendered)
//   await formxGrab.grabDom(slug, doc)      wait until #codesContent stops growing,
//                                           send its rendered outerHTML (Municode:
//                                           client-rendered)
//
// Every part carries the sha256 computed here, before anything leaves the
// page. ingest.py recomputes it on the received bytes and rejects any mismatch.
// The sink (python3 sink.py) listens on http://127.0.0.1:8770; Chrome must have
// "Local network access: Allow" for the code-host site (Site settings).
(() => {
  const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
  const b64 = buf => {
    const bytes = new Uint8Array(buf);
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  };
  const part = async (url, buf, http) => ({
    url, http, sha256: hex(await crypto.subtle.digest("SHA-256", buf)), b64: b64(buf),
  });
  // pause via the sink: hidden tabs throttle timers to about once a minute
  const sleep = ms => fetch("http://127.0.0.1:8770/wait?ms=" + ms).then(r => r.json()).catch(() => new Promise(r => setTimeout(r, ms)));
  window.formxGrab = {
    async fetchParts(urls) {
      const out = [];
      for (const url of urls) {
        const res = await fetch(url, { credentials: "include" });
        out.push(await part(url, await res.arrayBuffer(), res.status));
      }
      return out;
    },
    async domPart(selector, url) {
      const el = document.querySelector(selector);
      if (!el) throw new Error("no element " + selector);
      return part(url || location.href, new TextEncoder().encode(el.outerHTML).buffer, 200);
    },
    async send(payload, port = 8770) {
      const timeout = new Promise((_, rej) => setTimeout(() => rej(new Error("sink timeout (local network access not allowed?)")), 60000));
      const res = await Promise.race([fetch(`http://127.0.0.1:${port}/save`, {
        method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "text/plain" },
      }), timeout]);
      return res.json();
    },
    async grab(slug, doc, urls, transport = "chrome-same-origin-fetch") {
      return this.send({ slug, doc, transport, parts: await this.fetchParts(urls) });
    },
    async settle(sel = "#codesContent", maxMs = 30000) {
      let prev = -1;
      const t0 = Date.now();
      while (Date.now() - t0 < maxMs) {
        const el = document.querySelector(sel);
        const n = el ? el.innerHTML.length : 0;
        if (n > 1000 && n === prev) return n;
        prev = n;
        await sleep(1500);
      }
      return -1;
    },
    async grabDom(slug, doc, sel = "#codesContent") {
      if (await this.settle(sel) < 0) return { ok: false, error: "content never settled" };
      return this.send({ slug, doc, transport: "chrome-rendered-dom", parts: [await this.domPart(sel)] });
    },
    // Municode: in-app navigation keeps this script alive across pages. Click
    // the TOC link for nodeId (or push the route), then wait until the node's
    // own chunk is rendered and the content stops growing.
    async gotoNode(nodeId, maxMs = 30000) {
      const a = [...document.querySelectorAll('a[href*="nodeId="]')]
        .find(x => x.getAttribute("href").split("nodeId=")[1].split("&")[0] === nodeId);
      if (a) a.click();
      else { history.pushState({}, "", location.pathname + "?nodeId=" + nodeId); window.dispatchEvent(new PopStateEvent("popstate")); }
      const t0 = Date.now();
      let prev = -1;
      while (Date.now() - t0 < maxMs) {
        await sleep(1500);
        const el = document.querySelector("#codesContent");
        const hit = el && el.querySelector('div.chunk[id="c_' + nodeId + '"]');
        const n = el ? el.innerHTML.length : 0;
        // a "Mini TOC" page lists the node's children instead of their text:
        // refuse it, the target must name the child nodes instead
        if (hit && n === prev) return /^Mini TOC/.test(document.title) ? { via: "mini-toc", n: -1 } : { via: a ? "click" : "pushState", n };
        prev = n;
      }
      return { via: a ? "click" : "pushState", n: -1 };
    },
    // One document assembled from several Municode pages (one part per node).
    async grabNodes(slug, doc, nodeIds) {
      const parts = [], log = [];
      for (const id of nodeIds) {
        const r = await this.gotoNode(id);
        log.push(id.split("_").pop() + ":" + r.via + ":" + r.n);
        if (r.n < 0) return { ok: false, error: "node never rendered " + id, log };
        parts.push(await this.domPart("#codesContent", location.origin + location.pathname + "?nodeId=" + id));
      }
      const res = await this.send({ slug, doc, transport: "chrome-rendered-dom", parts, host_marker: this.marker() });
      res.log = log;
      return res;
    },
    // The host's own change marker as shown on the page (Municode "VERSION: <date>
    // (CURRENT)", eCode360 "Last updated"/"current through" wording).
    marker() {
      const m = document.body.innerText.match(/VERSION:\s*[A-Z]{3}\s+\d{1,2},\s+\d{4}[^\n]*|(current through|last updated|up to date through)[^\n]{0,120}/i);
      return m ? m[0].trim() : null;
    },
    // American Legal (codelibrary.amlegal.com): click the TOC link for a node
    // id ("0-0-0-6218"), wait until that node's box is rendered and the
    // section body stops growing, keep the rendered .codenav__section-body.
    async gotoAm(nodeId, maxMs = 30000) {
      const a = [...document.querySelectorAll(".codenav__toc a, a[href]")].find(x => (x.getAttribute("href") || "").endsWith("/" + nodeId));
      if (!a) return { n: -1, via: "no-link" };
      a.click();
      const t0 = Date.now();
      let prev = -1;
      while (Date.now() - t0 < maxMs) {
        await sleep(1500);
        const b = document.querySelector(".codenav__section-body");
        const n = b ? b.innerHTML.length : 0;
        if (location.pathname.endsWith("/" + nodeId) && b && b.querySelector("#rid-" + nodeId) && n === prev) return { n, via: "click" };
        prev = n;
      }
      return { n: -1, via: "timeout" };
    },
    // American Legal renders the first few sections and lazy-loads the rest
    // on scroll: scroll until every section the chapter lists in #section-0
    // is rendered, or give up (the page is then refused, not saved short).
    async loadAllAm(maxRounds = 40) {
      const s0 = document.querySelector("#section-0");
      const listed = s0 ? s0.innerText.split("\n").filter(l => /^\s*\d+[.\-]\d/.test(l)).length : 0;
      const count = () => document.querySelectorAll('.codenav__section-body [id^="section-"]').length - 1;
      let last = -1, still = 0;
      for (let i = 0; i < maxRounds && count() < listed; i++) {
        // the section body is its own scroll container; scroll it to the end
        // and fire the scroll event its lazy loader listens for
        const sc = document.querySelector(".codenav__section-body");
        sc.scrollTop = sc.scrollHeight;
        sc.dispatchEvent(new Event("scroll"));
        window.scrollTo(0, document.body.scrollHeight);
        await sleep(1200);
        if (count() === last) { if (++still > 6) break; } else { still = 0; last = count(); }
      }
      return { listed, rendered: count() };
    },
    async grabAm(slug, doc, nodeIds) {
      const parts = [], log = [];
      for (const id of nodeIds) {
        const r = location.pathname.endsWith("/" + id) && document.querySelector("#rid-" + id) ? { n: 1, via: "here" } : await this.gotoAm(id);
        if (r.n >= 0) {
          const c = await this.loadAllAm();
          r.via += "/" + c.rendered + "of" + c.listed;
          if (c.listed && c.rendered < c.listed) r.n = -1;
        }
        log.push(id + ":" + r.via + ":" + r.n);
        if (r.n < 0) return { ok: false, error: "node never rendered " + id, log };
        parts.push(await this.domPart(".codenav__section-body", location.href));
      }
      const m = document.body.innerText.match(/(\d{4} S-\d+|Supp\. No\. \d+ - \d{4}) \(current\)/);
      const res = await this.send({ slug, doc, transport: "chrome-rendered-dom", parts, host_marker: m ? m[0].trim() : null });
      res.log = log;
      return res;
    },
    // Start a long job without awaiting it (the JavaScript tool times out at
    // 45 s but the page keeps running); poll window.formxResult afterwards.
    //   formxGrab.bg("grabNodes", "sonoma-county", "adu-ordinance", [ids])
    bg(method, ...args) {
      window.formxResult = null;
      this[method](...args).then(r => { window.formxResult = r; }, e => { window.formxResult = { ok: false, error: e.message }; });
      return "started";
    },
    // Municode TOC links currently in the DOM, as "nodeId | label".
    toc(filter = /\| (Chapter|Article|Part|Division|Title|Appendix)/i) {
      return [...new Set([...document.querySelectorAll('a[href*="nodeId="]')]
        .map(a => a.getAttribute("href").split("nodeId=")[1].split("&")[0] + " | " + a.textContent.trim().replace(/\s+/g, " ").slice(0, 80)))]
        .filter(t => filter.test(t));
    },
  };
  return "formxGrab ready";
})();
