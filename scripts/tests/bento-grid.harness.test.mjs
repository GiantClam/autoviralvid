import { getGrid, validateGrid } from "../minimax/bento-grid.mjs";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const hero = getGrid("hero_1");
assert(hero, "hero_1 grid should exist");
assert(Array.isArray(hero.cards) && hero.cards.length === 1, "hero_1 should have one card");
assert(validateGrid("hero_1"), "hero_1 grid should be valid");
assert(validateGrid("bento_6"), "bento_6 grid should be valid");
assert(validateGrid("timeline"), "timeline grid should be valid");
assert(!validateGrid("unknown_grid"), "unknown grid should be invalid");

console.log("bento-grid harness passed");

