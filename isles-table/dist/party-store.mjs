// GM 2026-10-25 ("the DM handoff will need to transfer the maps and logs to the server to make them available to the
// guest DM"): the party chosen on Play an adventure is kept by Mythastria (POST /api/party), not by one browser, so
// whoever holds the GM role sees the same party and can start its fights. The saved characters' sheets go with it: a
// browser that does not have a character in its own roster (a guest GM's) uses the sheet the table kept.

// what a fight or the party's day needs from a sheet (not its import extract or builder choices)
export const tableSheet = c => { const { provenance, import: _, build, ...rest } = c; return rest; };

// this browser's roster, then the table's characters it does not have (marked fromTable)
export function mergeRoster(local, table) {
  const ids = new Set((local ?? []).map(c => c.id));
  return [...(local ?? []), ...((table?.characters) ?? []).filter(c => c && !ids.has(c.id)).map(c => ({ ...c, fromTable: true }))];
}

export async function loadTableParty(post) {
  const out = await post('/api/party', { op: 'get' }).catch(() => null);
  return out?.ok ? out.party ?? null : null;
}

// party: {members, characters: [ids], level}; roster: the sheets those ids name
export async function saveTableParty(post, party, roster) {
  const ids = new Set(party.characters ?? []);
  return post('/api/party', { op: 'save', party: { members: party.members ?? [], level: party.level || 1,
    characters: (roster ?? []).filter(c => ids.has(c.id)).map(tableSheet) } }).catch(() => ({ ok: false }));
}

// the table's party in the page's own shape ({members, characters: [ids], level})
export const partyChoice = p => p ? { members: p.members ?? [], characters: (p.characters ?? []).map(c => c.id), level: p.level || 1 } : null;
