#!/usr/bin/env python3
"""Scrape Valheim wiki (valheim.fandom.com) into 4 databases + bosses.

Libraries: weapons / creatures (+bosses) / armor (set pages w/ 3 pieces) / food.
Skips redirects, category-index pages and pages lacking the matching infobox.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
WT_CACHE = CACHE / "wikitexts.json"
UA = "ValheimDB/1.0 (site: valheim-db.pages.dev; contact franceiwhdbks865@gmail.com)"
API = "https://valheim.fandom.com/api.php"
DELAY = 0.5

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
        r = api({"action": "query", "list": "categorymembers", "cmtitle": "Category:" + cat,
                 "cmtype": "page", "cmnamespace": "0", "cmlimit": "500", **cont})
        out += [m["title"] for m in r.get("query", {}).get("categorymembers", [])]
        cont = r.get("continue") or {}
        if not cont:
            break
        time.sleep(DELAY)
    return out

def fetch_wikitexts(titles):
    """Batch fetch wikitext for titles (50/batch). Returns {title: text}."""
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        r = api({"action": "query", "prop": "revisions", "rvprop": "content",
                 "rvslots": "main", "titles": "|".join(chunk)})
        for pg in r.get("query", {}).get("pages", {}).values():
            t = pg.get("title", "?")
            rev = pg.get("revisions") or []
            txt = ""
            if rev:
                txt = (rev[0].get("slots", {}).get("main", {}) or {}).get("*", "")
            out[t] = txt
        time.sleep(DELAY)
    return out

def match_infobox(text, tpl):
    """Bracket-depth scan: return the FIRST {{tpl ...}} block or None."""
    pat = "{{" + tpl
    start = text.find(pat)
    if start < 0:
        return None
    i = text.find("{", start)  # position of '{' of '{{'
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
    return None

def normalize_wt(wt):
    """Split params glued onto value ends. Valheim infoboxes often write
    `x2|materials 2=...` on one line, which swallows the next param."""
    wt = wt.replace("|materials ", "\n|materials ")
    # any value directly followed by '|key=' (and not inside [[ ]])
    wt = re.sub(r"(?<![\[{<])([^\n|{<])\|(\s*[A-Za-z][\w ]*?=)", r"\1\n|\2", wt)
    return wt

def clean(s):
    if not s:
        return ""
    s = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", s)          # images
    s = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", s)          # [[a|b]] -> b
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)                      # [[a]] -> a
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)                          # simple templates
    s = re.sub(r"<[^>]+>", " ", s)                                # tags
    s = s.replace("*", "").replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip()

def parse_params(block):
    """Parse infobox params via line-state machine (handles multi-line values)."""
    params = {}
    lines = block.split("\n")
    cur_key, cur_val = None, []
    for ln in lines[1:]:  # skip '{{infobox ...'
        s = ln.strip()
        if not s:
            continue
        if s == "}}" or s.startswith("}}"):
            break
        m = re.match(r"^\|\s*([\w ]+?)\s*=\s*(.*)$", s)
        if m:
            if cur_key and cur_key not in params:
                params[cur_key] = " ".join(cur_val).strip()
            cur_key = m.group(1).strip().lower()
            cur_val = [m.group(2).strip()]
        elif cur_key is not None:
            # continuation line: strip leading | of nested content but keep text
            cur_val.append(s.lstrip("|").strip())
    if cur_key and cur_key not in params:
        params[cur_key] = " ".join(cur_val).strip()
    # trim stray closing braces/params glued to the last value
    for k, v in list(params.items()):
        i = v.find("}}")
        if i >= 0 and not v.endswith("}}"):
            v = v[:i]
        if v.endswith("}}"):
            v = v[:-2]
        params[k] = v.strip()
    return params

def num(s):
    m = re.search(r"-?\d+(?:\.\d+)?", str(s or ""))
    return float(m.group(0)) if m else None

def slug(t):
    s = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return s or "item"

def star_fields(params, prefix):
    """health 0star/1star/2star -> {0: val, 1: val, 2: val} with keys like health/damage."""
    out = {}
    for k, v in params.items():
        m = re.match(r"^" + prefix + r"\s*(\d)star$", k)
        if m:
            out[int(m.group(1))] = clean(v)
    return out

def parse_damage(v):
    """'Attack: 10 Blunt' -> {dmg: 10, type: 'Blunt'} ; '25 Pierce, 10 Fire' fallback."""
    m = re.match(r"(?:Attack:\s*)?([\d.]+)\s*([A-Za-z ]+)", v)
    if m:
        return {"dmg": num(m.group(1)), "type": m.group(2).strip()}
    return {"dmg": num(v), "type": ""}

# ---------------- scraper families ----------------

def scrape_weapons(titles, wts):
    out = []
    for t in titles:
        txt = wts.get(t, "")
        blk = match_infobox(txt, "infobox weapon")
        if not blk:
            continue
        p = parse_params(blk)
        dmg = {}
        for dk in ["slash", "pierce", "blunt", "chop", "pickaxe",
                   "fire", "frost", "lightning", "poison", "spirit"]:
            if p.get(dk):
                dmg[dk.title()] = num(p[dk])
        mats = []
        for k in sorted(k for k in p if k.startswith("materials")):
            v = clean(p[k])
            if v:
                mats.append(v)
        out.append({
            "name": p.get("title") or t, "slug": slug(p.get("title") or t),
            "image": "", "type": clean(p.get("type", "")), "source": clean(p.get("source", "")),
            "crafting_level": clean(p.get("crafting level", "")), "repair_level": clean(p.get("repair level", "")),
            "durability": num(p.get("durability")), "stamina": num(p.get("stamina")),
            "block_armor": num(p.get("block armor")), "knockback": num(p.get("knockback")),
            "parry": num(p.get("parry")), "backstab": num(p.get("backstab")),
            "damage": dmg, "materials": mats, "description": clean(p.get("description", "")),
        })
    return out

def scrape_creatures(titles, wts, boss=set()):
    out = []
    for t in titles:
        txt = wts.get(t, "")
        blk = match_infobox(txt, "infobox creature")
        if not blk:
            continue
        p = parse_params(blk)
        hp = star_fields(p, "health")
        dmgv = star_fields(p, "damage")
        drops = clean(p.get("drops", "")).split(",") if p.get("drops") else []
        drops = [d for d in drops if d and "trophy" not in d.lower()]
        entry = {
            "name": p.get("title") or t, "slug": slug(p.get("title") or t),
            "image": "", "location": clean(p.get("location", "")),
            "tameable": clean(p.get("tameable", "")), "trophy": clean(p.get("trophy", "")),
            "health_stars": {k: num(v) for k, v in hp.items()},
            "damage_stars": {k: parse_damage(v) for k, v in dmgv.items()},
            "weak": clean(p.get("weak", "")), "veryweak": clean(p.get("veryweak", "")),
            "resistant": clean(p.get("resistant", "")), "veryresistant": clean(p.get("veryresistant", "")),
            "immune": clean(p.get("immune", "")),
            "stagger": clean(p.get("stagger", "")), "faction": clean(p.get("faction", "")),
            "abilities": clean(p.get("abilities", "")), "drops": drops,
            "boss": t in boss, "description": "",
        }
        # grab first sentence after infobox as description
        after = txt[txt.find(blk) + len(blk):]
        m = re.search(r"\n\n([A-Z][^.\n]{20,300}\.)", after)
        if m:
            entry["description"] = re.sub(r"\[\[|\]\]|''|\{\{[^{}]*\}\}", "", m.group(1)).strip()
        out.append(entry)
    return out

def scrape_armor(titles, wts):
    """Armor pages hold 1-3 'infobox armor' blocks (pieces). Group by set page."""
    out = []
    for t in titles:
        txt = wts.get(t, "")
        blocks = []
        # collect ALL infobox armor blocks
        idx = 0
        while True:
            pos = txt.find("{{infobox armor", idx)
            if pos < 0:
                break
            depth = 0
            end = pos
            for j in range(pos, len(txt)):
                if txt[j] == "{":
                    depth += 1
                elif txt[j] == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
            blocks.append(txt[pos:end])
            idx = end
        if not blocks:
            continue
        pieces = []
        set_desc = ""
        for blk in blocks:
            p = parse_params(blk)
            if "title" in p or "armor" in p:
                pieces.append({
                    "name": clean(p.get("title", "")), "type": clean(p.get("type", "")),
                    "armor": num(p.get("armor")), "durability": num(p.get("durability")),
                    "weight": num(p.get("weight")), "materials": clean(p.get("materials 1", "")),
                    "movement_speed": clean(p.get("movement speed", "")),
                    "effect": clean(p.get("other effect", "")),
                })
        if not pieces:
            continue
        setname = t
        # set bonus text (often 'Set bonus' / '2 pieces:' etc.) - skip precise parse
        bonus = ""
        bm = re.search(r"(?:Set bonus|set bonus)[^\n]*\n([^\n]{10,300})", txt)
        if bm:
            bonus = clean(bm.group(1))
        out.append({
            "name": setname, "slug": slug(setname), "image": "",
            "pieces": pieces, "set_bonus": bonus,
            "description": set_desc,
            "total_armor": sum(pi["armor"] or 0 for pi in pieces),
        })
    return out

def scrape_food(titles, wts):
    out = []
    for t in titles:
        txt = wts.get(t, "")
        blk = match_infobox(txt, "infobox item")
        if not blk:
            continue
        p = parse_params(blk)
        ftype = clean(p.get("type", ""))
        hp = num(p.get("health"))
        stam = num(p.get("stamina"))
        if ftype.lower() != "food" and hp is None:
            continue
        mats = clean(p.get("materials", "")) or clean(p.get("materials 1", ""))
        out.append({
            "name": p.get("title") or t, "slug": slug(p.get("title") or t),
            "image": "", "source": clean(p.get("source", "")),
            "health": hp, "stamina": stam,
            "duration": num(p.get("duration")), "healing": clean(p.get("healing", "")),
            "effect": clean(p.get("effect", "")), "materials": mats,
            "description": clean(p.get("description", "")),
        })
    return out

def main():
    data = Path(__file__).resolve().parent.parent / "src" / "data"
    data.mkdir(parents=True, exist_ok=True)

    weapons_titles = cat_members("Weapons")
    creatures_titles = cat_members("Creatures")
    armor_titles = cat_members("Armor")
    food_titles = cat_members("Food")
    boss_titles = set(cat_members("Bosses"))
    print(f"categories: weapons={len(weapons_titles)} creatures={len(creatures_titles)} "
          f"armor={len(armor_titles)} food={len(food_titles)} bosses={len(boss_titles)}")

    all_t = list(dict.fromkeys(weapons_titles + creatures_titles + armor_titles + food_titles + list(boss_titles)))
    print(f"unique pages to fetch: {len(all_t)}")
    wts = {}
    if WT_CACHE.exists():
        wts = json.load(open(WT_CACHE, encoding="utf-8"))
        missing = [t for t in all_t if t not in wts]
        if missing:
            wts.update(fetch_wikitexts(missing))
            json.dump(wts, open(WT_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        else:
            print(f"loaded {len(wts)} wikitexts from cache")
    else:
        wts = fetch_wikitexts(all_t)
        json.dump(wts, open(WT_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"fetched wikitexts: {len(wts)}")
    wts = {k: normalize_wt(v) for k, v in wts.items()}

    weapons = scrape_weapons(weapons_titles, wts)
    merged_creatures = list(dict.fromkeys(creatures_titles + [b for b in boss_titles if b not in creatures_titles]))
    creatures = scrape_creatures(merged_creatures, wts, boss=boss_titles)
    armor = scrape_armor(armor_titles, wts)
    food = scrape_food(food_titles, wts)

    for fname, arr in [("weapons", weapons), ("creatures", creatures),
                       ("armor", armor), ("food", food)]:
        # inherit icons from the previous data file (icon fetch is a separate pass)
        old = {}
        oldf = data / f"{fname}.json"
        if oldf.exists():
            old = {x.get("slug"): x.get("icon", "") for x in json.load(open(oldf, encoding="utf-8"))}
        for it in arr:
            if not it.get("icon"):
                it["icon"] = old.get(it["slug"], "")
        (data / f"{fname}.json").write_text(json.dumps(arr, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{fname}: {len(arr)} items")

if __name__ == "__main__":
    main()
