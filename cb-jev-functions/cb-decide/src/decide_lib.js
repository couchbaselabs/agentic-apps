// decide_lib.js -- an ai_decide()-style function for Couchbase SQL++, backed by TypeSafe AI's Jev model.
//
// Couchbase JavaScript UDFs cannot rely on global variables, so every function
// below is self-contained: constants are local and the HTTP call is repeated.
//
// The three-dash placeholder in each function is replaced with your TypeSafe API
// key by install.sh. Never commit a real key.

// cb_decide(state, questions) -> OBJECT of answers, keyed like `questions`.
//   state:     text or any JSON value
//   questions: { name: {"type": "noul"|"choice"|"score", "instructions": "...", "criteria": ...} }
// Answers: noul -> {type, noul: 0..1}; choice -> {type, choice, probabilities, confidence};
//          score -> {type, score}
function cb_decide(state, questions) {
  var KEY = "---";
  var URL = "https://api.typesafe.ai/v1/systemone";
  var MODEL = "jev-latest";

  var opts = {
    "request": "POST",
    "header": ["Authorization: Bearer " + KEY, "Content-Type: application/json"],
    "data": JSON.stringify({ model: MODEL, state: state, questions: questions })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  if (!resp || !resp.answers) {
    throw new Error("cb_decide: unexpected response: " + JSON.stringify(resp));
  }
  return resp.answers;
}

// cb_decide_prob(state, question) -> DOUBLE in [0, 1], the probability the statement is true.
function cb_decide_prob(state, question) {
  var KEY = "---";
  var URL = "https://api.typesafe.ai/v1/systemone";
  var MODEL = "jev-latest";

  var opts = {
    "request": "POST",
    "header": ["Authorization: Bearer " + KEY, "Content-Type: application/json"],
    "data": JSON.stringify({
      model: MODEL,
      state: state,
      questions: { "d": { "type": "noul", "instructions": question } }
    })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  var a = resp && resp.answers ? resp.answers.d : null;
  if (!a || typeof a.noul !== "number") {
    throw new Error("cb_decide_prob: unexpected response: " + JSON.stringify(resp));
  }
  return a.noul;
}

// cb_decide_choice(state, question, options) -> the winning label.
// options: an array of labels, or an object {label: description}.
function cb_decide_choice(state, question, options) {
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
      state: state,
      questions: { "d": { "type": "choice", "instructions": question, "criteria": criteria } }
    })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  var a = resp && resp.answers ? resp.answers.d : null;
  if (!a || a.choice === undefined) {
    throw new Error("cb_decide_choice: unexpected response: " + JSON.stringify(resp));
  }
  return a.choice;
}

// cb_decide_score(state, question, levels) -> numeric score on the ordered rubric.
// levels: an ordered array of 2-10 rubric labels, lowest first.
function cb_decide_score(state, question, levels) {
  var KEY = "---";
  var URL = "https://api.typesafe.ai/v1/systemone";
  var MODEL = "jev-latest";

  var opts = {
    "request": "POST",
    "header": ["Authorization: Bearer " + KEY, "Content-Type: application/json"],
    "data": JSON.stringify({
      model: MODEL,
      state: state,
      questions: { "d": { "type": "score", "instructions": question, "criteria": levels } }
    })
  };
  var q = N1QL("SELECT CURL($1, $2) AS r", [URL, opts]);
  var resp = null;
  for (const row of q) { resp = row.r; }
  q.close();

  var a = resp && resp.answers ? resp.answers.d : null;
  if (!a || a.score === undefined) {
    throw new Error("cb_decide_score: unexpected response: " + JSON.stringify(resp));
  }
  return a.score;
}
