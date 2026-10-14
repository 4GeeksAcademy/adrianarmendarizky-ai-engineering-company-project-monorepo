// Checks safeReturnTo() with good and bad return addresses.
// Run: node infra/hardening/check_return_to.mjs   (needs Node 22.18 or newer)
import { safeReturnTo } from "../../uis/backoffice/lib/returnTo.ts";

const LOCAL = "http://localhost:3000/login";
const SPACE = "https://abc-def-3000.app.github.dev/login";
const PROD = "https://backoffice.brasaland.test/login";

const cases = [
  ["local app is allowed from a local page", "http://localhost:3001/", LOCAL, [], "http://localhost:3001/"],
  ["outside site is refused", "https://attacker.example/", LOCAL, [], null],
  ["javascript: address is refused", "javascript:alert(1)", LOCAL, [], null],
  ["address with no protocol is refused", "//attacker.example", LOCAL, [], null],
  ["address with a username is refused", "https://localhost:3001@attacker.example/", LOCAL, [], null],
  ["sibling port of own Codespace is allowed", "https://abc-def-3001.app.github.dev/", SPACE, [], "https://abc-def-3001.app.github.dev/"],
  ["someone else's Codespace is refused", "https://other-xyz-3001.app.github.dev/", SPACE, [], null],
  ["look-alike Codespace host is refused", "https://abc-def-3001.app.github.dev.attacker.example/", SPACE, [], null],
  ["localhost is refused from a production page", "http://localhost:3001/", PROD, [], null],
  ["listed production origin is allowed", "https://incidents.brasaland.test/", PROD, ["https://incidents.brasaland.test"], "https://incidents.brasaland.test/"],
  ["missing returnTo gives null", null, LOCAL, [], null],
];

let failed = 0;
for (const [name, value, here, extra, expected] of cases) {
  const ok = safeReturnTo(value, here, extra) === expected;
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
}
console.log(failed === 0 ? "all checks passed" : `${failed} check(s) FAILED`);
process.exit(failed === 0 ? 0 : 1);
