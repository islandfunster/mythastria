# Effect graphics and placement contract

This increment belongs to the standalone Isles Table prototype. It does not modify Claude's simulator or the Seven Isles adventure. The current material art is original procedural SVG, with clean outlines and restrained retro colour palettes. Token PNG assets are unchanged.

## Geometry

The engine stores square-centre coordinates, using the same convention as combatants. The renderer adds 0.5 to map coordinates to position them in SVG. Dimensions are feet; 5 ft equals one square. Direction is degrees clockwise from east in the browser's downward-positive Y axis. The origin is the start edge/apex of directional shapes or the centre of radial ones.

| Shape | Geometry | Sizing |
| --- | --- | --- |
| `line` | Oriented strip, starts at origin | `length_ft`, `width_ft` |
| `cone` | Flat-ended triangle, apex at origin | Length and outer width both `length_ft` |
| `circle` | Circular radius/burst/cloud | `radius_ft` |
| `rectangle` | Oriented rectangular zone/wall | `length_ft`, `width_ft` |
| `ranged` | Thin illustrated trajectory and travelling particle | `length_ft`; no affected area implied |
| `melee` | Local slash/impact marker | Fixed 5-ft-diameter marker; no reach implied |

Area boundaries are visual geometry, not rules-level grid inclusion. No diagonal rule, wall clipping, range check, target inclusion or damage is inferred. An effect can extend beyond the map; its origin must be on the map. Geometry, material and movement policy are independent.

## Effect record

```json
{
  "id": "fx:engine-command-id",
  "label": "Burning breath",
  "shape": "cone",
  "appearance": "fire",
  "origin": [8, 4],
  "angle_deg": 180,
  "length_ft": 30,
  "width_ft": 5,
  "radius_ft": 10,
  "source": "npc",
  "control": "fixed",
  "source_actor": "actor-id",
  "expires_round": 4
}
```

Unused dimensions remain valid numbers (5–120 ft). Labels are plain text, at most 100 bytes. Materials: fire, frost, lightning, poison, smoke, arcane, physical, radiant, acid, thunder, healing, shadow, transport. The selected material animates inside the boundary, never moves the boundary itself. All effects respect reduced-motion settings and the local Animate artwork checkbox.

`source`: player, npc, trap, spell. `control`: movable, fixed, attached. Only player/movable effects accept edit operations. Player-created fixed and attached effects can be removed but cannot be independently repositioned. Attached effects use an existing source actor's current coordinates in every resolved state, including after undo. Fixed effects retain their committed origin and direction if their source later moves. An origin for breath/bolt currently uses the fixture actor centre; a future real event should specify mouth/edge offset and target knowledge as authoritative data.

`expires_round` is null for indefinite player templates; otherwise the effect is absent from resolved state at the beginning of that round. Expiry is independent of CSS animation time. A 1-round template lasts through the current round, not until the caster's next turn. Concentration, dispels and per-turn expiry need future simulator events. Instant visuals now use the separate event envelope below.

## Prototype operations

All mutations use `{op:"effect", id, revision, action}`. Rust rejects stale revisions, conflicting command IDs, invalid geometry and unauthorized edits. Identical command retries are idempotent within the existing 256-command cache.

- `create`: `action.effect` includes the full record. Rust assigns its ID and forces source to player. Placement policy may be movable, fixed or attached. Maximum 40 active records.
- `edit`: `effect_id`, optional origin, angle_deg, length_ft, width_ft, radius_ft. Only player/movable records accept it; source/policy cannot be changed through edits.
- `remove`: only player-created records.
- `trigger`: preset identifier, not client geometry. The engine determines the source, origin, aim, policy and expiry from the training fixture. Presets: npc_breath, trap_flames, spell_cloud, spell_blast, spell_aura, ranged_hit, melee_hit.
- `clear_triggers`: explicit hotseat-GM test reset; removes non-player demonstration records. It is not a player repositioning permission.

Effects are embedded in portable saves using a serde default so older saves still load. Responses include resolved `effects`; state and result exports also carry the extension. Consumers of the older simulator format may ignore it. These are local hotseat capabilities, not authenticated multiplayer roles.

## Interaction

Place on map enters placement mode. Drag to choose origin, direction and size; click uses entered size. Attached placement uses the selected token as the anchor. Free placement permits sub-square origins; dragging an existing centre handle changes position in half-square increments. Place at X/Y creates a template from the numeric coordinates and angle without requiring a pointer drag. Numeric coordinates also provide exact repositioning. The separate aim handle rotates a permitted effect. Numeric size/angle inputs apply to the selected movable effect. An edit gesture commits once on release; Escape or pointer cancellation abandons it. Leaving Edit effects restores normal token dragging and keyboard movement. Ctrl+Z remains token-move undo; it does not undo effect creation or editing.

## Next engine integration

Claude's simulator remains the rules reference. For real effects, provide authoritative source actor/trap, delivery (attack/save/automatic), selected legal targets or geometry, material, resolved origin/aim, movement permissions, duration/expiry, visibility and event outcome. Separate an instantaneous projectile/impact event from a persistent zone. Player placement should be a pending engine decision: receive legal origin/range/shape constraints, preview, submit, validate, then commit and lock or expose only the moves that the spell permits. Never treat a template drawn here as a resolved spell cast.

