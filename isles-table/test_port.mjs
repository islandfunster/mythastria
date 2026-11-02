// Node entry for the engine port tests: node .\test_port.mjs
import fs from 'node:fs';
import { RustEngine } from './dist/engine.mjs';
import { run, runAsync } from './port_tests.mjs';
const engine = await RustEngine.create(fs.readFileSync(new URL('./dist/isles_engine.wasm', import.meta.url)));
const results = [...run(engine), ...await runAsync()];
for (const [name, ok, why] of results) console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : '\n     ' + why}`);
const failed = results.filter(r => !r[1]).length;
console.log(`${results.length - failed}/${results.length} port tests passed`);
process.exit(failed ? 1 : 0);
