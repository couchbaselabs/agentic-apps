// Offline test: runs jev_lib.js with a mocked N1QL() so no cluster or API key is needed.
// Usage: node test/mock_test.js
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const src = fs.readFileSync(__dirname + "/../src/jev_lib.js", "utf8");
let nextResponse = null;
let lastParams = null;

const ctx = {
  JSON, Array, Error,
  N1QL: function (stmt, params) {
    lastParams = params;
    const rows = [{ r: nextResponse }];
    rows.close = function () {};
    return rows;
  }
};
vm.createContext(ctx);
vm.runInContext(src, ctx);

// Guard against globals: the library must only define functions at top level.
assert.deepStrictEqual(
  Object.keys(ctx).filter(k => !["JSON", "Array", "Error", "N1QL"].includes(k)).sort(),
  ["jev", "jev_choice", "jev_prob", "jev_score"]
);

// jev / jev_prob read answers.match.noul
nextResponse = { answers: { match: { type: "noul", noul: 0.98 } } };
assert.strictEqual(ctx.jev({ firstName: "Giuseppe" }, "the name is European"), true);
assert.strictEqual(ctx.jev_prob({ firstName: "Giuseppe" }, "the name is European"), 0.98);
nextResponse = { answers: { match: { type: "noul", noul: 0.002 } } };
assert.strictEqual(ctx.jev({ firstName: "Wei" }, "the name is European"), false);

// Request shape
const body = JSON.parse(lastParams[1].data);
assert.strictEqual(lastParams[0], "https://api.typesafe.ai/v1/systemone");
assert.strictEqual(body.model, "jev-latest");
assert.strictEqual(body.questions.match.type, "noul");
assert.ok(body.questions.match.instructions.includes("the name is European"));
assert.ok(lastParams[1].header[0].startsWith("Authorization: Bearer "));

// jev_choice: array options become {label: label}; reads .choice
nextResponse = { answers: { pick: { type: "choice", choice: "billing", probabilities: { billing: 0.9 }, confidence: 0.9 } } };
assert.strictEqual(ctx.jev_choice({ t: 1 }, "which team?", ["billing", "technical"]), "billing");
assert.deepStrictEqual(JSON.parse(lastParams[1].data).questions.pick.criteria, { billing: "billing", technical: "technical" });

// jev_score: reads .score
nextResponse = { answers: { rate: { type: "score", score: 3.2 } } };
assert.strictEqual(ctx.jev_score({ p: 1 }, "how luxurious?", ["budget", "mid", "premium", "luxury"]), 3.2);

// Bad response throws
nextResponse = { answers: { match: { type: "noul" } } };
assert.throws(() => ctx.jev({}, "x"), /unexpected response/);

console.log("jev: all mock tests passed");
