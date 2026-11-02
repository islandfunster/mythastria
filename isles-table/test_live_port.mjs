// The browser runner already calls these functions. Run the pure live-port tests in Node too.
import assert from 'node:assert/strict';
import { run, runAsync, runReach, runSpells, runActions, runFog, runNotes, runPopout } from './play_tests.mjs';
const results = [...run(), ...await runAsync(), ...runReach(), ...runSpells(), ...runActions(), ...runFog(), ...runNotes(), ...await runPopout()];
for (const [name, ok, why] of results) console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : ': ' + why}`);
assert(results.every(([, ok]) => ok), 'Live view/port regressions failed');
console.log(`${results.length} live view/port tests passed (no browser rendering)`);
