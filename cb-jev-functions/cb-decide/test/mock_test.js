// Offline test: runs decide_lib.js with a mocked N1QL() so no cluster or API key is needed.
// Usage: node test/mock_test.js
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const src = fs.readFileSync(__dirname + "/../src/decide_lib.js", "utf8");
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

// The library must only define functions at top level (no globals).
assert.deepStrictEqual(
  Object.keys(ctx).filter(k => !["JSON", "Array", "Error", "N1QL"].includes(k)).sort(),
  ["cb_decide", "cb_decide_choice", "cb_decide_prob", "cb_decide_score"]
);

// cb_decide passes questions through and returns the answers map unchanged
const questions = {
  issue: { type: "choice", instructions: "main issue?", criteria: { battery: "battery", screen: "screen" } },
  wants_return: { type: "noul", instructions: "wants to return it?" }
};
nextResponse = { answers: {
  issue: { type: "choice", choice: "battery", probabilities: { battery: 0.8, screen: 0.2 }, confidence: 0.8 },
  wants_return: { type: "noul", noul: 0.91 }
}};
const out = ctx.cb_decide("Battery dies in an hour. I want my money back.", questions);
assert.strictEqual(out.issue.choice, "battery");
assert.strictEqual(out.wants_return.noul, 0.91);
const body = JSON.parse(lastParams[1].data);
assert.strictEqual(lastParams[0], "https://api.typesafe.ai/v1/systemone");
assert.strictEqual(body.model, "jev-latest");
assert.strictEqual(body.state, "Battery dies in an hour. I want my money back.");
assert.deepStrictEqual(body.questions, questions);
assert.ok(lastParams[1].header[0].startsWith("Authorization: Bearer "));

// Convenience wrappers
nextResponse = { answers: { d: { type: "noul", noul: 0.12 } } };
assert.strictEqual(ctx.cb_decide_prob({ a: 1 }, "is it urgent?"), 0.12);
nextResponse = { answers: { d: { type: "choice", choice: "sales" } } };
assert.strictEqual(ctx.cb_decide_choice({ a: 1 }, "which team?", ["billing", "sales"]), "sales");
assert.deepStrictEqual(JSON.parse(lastParams[1].data).questions.d.criteria, { billing: "billing", sales: "sales" });
nextResponse = { answers: { d: { type: "score", score: 2.5 } } };
assert.strictEqual(ctx.cb_decide_score({ a: 1 }, "difficulty?", ["easy", "medium", "hard"]), 2.5);

// Bad responses throw
nextResponse = { oops: true };
assert.throws(() => ctx.cb_decide("x", questions), /unexpected response/);
nextResponse = { answers: { d: { type: "noul" } } };
assert.throws(() => ctx.cb_decide_prob("x", "q"), /unexpected response/);

console.log("cb_decide: all mock tests passed");
