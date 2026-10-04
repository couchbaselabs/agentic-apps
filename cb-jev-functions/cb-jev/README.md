# Plain-English conditions in SQL++: a `jev()` function for Couchbase

Say you have a collection of 50,000 support tickets and want the ones where the customer is angry. A `LIKE` pattern won't find them. Training a classifier takes labeled data and time. Sending every row to a chat LLM and parsing the text it returns is slow and expensive.

[TypeSafe AI's Jev](https://typesafe.ai/) is a model that answers this kind of question with a typed value and a probability instead of a paragraph. This repo adds Jev to Couchbase as a set of SQL++ functions, so you can write the condition in English and use it next to joins, `GROUP BY` and `ORDER BY`:

```sql
SELECT id, firstName, lastName
FROM person
WHERE jev(person, 'the name is European')
LIMIT 5;
```

The function names follow the `jev()` family that the DuckDB community extensions popularized (see [Jev and DuckDB](https://duckdb.org/2026/09/29/jev)). This project is unofficial and is not affiliated with TypeSafe AI or DuckDB.

## What you get

| Function | Returns | Use it for |
| --- | --- | --- |
| `jev(doc, condition)` | `BOOLEAN` | Filtering in `WHERE` |
| `jev_prob(doc, condition)` | `DOUBLE`, 0 to 1 | Ranking with `ORDER BY`, custom thresholds |
| `jev_choice(doc, question, options)` | label (`STRING`) | Classifying and `GROUP BY` |
| `jev_score(doc, question, levels)` | number | Scoring on an ordered rubric |

Each function takes a whole document (or any JSON value) as its first argument. Pass the keyspace alias, as in `jev(person, '...')`, to send the entire document.

## What Jev is

Jev is what TypeSafe calls a *System One model*. You send it a state (text or JSON) and a set of typed questions, and it returns typed answers with calibrated probabilities. It never generates a sentence. There are three question types:

| Type | Question | Answer |
| --- | --- | --- |
| `noul` | Is this true? | The probability of yes, from 0 to 1 |
| `choice` | Which option fits best? | The winning label, plus probabilities and confidence |
| `score` | Where on this ordered scale? | A score on your rubric |

A `noul` answer looks like `{"type": "noul", "noul": 0.93}`. The value is the probability that the answer is yes. It is not a rating of how strongly something holds: 0.9 for "the customer is angry" means the model is 90% sure the customer is angry, not that the customer is 90% angry. For degrees, use a `score` question.

`jev()` is `noul >= 0.5`. When you want a different cutoff, use `jev_prob()` and compare it yourself.

## How it works

```
SELECT ... WHERE jev(person, 'the name is European')
        |
        v
 JavaScript UDF (src/jev_lib.js) --> N1QL("SELECT CURL(...)") --> https://api.typesafe.ai/v1/systemone
        ^                                                                  |
        +------------------ { "answers": { "match": { "type": "noul", "noul": 0.97 } } } <---+
```

Each function builds a request with your document as `state` and one typed question, calls the System One endpoint through SQL++'s built-in `CURL()`, and reads the answer. Couchbase JavaScript UDFs can't rely on global variables, so every function in the library is self-contained.

## Prerequisites

- Couchbase Server with the Query service and JavaScript UDF support (7.x or later; check that your edition includes JavaScript UDFs).
- A [TypeSafe AI](https://console.typesafe.ai/) API key. Jev access may be waitlisted or available through a gateway; see TypeSafe's docs.
- `curl` and `perl` on the machine where you run the install script (both ship with macOS and most Linux distributions).
- The Query service reachable from your machine on port 8093, and outbound HTTPS from the query nodes to `api.typesafe.ai`.

## Step 1: Install the library

```bash
export TYPESAFE_API_KEY="your-typesafe-key"
export CB_PASSWORD="your-couchbase-admin-password"
./install.sh
```

The script injects your key into a build copy of the library (`build/`, which is git-ignored), uploads it to the Query service at `http://localhost:8093/evaluator/v1/libraries/jev_lib`, and allowlists `https://api.typesafe.ai` for `CURL()`. Set `CB_HOST` or `CB_USER` if your cluster isn't `localhost` with the `Administrator` user.

The allowlist is a cluster-level query setting, so the script sets it through the cluster manager (port 8091). You can also set it in the web console under Settings > Query Settings > CURL() Allowlist.

Or upload by hand, after replacing the three-dash placeholder in each function with your key:

```bash
curl -u Administrator:password -X POST \
  http://localhost:8093/evaluator/v1/libraries/jev_lib \
  --data-binary @build/jev_lib.js
```

## Step 2: Register the functions

Run `sql/01_register_functions.sql` with no query context set, so the functions are global:

```sql
CREATE OR REPLACE FUNCTION jev(doc, cond)            LANGUAGE JAVASCRIPT AS "jev"        AT "jev_lib";
CREATE OR REPLACE FUNCTION jev_prob(doc, cond)       LANGUAGE JAVASCRIPT AS "jev_prob"   AT "jev_lib";
CREATE OR REPLACE FUNCTION jev_choice(doc, q, opts)  LANGUAGE JAVASCRIPT AS "jev_choice" AT "jev_lib";
CREATE OR REPLACE FUNCTION jev_score(doc, q, levels) LANGUAGE JAVASCRIPT AS "jev_score"  AT "jev_lib";
```

## Step 3: Load the sample data

The sample data is 12 people, 10 support tickets and 8 products. Create a bucket and scope, set the query context, and load it:

```bash
couchbase-cli bucket-create -c localhost -u Administrator -p password \
  --bucket jevdemo --bucket-type couchbase --bucket-ramsize 256

cbq -e http://localhost:8093 -u Administrator -p password
```

Then, in the `cbq` shell:

```
CREATE SCOPE jevdemo.demo;
\SET -query_context "default:jevdemo.demo";
\SOURCE sql/02_sample_data.sql;
```

In the Query Workbench, paste the contents of `sql/02_sample_data.sql` and pick `jevdemo.demo` in the query context dropdown. With the context set, every query below refers to collections by their plain names: `person`, `tickets` and `products`.

## Step 4: Try it

First a smoke test on literals. Expect a probability near 1, one near 0, and `true`:

```sql
SELECT jev_prob({"firstName": "Giuseppe", "lastName": "Donati"}, 'the name is European') AS p_eu,
       jev_prob({"firstName": "Wei",      "lastName": "Zhang"},  'the name is European') AS p_other,
       jev({"firstName": "Giuseppe", "lastName": "Donati"},      'the name is European') AS is_eu;
```

Model output is probabilistic, so borderline cases (for example, an English-looking name that is also common in Europe) can land either side of 0.5. The examples below describe what to expect, not exact results.

### Filter

```sql
SELECT id, firstName, lastName
FROM person
WHERE jev(person, 'the name is European')
LIMIT 5;
```

Expect names such as Carmen Lepland, Giuseppe Donati, A. C. Bos, Olga Petrova and Hans Müller. Without an `ORDER BY`, which five rows come back isn't fixed.

### Run the cheap predicate first

A `WHERE` clause with `gender = "female" AND jev(...)` doesn't guarantee evaluation order. A subquery makes the narrowing explicit, so only matching rows reach the API:

```sql
SELECT p.id, p.firstName, p.lastName
FROM (
  SELECT person.*
  FROM person
  WHERE person.gender = "female"
) AS p
WHERE jev(p, 'the name is European');
```

### Rank

```sql
SELECT t.subject, jev_prob(t, 'the customer is angry') AS p
FROM tickets AS t
ORDER BY p DESC
LIMIT 5;
```

Expect the double-charge and "third time I am asking" tickets near the top and the thank-you ticket near the bottom.

### Classify, then group

Compute the label once per row in a subquery, then group on it. Writing the call in both `SELECT` and `GROUP BY` would call the API twice per row.

```sql
SELECT c.team, COUNT(*) AS n
FROM (
  SELECT jev_choice(t, 'which team should handle this?',
                    ['billing', 'technical', 'security', 'sales']) AS team
  FROM tickets AS t
) AS c
GROUP BY c.team
ORDER BY n DESC;
```

Pass an object instead of an array to describe each option. This tends to help on ambiguous cases such as the password-reset ticket:

```sql
SELECT t.ticket_id,
       jev_choice(t, 'which team should handle this?', {
         "billing":   "Payments, refunds, invoices, VAT",
         "technical": "Bugs, crashes, integrations, outages",
         "security":  "Account compromise, suspicious activity, password resets",
         "sales":     "Pricing, upgrades, volume discounts"
       }) AS team
FROM tickets AS t;
```

### Score

```sql
SELECT s.name, s.price, s.luxury
FROM (
  SELECT g.name, g.price,
         jev_score(g, 'how luxurious is this product?',
                   ['budget', 'mid-range', 'premium', 'luxury']) AS luxury
  FROM products AS g
) AS s
ORDER BY s.luxury DESC, s.price DESC;
```

The score is numeric, so it sorts directly. It can be fractional. Check one real response to confirm the scale before you rely on specific values. Expect the watch and the overcoat near the top and the cable and the bottle near the bottom.

### Use your own threshold

```sql
SELECT r.ticket_id, r.subject, r.angry
FROM (
  SELECT t.ticket_id, t.subject, jev_prob(t, 'the customer is angry') AS angry
  FROM tickets AS t
) AS r
WHERE r.angry > 0.8
ORDER BY r.angry DESC;
```

All of these queries are also in `sql/03_examples.sql`.

## Cost, speed and privacy

- **One HTTP call per row.** A Couchbase scalar UDF runs once per row, so every row a `jev*()` call evaluates costs one nested query and one API request. The DuckDB extensions can pack hundreds of judgments into one request because DuckDB hands them rows in chunks; a scalar UDF can't. This is fine for exploration and small result sets. For large collections, narrow the candidates first with a selective `WHERE` and `LIMIT` in a subquery.
- **No caching.** Couchbase UDFs can't keep state between calls, so repeating a query repeats the API calls. If you need a cache, keep one in a collection keyed by a hash of the document and the condition.
- **Failures abort the statement.** A rate limit (429) or server error makes the function throw, and the whole query fails. Rerun it, or reduce the row count.
- **Your data leaves the cluster.** Every function sends the document you pass to a third-party API. Don't run it on data you aren't allowed to share, and send only the fields you need, for example `jev(OBJECT_PICK(p, ["firstName", "lastName"]), '...')`.
- **The key lives in the library.** The API key is embedded in the library source at install time, and anyone who can read libraries on the cluster can read it. Use a key scoped to this purpose and rotate it if it's exposed.
- **Format is not correctness.** A well-typed answer can still be wrong. Spot-check results against a baseline before you trust the labels.

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
src/jev_lib.js                 the four functions
sql/01_register_functions.sql  CREATE FUNCTION statements
sql/02_sample_data.sql         collections and sample documents
sql/03_examples.sql            runnable examples
sql/99_cleanup.sql             drops functions and demo scope
install.sh / uninstall.sh      library upload and allowlist
test/mock_test.js              offline tests
```

## Related

- A companion repo, `cb-decide`, emulates Databricks' `ai_decide()` with a general `cb_decide()` function over the same Jev API.
- [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) (TypeSafe AI)
- [Jev and DuckDB: Plain-English Conditions in SQL](https://duckdb.org/2026/09/29/jev) (DuckDB blog)

## License

Apache 2.0. See [LICENSE](LICENSE).
