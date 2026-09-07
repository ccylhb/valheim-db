import type { APIRoute } from "astro";
import weapons from "../data/weapons.json";
import creatures from "../data/creatures.json";
import armor from "../data/armor.json";
import food from "../data/food.json";

interface Entry {
  t: string;
  u: string;
  k: string;
  i?: string;
}

export const GET: APIRoute = () => {
  const tools: Entry[] = [
    { t: "Boss Order Guide", u: "/rankings/#bosses", k: "Tool" },
    { t: "Weapon Damage Rankings", u: "/rankings/#weapons", k: "Tool" },
    { t: "Best Food Rankings", u: "/rankings/#food", k: "Tool" },
    { t: "Armor Set Rankings", u: "/rankings/#armor", k: "Tool" },
    { t: "Food Planner", u: "/food-planner/", k: "Tool" },
  ];
  const items: Entry[] = [
    ...weapons.map((w: any) => ({ t: w.name, u: `/weapons/${w.slug}/`, k: w.type || "Weapon", i: w.icon || "" })),
    ...creatures.map((c: any) => ({ t: c.name, u: `/creatures/${c.slug}/`, k: c.boss ? "Boss" : "Creature", i: c.icon || "" })),
    ...armor.map((a: any) => ({ t: a.name, u: `/armor/${a.slug}/`, k: "Armor", i: a.icon || "" })),
    ...food.map((f: any) => ({ t: f.name, u: `/food/${f.slug}/`, k: "Food", i: f.icon || "" })),
  ];
  return new Response(JSON.stringify({ tools, items }), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
