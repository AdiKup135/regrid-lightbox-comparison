// Change markers for the Chrome-only hosts. Run once per host family in a
// tab already open on that host (same-origin fetches), paste the returned
// array into obs.json, then: python3 check_markers.py --observed obs.json
//
// eCode360 (any ecode360.com tab): the current version's "Includes
// legislation through ..." line embedded in each chapter page.
// municipal.codes (atherton.municipal.codes tab): "current through Ordinance N".
// American Legal: the version label ("Supp. No. 82 - 2026 (current)",
// "2026 S-20 (current)") is only in the rendered page: open the code and read
// it (formxMarkers.amlegalHere()).
(() => {
  const ECODE = {
    "sunnyvale": "https://ecode360.com/42732718", "mill-valley": "https://ecode360.com/44319622",
    "sausalito": "https://ecode360.com/47135313", "napa": "https://ecode360.com/43397584",
    "menlo-park": "https://ecode360.com/47187943", "los-altos-hills": "https://ecode360.com/44000032",
    "healdsburg": "https://ecode360.com/48343648",
  };
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const unescape = s => { const t = document.createElement("textarea"); t.innerHTML = s; return t.value; };
  window.formxMarkers = {
    async ecode360() {
      const out = [];
      for (const [slug, url] of Object.entries(ECODE)) {
        const html = unescape(await (await fetch(url)).text());
        const m = [...html.matchAll(/\{[^{}]*"displayDate":"([^"]+)"[^{}]*\}/g)].find(x => x[0].includes('"current":true'));
        out.push({ slug, marker: m ? m[1] : null });
        await sleep(2500);
      }
      return out;
    },
    async municipalCodes(slug = "atherton", path = "/Code/17") {
      const html = await (await fetch(path)).text();
      const m = html.match(/current through Ordinance [^<.]{0,60}\.?/);
      return [{ slug, marker: m ? m[0] : null }];
    },
    amlegalHere(slug) {
      const m = document.body.innerText.match(/(\d{4} S-\d+|Supp\. No\. \d+ - \d{4}) \(current\)/);
      return [{ slug, marker: m ? m[0] : null }];
    },
  };
  return "formxMarkers ready";
})();
