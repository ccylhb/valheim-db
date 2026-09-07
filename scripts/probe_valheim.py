#!/usr/bin/env python3
"""Probe Valheim wiki: category member lists + representative wikitexts."""
import json, re, time, urllib.request, urllib.parse

UA = "ValheimDB/1.0 (site: valheim-db.pages.dev; contact franceiwhdbks865@gmail.com)"
API = "https://valheim.fandom.com/api.php"

def api(p, tries=3):
    url = API + "?" + urllib.parse.urlencode({**p, "format": "json"})
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:
            if i == tries - 1:
                return {"_err": str(e)[:80]}
            time.sleep(1.5)

def cat_members(cat):
    out, cont = [], {}
    while True:
        p = {"action": "query", "list": "categorymembers", "cmtitle": "Category:" + cat,
             "cmtype": "page", "cmnamespace": "0", "cmlimit": "500", **cont}
        r = api(p)
        q = r.get("query", {})
        out += [m["title"] for m in q.get("categorymembers", [])]
        cont = r.get("continue") or r.get("query-continue", {}).get("categorymembers", {})
        if not cont:
            break
        time.sleep(0.3)
    return out

if __name__ == "__main__":
    for cat in ["Weapons", "Creatures", "Armor", "Food"]:
        mem = cat_members(cat)
        print(f"=== Category:{cat} = {len(mem)} ===")
        print(" ".join(mem[:40]))
    reps = {"weapon": "Bronze Sword", "creature": "Boar", "armor": "Bronze helmet",
            "food": "Cooked boar meat", "food2": "Deer stew"}
    r = api({"action": "query", "prop": "revisions", "rvprop": "content",
             "rvslots": "main", "titles": "|".join(reps.values())})
    for pg in r.get("query", {}).get("pages", {}).values():
        t = pg.get("title", "?")
        txt = ""
        rev = pg.get("revisions") or []
        if rev:
            txt = (rev[0].get("slots", {}).get("main", {}) or {}).get("*", "")
        print(f"\n########## {t} (len {len(txt)}) ##########")
        print(txt[:1200])
