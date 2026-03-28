const SLIDE_BOUNDS = { width: 10, height: 5.625 };

export const BENTO_GRIDS = {
  hero_1: {
    name: "Full Focus",
    cards: [{ id: "main", x: 0.5, y: 0.5, w: 9.0, h: 4.625 }],
  },
  split_2: {
    name: "Split Two",
    cards: [
      { id: "left", x: 0.4, y: 0.5, w: 4.3, h: 4.2 },
      { id: "right", x: 5.3, y: 0.5, w: 4.3, h: 4.2 },
    ],
  },
  asymmetric_2: {
    name: "Asymmetric Two",
    cards: [
      { id: "major", x: 0.4, y: 0.5, w: 5.8, h: 4.2 },
      { id: "minor", x: 6.6, y: 0.5, w: 3.0, h: 4.2 },
    ],
  },
  grid_3: {
    name: "Grid Three",
    cards: [
      { id: "c1", x: 0.35, y: 0.5, w: 2.9, h: 4.2 },
      { id: "c2", x: 3.55, y: 0.5, w: 2.9, h: 4.2 },
      { id: "c3", x: 6.75, y: 0.5, w: 2.9, h: 4.2 },
    ],
  },
  grid_4: {
    name: "Grid Four",
    cards: [
      { id: "tl", x: 0.4, y: 0.4, w: 4.3, h: 2.0 },
      { id: "tr", x: 5.3, y: 0.4, w: 4.3, h: 2.0 },
      { id: "bl", x: 0.4, y: 2.8, w: 4.3, h: 2.0 },
      { id: "br", x: 5.3, y: 2.8, w: 4.3, h: 2.0 },
    ],
  },
  bento_5: {
    name: "Bento Five",
    cards: [
      { id: "hero", x: 0.4, y: 0.4, w: 5.0, h: 4.4 },
      { id: "s1", x: 5.8, y: 0.4, w: 3.8, h: 1.0 },
      { id: "s2", x: 5.8, y: 1.7, w: 3.8, h: 1.0 },
      { id: "s3", x: 5.8, y: 3.0, w: 3.8, h: 1.0 },
      { id: "s4", x: 5.8, y: 4.3, w: 3.8, h: 0.5 },
    ],
  },
  bento_6: {
    name: "Bento Six",
    cards: [
      { id: "h1", x: 0.35, y: 0.4, w: 4.5, h: 2.5 },
      { id: "h2", x: 5.15, y: 0.4, w: 4.5, h: 2.5 },
      { id: "s1", x: 0.35, y: 3.2, w: 2.1, h: 1.6 },
      { id: "s2", x: 2.75, y: 3.2, w: 2.1, h: 1.6 },
      { id: "s3", x: 5.15, y: 3.2, w: 2.1, h: 1.6 },
      { id: "s4", x: 7.55, y: 3.2, w: 2.1, h: 1.6 },
    ],
  },
  timeline: {
    name: "Timeline",
    cards: [
      { id: "t1", x: 0.5, y: 1.5, w: 1.5, h: 2.5 },
      { id: "t2", x: 2.1, y: 1.5, w: 1.5, h: 2.5 },
      { id: "t3", x: 3.7, y: 1.5, w: 1.5, h: 2.5 },
      { id: "t4", x: 5.3, y: 1.5, w: 1.5, h: 2.5 },
      { id: "t5", x: 6.9, y: 1.5, w: 1.5, h: 2.5 },
    ],
    axis: { y: 2.7, x1: 0.5, x2: 9.2 },
  },
};

function overlaps(a, b) {
  const ax2 = a.x + a.w;
  const ay2 = a.y + a.h;
  const bx2 = b.x + b.w;
  const by2 = b.y + b.h;
  return a.x < bx2 && ax2 > b.x && a.y < by2 && ay2 > b.y;
}

export function getGrid(name) {
  const key = String(name || "").trim();
  return BENTO_GRIDS[key] || null;
}

export function validateGrid(name, bounds = SLIDE_BOUNDS) {
  const grid = getGrid(name);
  if (!grid || !Array.isArray(grid.cards) || grid.cards.length === 0) return false;

  for (const card of grid.cards) {
    if (
      Number(card.x) < 0 ||
      Number(card.y) < 0 ||
      Number(card.w) <= 0 ||
      Number(card.h) <= 0 ||
      Number(card.x) + Number(card.w) > bounds.width ||
      Number(card.y) + Number(card.h) > bounds.height
    ) {
      return false;
    }
  }

  for (let i = 0; i < grid.cards.length; i += 1) {
    for (let j = i + 1; j < grid.cards.length; j += 1) {
      if (overlaps(grid.cards[i], grid.cards[j])) return false;
    }
  }
  return true;
}

export function getCardById(gridName, cardId, index = 0) {
  const grid = getGrid(gridName);
  if (!grid || !Array.isArray(grid.cards) || grid.cards.length === 0) return null;
  const byId = grid.cards.find((card) => String(card.id) === String(cardId || ""));
  if (byId) return byId;
  const strictSlot = ["1", "true", "yes", "on"].includes(
    String(process?.env?.MINIMAX_STRICT_CARD_SLOT || "").trim().toLowerCase(),
  );
  if (strictSlot && String(cardId || "").trim()) {
    console.warn(
      `[bento-grid] unresolved card_id "${cardId}" for grid "${gridName}", fallback by index=${index}`,
    );
  }
  return grid.cards[index % grid.cards.length];
}
