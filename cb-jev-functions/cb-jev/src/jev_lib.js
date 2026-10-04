// jev_lib.js -- plain-English conditions in SQL++, backed by TypeSafe AI's Jev model.
//
// Couchbase JavaScript UDFs cannot rely on global variables, so every function
// below is self-contained: constants are local and the HTTP call is repeated.
//
// The three-dash placeholder in each function is replaced with your TypeSafe API key by install.sh.
// Never commit a real key.

// jev(doc, condition) -> BOOLEAN, for WHERE. True when P(yes) >= 0.5.
function jev(doc, condition) {
  var KEY = "---";
  var URL = "https://api.typesafe.ai/v1/systemone";
  var MODEL = "jev-latest";
  var THRESHOLD = 0.5;

  var opts = {
    "request": "POST",
    "header": ["Authorization: Bearer " + KEY, "Content-Type: application/json"],
    "data": JSON.stringify({
      model: MODEL,
      state: doc,
      questions: { "match": {
        "type": "noul",
        "instructions": "Does this record satisfy the condition: " + condition + "?"
      }}
    })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  var a = resp && resp.answers ? resp.answers.match : null;
  if (!a || typeof a.noul !== "number") {
    throw new Error("jev: unexpected response: " + JSON.stringify(resp));
  }
  return a.noul >= THRESHOLD;
}

// jev_prob(doc, condition) -> DOUBLE in [0, 1], the probability the condition is true.
function jev_prob(doc, condition) {
  var KEY = "---";
  var URL = "https://api.typesafe.ai/v1/systemone";
  var MODEL = "jev-latest";

  var opts = {
    "request": "POST",
    "header": ["Authorization: Bearer " + KEY, "Content-Type: application/json"],
    "data": JSON.stringify({
      model: MODEL,
      state: doc,
      questions: { "match": {
        "type": "noul",
        "instructions": "Does this record satisfy the condition: " + condition + "?"
      }}
    })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  var a = resp && resp.answers ? resp.answers.match : null;
  if (!a || typeof a.noul !== "number") {
    throw new Error("jev_prob: unexpected response: " + JSON.stringify(resp));
  }
  return a.noul;
}

// jev_choice(doc, question, options) -> the winning label.
// options: an array of labels, or an object {label: description}.
function jev_choice(doc, question, options) {
  var KEY = "---";
  var URL = "https://api.typesafe.ai/v1/systemone";
  var MODEL = "jev-latest";

  var criteria = options;
  if (Array.isArray(options)) {
    criteria = {};
    for (var i = 0; i < options.length; i++) { criteria[options[i]] = options[i]; }
  }
  var opts = {
    "request": "POST",
    "header": ["Authorization: Bearer " + KEY, "Content-Type: application/json"],
    "data": JSON.stringify({
      model: MODEL,
      state: doc,
      questions: { "pick": { "type": "choice", "instructions": question, "criteria": criteria } }
    })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  var a = resp && resp.answers ? resp.answers.pick : null;
  if (!a || a.choice === undefined) {
    throw new Error("jev_choice: unexpected response: " + JSON.stringify(resp));
  }
  return a.choice;
}

// jev_score(doc, question, levels) -> numeric score on the ordered rubric.
// levels: an ordered array of 2-10 rubric labels, lowest first.
function jev_score(doc, question, levels) {
  var KEY = "---";
  var URL = "https://api.typesafe.ai/v1/systemone";
  var MODEL = "jev-latest";

  var opts = {
    "request": "POST",
    "header": ["Authorization: Bearer " + KEY, "Content-Type: application/json"],
    "data": JSON.stringify({
      model: MODEL,
      state: doc,
      questions: { "rate": { "type": "score", "instructions": question, "criteria": levels } }
    })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  var a = resp && resp.answers ? resp.answers.rate : null;
  if (!a || a.score === undefined) {
    throw new Error("jev_score: unexpected response: " + JSON.stringify(resp));
  }
  return a.score;
}