Before rules integration, verify wall occlusion, cone convention, emanations versus bursts, affected-square policy, source edge offsets, path-following projectiles, concentration removal and caster-turn duration against the simulator. The current trigger lab does not claim any of those rules.

## Verification

Fourteen native Rust core tests pass. Actual-WASM effect checks cover create/edit/remove, fixed-source rejection, attached movement/undo, expiry, save/load, backward compatibility, malformed records, command retry/staleness and unchanged actors/resources/RNG. Pure rendering checks exercise all 78 shape/material pairs. The UI DOM harness covers mouse placement, centre handles, exact position, disabled locked controls and cancellation. Browser visual QA is unavailable in this environment; installed-browser layout and mouse feel still require user verification.


## One-shot visual events

Brief graphics are separate from persistent `effects`. A `visual_events` record contains id, kind (`projectile`, `melee`, `burst`, `breath`, `pulse`), the fixed Effect snapshot, outcome (`hit`, `miss`, `critical`, `demo`) and duration_ms (300–6000). The Game keeps the latest 24 records for replay and saves; each relevant result includes only newly emitted events. General replies include the recent list. Older saves default to an empty list.

The real melee command emits one event after determining its actual outcome; no additional RNG call is made. Event IDs include revision and command ID. Retried commands do not emit a second event. The hotseat trigger presets npc_breath, ranged_hit, melee_hit and spell_blast now emit transient events instead of persistent zones. Their fixed geometry is still derived by Rust. Clouds, trap jets and wards remain persistent.

A `replay` effect operation takes event_id and emits a new visual ID with the original fixed snapshot, outcome and duration. It logs the replay, but repeats no combat action, rolls, damage or resource use. Replay does not retarget old geometry if a combatant has since moved. Player templates can also be previewed locally once without an engine mutation.

The presentation queue allows at most eight concurrent pictures, deduplicates received event IDs, and expires them using browser time. It primes silently on initial/resumed/loaded sessions, so saved old impacts never autoplay. Negative CSS animation delays preserve elapsed playback progress across map redraws. Stop playback clears only active pictures, not persistent zones or the recorded replay list. Reduced-motion and Animate artwork settings replace motion with brief static marks. No synchronous flashing or screen shake is used.

Additional checks cover actual-WASM melee hit/miss/critical output, no extra replay damage/RNG, command retries, bounded records and backward-compatible loads. A virtual clock verifies playback expiry, deduplication, concurrency limits and silent hydration; SVG checks cover all 20 event kind/outcome combinations. The DOM harness exercises one-shot triggering, replay and stop playback. These do not replace browser visual review.


## Expanded visual library and chosen sources

The atlas has 13 presets with animated SVG thumbnails. Each selects shape, material and dimensions for manual placement. New materials have independent motion: acid droplets, expanding thunder rings, rising healing crosses, curling shadows and gold scan lines. They remain clipped to stationary template boundaries and respect animation/reduced-motion controls.

The test `trigger` action accepts optional source_actor and target_actor IDs. They must identify living combatants; invalid or defeated IDs are rejected atomically. Defaults prefer a living foe as source and a living party member as target, falling back to another living actor. Rust derives current coordinates and direction. Directional breath/bolt/acid previews and transport require different source and target IDs. Trap jets always retain their fixture vent geometry; the actor selectors are disabled for that preset. These are graphics tests, not legal action offers.

New test presets: acid_jet (one-shot breath envelope), thunder_burst (one-shot expansion), healing_pulse (one-shot glyphs, no HP change), shadow_cloud (fixed persistent area), transport (one-shot teleport-style shimmer, no movement).

Transport adds kind `teleport` plus optional target_origin and token_id on VisualEvent. They default to null for older saves. A transport event requires both and validates the destination and registered token. Rust captures the source position, destination position and source token ID at trigger time. Replay retains that snapshot. The renderer uses approved token PNG alpha as a mask for golden scan lines and shows a ghost at the destination; real combatants remain unchanged and visible. The token registry footprint controls ghost size. This is a visual preview, not a claim that an occupied destination or chosen distance is a legal teleport.

Checks exercise chosen actors, all new trigger types, rejected unknown/self targets, unchanged HP/positions/resources/RNG, transport save/load validation, the alpha-mask renderer, preview cards and selector persistence. Browser appearance remains to be reviewed by the user.


## Compact table controls

Effects now opens from the multifunction Effects button. Place contains presets and folded custom shape/size/policy settings; On map contains existing templates, edit/preview/remove and optional exact coordinates; Test & replay contains engine visual demonstrations. A normal tap is sufficient. Optional right-click or double-click also opens the panel. Place on map closes it automatically, retaining all input values, and Done or Move returns to token movement. The panel is nonmodal so mouse/touch map interactions remain available; keyboard shortcuts do not move tokens while a disclosure form is open. No effect record or engine permission changed in this layout increment.
