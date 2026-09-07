#!/usr/bin/env python3
"""ValheimDB icon fetch: parse `image` params from cached wikitext, download via
Fandom standard thumb URL. Datasets: weapons / creatures / armor / food."""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("C:/Users/梁会斌/Documents/Codex/valheim-db")
CACHE = ROOT / "scripts" / "cache" / "wikitexts.json"
DATA = ROOT / "src" / "data"
ICON_DIR = ROOT / "public" / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)
UA = "ValheimDB/1.0 (site: valheim-db.pages.dev; contact franceiwhdbks865@gmail.com)"
API = "https://valheim.fandom.com/api.php"
DL_HOST = "https://static.wikia.nocookie.net/valheim"
DELAY = 0.4

def api(p, retries=3):
    url = API + "?" + urllib.parse.urlencode({**p, "format": "json"})
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except Exception:
            if i == retries - 1:
                return None
            time.sleep(2 * (i + 1))

def safe_name(t):
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_") + ".png"

def page_image(wt):
    """Return first image filename referenced by an infobox on the page."""
    if not wt:
        return None
    m = re.search(r"image\s*0star\s*=\s*([^\n|]+)", wt)
    if not m:
        m = re.search(r"image\s*=\s*([^\n|]+)", wt)
    if not m:
        return None
    v = m.group(1).strip()
    v = re.sub(r"\[\[(?:File|Image):([^\]|]*).*", r"\1", v)  # [[File:x.png|...]]
    v = re.sub(r"^\[\[(?:File|Image):", "", v).rstrip("]").strip()
    return v if v.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) else None

def thumb_url(raw):
    m = re.search(r"images/(?:thumb/)?([0-9a-f]/[0-9a-f]{2}/[^/]+\.[a-z]+)", raw)
    if not m:
        return None
    rel = m.group(1)
    fname = rel.split("/")[-1]
    return f"{DL_HOST}/images/thumb/{rel}/120px-{urllib.parse.quote(fname)}"

def main():
    wts = json.load(open(CACHE, encoding="utf-8"))
    wts_lower = {k.lower(): v for k, v in wts.items()}
    datasets = ["weapons", "creatures", "armor", "food"]
    flat = []  # (ds, item)
    for ds in datasets:
        d = json.load(open(DATA / f"{ds}.json", encoding="utf-8"))
        missing = [it for it in d if not it.get("icon")]
        print(f"{ds}: {len(d)} items, {len(missing)} missing icons")
        flat += [(ds, it) for it in missing]

    # map item -> image file name from cached wikitext
    file_of = {}
    for ds, it in flat:
        wt = wts_lower.get(it["name"].lower(), "")
        img = page_image(wt)
        if img:
            file_of[it["name"]] = "File:" + img
    print(f"resolved from wikitext: {len(file_of)}/{len(flat)}")

    # imageinfo to get raw url
    ft_list = sorted(set(file_of.values()))
    rawmap = {}
    for start in range(0, len(ft_list), 50):
        chunk = ft_list[start:start + 50]
        r = api({"action": "query", "titles": "|".join(chunk), "prop": "imageinfo", "iiprop": "url"})
        if r:
            for pg in r.get("query", {}).get("pages", {}).values():
                ii = pg.get("imageinfo")
                if ii:
                    rawmap[pg["title"]] = ii[0].get("url") or ""
        time.sleep(DELAY)
    print(f"imageinfo ok: {len(rawmap)}")

    fetched = 0
    for ds, it in flat:
        ft = file_of.get(it["name"])
        raw = rawmap.get(ft) if ft else None
        url = thumb_url(raw) if raw else None
        if not url:
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            b = urllib.request.urlopen(req, timeout=40).read()
            if len(b) > 300:
                (ICON_DIR / safe_name(it["slug"])).write_bytes(b)
                fetched += 1
        except Exception:
            pass
        time.sleep(0.12)
    print(f"downloaded: {fetched}")

    for ds in datasets:
        d = json.load(open(DATA / f"{ds}.json", encoding="utf-8"))
        patched = 0
        for it in d:
            if it.get("icon"):
                continue
            fname = safe_name(it["slug"])
            if (ICON_DIR / fname).exists():
                it["icon"] = "/icons/" + fname
                patched += 1
        json.dump(d, open(DATA / f"{ds}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        have = sum(1 for it in d if it.get("icon"))
        print(f"{ds}: now {have}/{len(d)} (+{patched})")

if __name__ == "__main__":
    main()
