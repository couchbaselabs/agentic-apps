# `cb_decide()`: an `ai_decide()`-style function for Couchbase SQL++

Many enterprise AI tasks don't need an LLM to write anything. They need a decision: which category does this ticket belong to, does this document need review, which model should handle this prompt. Using a chat LLM for those adds latency and cost that compound at scale, and leaves you parsing free text.

On September 30, 2026, Databricks announced `ai_decide`, a Beta AI Function powered by a decision model. You give it unstructured text and one or more questions, and it returns a probability, a choice from named criteria, or a score on an ordered scale. It can be called from SQL or a REST API.

This repo brings the same pattern to Couchbase. `cb_decide()` is a SQL++ function that sends your text (or JSON document) and a set of typed questions to [TypeSafe AI's Jev](https://typesafe.ai/) model, the kind of decision model Databricks' announcement points to, and returns typed answers you can filter, group and sort on.

This project is unofficial. It is inspired by `ai_decide` and is not affiliated with Databricks or TypeSafe AI, and the signature of `cb_decide()` is my own design, not a copy of Databricks'.

## What you get

| Function | Returns | Use it for |
| --- | --- | --- |
| `cb_decide(state, questions)` | `OBJECT`, one answer per question | Several decisions about the same input in one call |
| `cb_decide_prob(state, question)` | `DOUBLE`, 0 to 1 | A yes/no question as a probability |
| `cb_decide_choice(state, question, options)` | label (`STRING`) | Classification |
| `cb_decide_score(state, question, levels)` | number | Scoring on an ordered rubric |

`state` can be a string or any JSON value, including a whole document.

## The three question types

| Type | Question | Answer shape |
| --- | --- | --- |
| `noul` | Is this true? | `{"type": "noul", "noul": 0.93}`, the probability of yes |
| `choice` | Which option fits best? | `{"type": "choice", "choice": "billing", "probabilities": {...}, "confidence": 0.9}` |
| `score` | Where on this ordered scale? | `{"type": "score", "score": 2.5}` |

For `noul`, the value is the probability that the answer is yes. It is not a rating of degree: 0.9 for "the customer wants a refund" means the model is 90% sure they do. For degrees, use a `score` question.

A question is an object with a `type`, `instructions`, and optional `criteria`. For `choice`, `criteria` is an object of `{label: description}`. For `score`, it is an ordered array of 2 to 10 rubric levels. For `noul`, you can optionally pass `{"true": "...", "false": "..."}` to define what yes and no mean.

All the questions in one `cb_decide()` call are answered in a single request, so asking three questions about a row costs little more than asking one.

## How it works

```
SELECT cb_decide(r.text, {...questions...}) FROM reviews AS r
        |
        v
 JavaScript UDF (src/decide_lib.js) --> N1QL("SELECT CURL(...)") --> https://api.typesafe.ai/v1/systemone
        ^                                                                    |
        +------------ { "answers": { "issue": {...}, "wants_return": {...} } } <---+
```

Couchbase JavaScript UDFs can't rely on global variables, so every function in the library is self-contained.

One difference from Databricks is worth stating plainly. `ai_decide` runs inside the Databricks platform, next to governed data. `cb_decide()` calls a hosted API, so the text you pass leaves your cluster.

## Prerequisites

- Couchbase Server with the Query service and JavaScript UDF support (7.x or later; check that your edition includes JavaScript UDFs).
- A [TypeSafe AI](https://console.typesafe.ai/) API key. Jev access may be waitlisted or available through a gateway; see TypeSafe's docs.
- `curl` and `perl` on the machine where you run the install script.
- The Query service reachable from your machine on port 8093, and outbound HTTPS from the query nodes to `api.typesafe.ai`.

## Step 1: Install the library

```bash
export TYPESAFE_API_KEY="your-typesafe-key"
export CB_PASSWORD="your-couchbase-admin-password"
./install.sh
```

The script injects your key into a build copy of the library (`build/`, which is git-ignored), uploads it to the Query service at `http://localhost:8093/evaluator/v1/libraries/decide_lib`, and allowlists `https://api.typesafe.ai` for `CURL()`. Set `CB_HOST` or `CB_USER` if your cluster isn't `localhost` with the `Administrator` user.

The allowlist is a cluster-level query setting, so the script sets it through the cluster manager (port 8091). You can also set it in the web console under Settings > Query Settings > CURL() Allowlist.

Or upload by hand, after replacing the three-dash placeholder in each function with your key:

```bash
curl -u Administrator:password -X POST \
  http://localhost:8093/evaluator/v1/libraries/decide_lib \
  --data-binary @build/decide_lib.js
```

## Step 2: Register the functions

Run `sql/01_register_functions.sql` with no query context set, so the functions are global:

```sql
CREATE OR REPLACE FUNCTION cb_decide(state, questions)       LANGUAGE JAVASCRIPT AS "cb_decide"        AT "decide_lib";
CREATE OR REPLACE FUNCTION cb_decide_prob(state, question)   LANGUAGE JAVASCRIPT AS "cb_decide_prob"   AT "decide_lib";
CREATE OR REPLACE FUNCTION cb_decide_choice(state, q, opts)  LANGUAGE JAVASCRIPT AS "cb_decide_choice" AT "decide_lib";
CREATE OR REPLACE FUNCTION cb_decide_score(state, q, levels) LANGUAGE JAVASCRIPT AS "cb_decide_score"  AT "decide_lib";
```

## Step 3: Load the sample data

The sample data is 8 product reviews, 6 prompts and 4 agent answers. Create a bucket and scope, set the query context, and load it:

```bash
couchbase-cli bucket-create -c localhost -u Administrator -p password \
  --bucket decidedemo --bucket-type couchbase --bucket-ramsize 256

cbq -e http://localhost:8093 -u Administrator -p password
```

Then, in the `cbq` shell:

```
CREATE SCOPE decidedemo.demo;
\SET -query_context "default:decidedemo.demo";
\SOURCE sql/02_sample_data.sql;
```

In the Query Workbench, paste the contents of `sql/02_sample_data.sql` and pick `decidedemo.demo` in the query context dropdown. With the context set, every query below refers to collections by their plain names: `reviews`, `prompts` and `agent_answers`.

## Step 4: Try it

Model output is probabilistic, so the descriptions below say what to expect, not exact values.

### One call, several questions

```sql
SELECT cb_decide(
  "The battery dies in an hour and I want my money back.",
  {
    "issue":        {"type": "choice", "instructions": "What is the main issue?",
                     "criteria": {"battery": "Battery life or charging", "screen": "Display problems",
                                  "shipping": "Delivery or damage", "other": "Anything else"}},
    "wants_return": {"type": "noul", "instructions": "Does the customer want to return the product?"}
  }
) AS decision;
```

Expect `decision.issue.choice` to be `battery` and `decision.wants_return.noul` to be close to 1.

### Review tagging

Tag each review with its main issue and whether the customer wants to return it, then aggregate by product and month. The inner query calls `cb_decide()` once per review, and the outer queries read the answers.

```sql
SELECT t.product, t.month, t.issue,
       COUNT(*) AS reviews,
       SUM(CASE WHEN t.wants_return > 0.5 THEN 1 ELSE 0 END) AS likely_returns
FROM (
  SELECT s.product, SUBSTR(s.review_date, 0, 7) AS month,
         s.d.issue.choice AS issue, s.d.wants_return.noul AS wants_return
  FROM (
    SELECT r.product, r.review_date,
           cb_decide(r.text, {
             "issue":        {"type": "choice", "instructions": "What is the main issue, if any?",
                              "criteria": {"quality": "Defect, breakage or poor build",
                                           "battery": "Battery life",
                                           "software": "App or connectivity problems",
                                           "shipping": "Damaged or wrong item on arrival",
                                           "none": "No problem, positive review"}},
             "wants_return": {"type": "noul", "instructions": "Does the customer want to return or replace the product?"}
           }) AS d
    FROM reviews AS r
  ) AS s
) AS t
GROUP BY t.product, t.month, t.issue
ORDER BY t.product, t.month;
```

Expect the broken zipper, the stitching and the battery reviews to show up as likely returns, and the positive reviews as `none`.

### Model routing

Judge how hard each prompt is, then route it to a model tier:

```sql
SELECT s.prompt_id, s.prompt,
       s.d.reasoning.noul AS needs_reasoning,
       s.d.difficulty.score AS difficulty,
       CASE WHEN s.d.reasoning.noul > 0.5 THEN "large-model" ELSE "small-model" END AS route
FROM (
  SELECT p.prompt_id, p.prompt,
         cb_decide(p.prompt, {
           "reasoning":  {"type": "noul", "instructions": "Does answering this require multi-step reasoning?"},
           "difficulty": {"type": "score", "instructions": "How difficult is this request?",
                          "criteria": ["trivial", "easy", "moderate", "hard"]}
         }) AS d
  FROM prompts AS p
) AS s
ORDER BY s.prompt_id;
```

Expect the capital-of-France and Fahrenheit prompts to route to the small model and the proof and sharding prompts to the large one. The `score` is numeric and can be fractional; check one real response to confirm the scale before you rely on specific values.

### Agent evaluation

Use the model as a judge. Here the whole document, including the policy, is the state:

```sql
SELECT s.answer_id, s.answer,
       s.d.follows_policy.noul AS follows_policy,
       s.d.completeness.score  AS completeness
FROM (
  SELECT a.answer_id, a.answer,
         cb_decide(a, {
           "follows_policy": {"type": "noul",
                              "instructions": "Does the answer comply with the policy?"},
           "completeness":   {"type": "score",
                              "instructions": "How completely does the answer address every part of the question?",
                              "criteria": ["not at all", "partly", "mostly", "fully"]}
         }) AS d
  FROM agent_answers AS a
) AS s
ORDER BY s.answer_id;
```

Expect answer 1 (promises a $250 refund) to score low on policy, and answer 3 (answers half the question) to score low on completeness.

### Single-question helpers

```sql
SELECT r.product,
       cb_decide_prob(r.text, 'The customer is satisfied.') AS satisfied,
       cb_decide_choice(r.text, 'Which part of the product is discussed?',
                        ['fit and comfort', 'durability', 'battery', 'sound', 'software', 'other']) AS topic
FROM reviews AS r
LIMIT 4;
```

Each helper makes its own API call, so this query makes two per row. When you need several answers about the same row, one `cb_decide()` call is cheaper.

All of these queries are also in `sql/03_examples.sql`.

## Cost, speed and privacy

- **One HTTP call per row.** A Couchbase scalar UDF runs once per row, so every row a `cb_decide*()` call evaluates costs one nested query and one API request. Put several questions in one `cb_decide()` call, and narrow the rows first with a selective `WHERE` and `LIMIT` in a subquery.
- **No caching.** Couchbase UDFs can't keep state between calls, so repeating a query repeats the API calls.
- **Failures abort the statement.** A rate limit (429) or server error makes the function throw, and the whole query fails.
- **Your data leaves the cluster.** Every call sends the state you pass to a third-party API. Don't run it on data you aren't allowed to share, and send only the fields you need.
- **The key lives in the library.** The API key is embedded in the library source at install time, and anyone who can read libraries on the cluster can read it. Use a key scoped to this purpose and rotate it if it's exposed.
- **Format is not correctness.** A well-typed answer can still be wrong. Spot-check results against a baseline before you trust the labels, especially when the output drives routing or other automated decisions.

## Test without a cluster

`test/mock_test.js` runs the library against a mocked `N1QL()` and checks the request shape, response parsing and error handling. It needs only Node.js:

```bash
node test/mock_test.js
```

## Clean up

```bash
# 1. In cbq, with no query context: run sql/99_cleanup.sql (drops functions and the demo scope)
# 2. Remove the library:
export CB_PASSWORD="your-couchbase-admin-password"
./uninstall.sh
```

## Layout

```
src/decide_lib.js              the four functions
sql/01_register_functions.sql  CREATE FUNCTION statements
sql/02_sample_data.sql         collections and sample documents
sql/03_examples.sql            runnable examples
sql/99_cleanup.sql             drops functions and demo scope
install.sh / uninstall.sh      library upload and allowlist
test/mock_test.js              offline tests
```

## Related

- A companion repo, `cb-jev`, provides the DuckDB-style `jev()` family (`jev`, `jev_prob`, `jev_choice`, `jev_score`) over the same API.
- [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) (TypeSafe AI)
- [Databricks: Introducing `ai_decide`](https://www.databricks.com/blog/introducing-aidecide-make-fast-decisions-your-governed-data)
- [`ai_decide` SQL reference](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_decide)

## License

Apache 2.0. See [LICENSE](LICENSE).
