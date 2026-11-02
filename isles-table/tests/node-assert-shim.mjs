// A small stand-in for Node's 'node:assert/strict', so Node test scripts (test_live_port.mjs, ...) also
// run in the browser runner on a PC without Node (tests/node_tests.html maps the import to this file). Only what such
// scripts use: assert(), equal, notEqual, deepEqual, throws.
function fail(message, why) { throw new Error(message ? `${message} (${why})` : why); }
function same(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b) || Object.getPrototypeOf(a) !== Object.getPrototypeOf(b)) return false;
  const ka = Object.keys(a), kb = Object.keys(b);
  return ka.length === kb.length && ka.every(k => Object.hasOwn(b, k) && same(a[k], b[k]));
}
const show = v => { try { return JSON.stringify(v); } catch { return String(v); } };
export default function assert(value, message) { if (!value) fail(message, 'expected a true value'); }
assert.ok = assert;
assert.equal = (a, b, message) => { if (!Object.is(a, b)) fail(message, `${show(a)} !== ${show(b)}`); };
assert.notEqual = (a, b, message) => { if (Object.is(a, b)) fail(message, `${show(a)} should differ`); };
assert.deepEqual = (a, b, message) => { if (!same(a, b)) fail(message, `${show(a)} is not ${show(b)}`); };
assert.throws = (fn, expected, message) => {
  try { fn(); } catch (e) {
    if (expected instanceof RegExp && !expected.test(String(e?.message ?? e))) fail(message, `wrong error: ${e?.message}`);
    return;
  }
  fail(message, 'expected an error');
};
