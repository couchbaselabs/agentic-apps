# cb-jev-functions: typed AI decisions inside Couchbase SQL++

Put a judgment inside a query:

```sql
SELECT name, price
FROM products
WHERE price < 500
  AND jev(products, 'a good gift for a frequent flyer');
```

There is no column that says "good gift for a frequent flyer". The condition is a sentence, and the function returns a boolean. This folder contains two small projects that add that capability to Couchbase Server using three things it already has: [`CURL()`](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/curl.html), JavaScript user-defined functions, and [TypeSafe AI's Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) model.

Jev is a *decision model*. It answers typed questions with typed values instead of writing prose, so the results can be filtered, sorted, grouped and indexed like any other SQL++ value.

> **Unofficial.** These projects are not affiliated with or endorsed by Couchbase, TypeSafe AI, Databricks or DuckDB. They call a hosted third-party API, so read [Before you use it](#before-you-use-it).

## Two projects, one engine

| | [`cb-jev`](cb-jev) | [`cb-decide`](cb-decide) |
| --- | --- | --- |
| **Functions** | `jev`, `jev_prob`, `jev_choice`, `jev_score` | `cb_decide`, `cb_decide_prob`, `cb_decide_choice`, `cb_decide_score` |
| **Shape** | One question per call, one value back | Many questions per call, an object back |
| **Reads best in** | `WHERE`, `ORDER BY`, `GROUP BY` | A projection you store, or read field by field |
| **Modeled on** | pg-jev and the [DuckDB `jev()` extensions](https://duckdb.org/2026/09/29/jev) | Databricks' [`ai_decide`](https://www.databricks.com/blog/introducing-aidecide-make-fast-decisions-your-governed-data) |
| **Sample data** | `person`, `tickets`, `products` | `reviews`, `prompts`, `agent_answers` |

The `cb_decide()` signature is my own design. It follows the idea behind `ai_decide`, not its exact syntax.

**Which one should I use?**

| You need | Use |
| --- | --- |
| A condition inside `WHERE` | `jev(doc, 'condition')` |
| A probability to sort or threshold | `jev_prob` |
| One label to group on | `jev_choice` or `cb_decide_choice` |
| An ordered rating | `jev_score` or `cb_decide_score` |
| Several judgments about one document in a single request | `cb_decide` |
| Decisions you will store, index and reuse | `cb_decide` with an `UPDATE` |

You can install both. They use separate libraries (`jev_lib` and `decide_lib`) and separate function names.

## What Jev returns

You send Jev a state (text or JSON) and typed questions. There are three question types:

| Type | Question | Answer | SQL analogue |
| --- | --- | --- | --- |
| `noul` | Is this true? | `{"type": "noul", "noul": 0.93}`, the probability of yes | A `BOOLEAN` predicate |
| `choice` | Which option fits best? | `{"type": "choice", "choice": "billing", "probabilities": {...}, "confidence": 0.9}` | An enum you can `GROUP BY` |
| `score` | Where on this ordered scale? | `{"type": "score", "score": 2.5}` | An ordinal you can `ORDER BY` |

A `noul` value is the probability that the answer is yes. It is not a degree: 0.9 for "a good gift for a frequent flyer" means the model is 90% sure, not that the product is 90% giftable. For degrees, use a `score`. The score is numeric and can be fractional, so check one real response to confirm the scale before relying on specific values.

## How it works

```
SELECT ... WHERE jev(products, 'a good gift for a frequent flyer')
        |
        v
 JavaScript UDF --> N1QL("SELECT CURL(...)") --> https://api.typesafe.ai/v1/systemone
        ^                                                   |
        +--------- { "answers": { "match": { "type": "noul", "noul": 0.91 } } } <---+
```

Each function builds a request with your document as `state` and one or more typed questions, calls the System One endpoint through `CURL()`, and reads the answers. Couchbase JavaScript UDFs can't rely on global variables, so every function in each library is self-contained.

## Prerequisites

- Couchbase Server with the Query service and JavaScript UDF support (7.x or later; check that your edition and deployment support JavaScript UDFs and let `CURL()` reach external endpoints).
- A [TypeSafe AI](https://console.typesafe.ai/) API key. Jev access may be waitlisted or available through a gateway; see TypeSafe's documentation.
- `curl` and `perl` on the machine where you run the install scripts, and `couchbase-cli` and `cbq` for the sample data steps.
- The Query service reachable on port 8093, and outbound HTTPS from the query nodes to `api.typesafe.ai`.
- A Couchbase user that can upload libraries and create functions. People who run the queries need access to `CURL()`; anyone other than a Full Administrator needs the `QUERY_EXTERNAL_ACCESS` role.

## Quick start

The steps are the same for both projects. This example uses `cb-jev`; for `cb-decide`, change the folder, the bucket name (`decidedemo`) and the library file.

```bash
cd cb-jev
export TYPESAFE_API_KEY="your-typesafe-key"
export CB_PASSWORD="your-couchbase-admin-password"

# 1. Upload the library (port 8093) and allowlist the TypeSafe endpoint for CURL()
./install.sh

# 2. Create a bucket for the sample data
couchbase-cli bucket-create -c localhost -u Administrator -p password \
  --bucket jevdemo --bucket-type couchbase --bucket-ramsize 256

# 3. Register the functions, load the data and run the examples
cbq -e http://localhost:8093 -u Administrator -p password
```

In the `cbq` shell:

```
\SOURCE sql/01_register_functions.sql;
CREATE SCOPE jevdemo.demo;
\SET -query_context "default:jevdemo.demo";
\SOURCE sql/02_sample_data.sql;
\SOURCE sql/03_examples.sql;
```

Run `01_register_functions.sql` with no query context set, so the functions are global. After you set the context, queries refer to collections by their plain names (`products`, `person`, `reviews`).

Each project's own README has the full walkthrough, every example with a description of what to expect, and a cleanup procedure.

## What the install script does

`install.sh` reads `TYPESAFE_API_KEY` and `CB_PASSWORD` from your environment, injects the key into a build copy of the library (`build/`, which is git-ignored), uploads it to `http://<host>:8093/evaluator/v1/libraries/<library>`, and adds `https://api.typesafe.ai` to the `CURL()` access list. The key never appears in the source files. Set `CB_HOST` or `CB_USER` if your cluster isn't `localhost` with the `Administrator` user.

The access list is a cluster-level setting. The script sets it through the cluster manager on port 8091, using the `curlWhitelist` endpoint that the `CURL()` documentation names. You can also set it in the web console under Settings > Query Settings.

## Layout

```
cb-jev-functions/
├── README.md              this file
├── cb-jev/                jev(), jev_prob(), jev_choice(), jev_score()
│   ├── README.md
│   ├── install.sh / uninstall.sh
│   ├── src/jev_lib.js
│   ├── sql/               register, sample data, examples, cleanup
│   └── test/mock_test.js
└── cb-decide/             cb_decide(), cb_decide_prob(), cb_decide_choice(), cb_decide_score()
    ├── README.md
    ├── install.sh / uninstall.sh
    ├── src/decide_lib.js
    ├── sql/               register, sample data, examples, cleanup
    └── test/mock_test.js
```

## Before you use it

- **Your data leaves the cluster.** Every call sends the document you pass to a third-party API. Send only the fields a question needs, for example `jev({"description": p.description}, '...')`, and keep regulated data out of any trial. If you need data to stay in your network, the wrappers can be pointed at a self-hosted endpoint that speaks the same API: change the URL in the library and add it to the access list. Vet the quality and license of any such server first.
- **One HTTP call per row.** A Couchbase scalar UDF runs once per row, so every row a function evaluates costs one nested query and one API request. Narrow rows first with a selective subquery and `LIMIT`, ask several questions in one `cb_decide()` call, and write results back to documents so you never pay twice.
- **No caching and no retries.** UDFs can't keep state between calls, so repeating a query repeats the calls. A rate limit or server error makes the function throw and the whole statement fail.
- **The key lives in the library.** Anyone who can read libraries on the cluster can read it. Use a key scoped to this purpose and rotate it if it is exposed.
- **A well-typed answer can still be wrong.** Probabilities are a quality signal, not a guarantee. Label a sample yourself, compare, and choose thresholds from your own data. For a fixed, high-volume classification task, a model you train yourself can be cheaper and faster.
- **Results can change.** The wrappers call the `jev-latest` model alias. If you need repeatable results, pin an explicit model version in the library.

## Testing

Each project has an offline test that runs the library against a mocked `N1QL()`, so it needs only Node.js and no cluster or API key. It checks the request shape, response parsing, error handling and that the library defines no globals.

```bash
node cb-jev/test/mock_test.js
node cb-decide/test/mock_test.js
```

The SQL examples are meant to be run against your own cluster with your own key. Model output is probabilistic, so the READMEs describe what to expect, not exact values.

## Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| `CURL()` fails with a message about the URL not being allowed | The endpoint isn't on the access list. Re-run `install.sh`, or add `https://api.typesafe.ai` in Settings > Query Settings. |
| Authorization error from the API | The key is wrong, expired or doesn't have Jev access. Re-run `install.sh` with a valid `TYPESAFE_API_KEY`. |
| `unexpected response` thrown by a function | The API returned an error body instead of answers. The message includes the response; check the key, the model name and your rate limit. |
| Function not found | `01_register_functions.sql` wasn't run, or was run with a query context set. Run it with no context. |
| Library not found | The upload failed. Re-run `install.sh` and read its output. |
| Query is very slow | Each row makes an API call. Narrow rows first and add a `LIMIT`. |
| An updated key or library doesn't seem to take effect | Re-run `install.sh`, then re-run the `CREATE OR REPLACE FUNCTION` statements. |

## Status

This is an early release. The JavaScript is covered by offline tests with a mocked `N1QL()`. Validate the SQL examples on your cluster and with your own API key before you rely on them, and treat the performance and price figures quoted by vendors as vendor claims until you measure them on your data.

## References

- Couchbase documentation: [CURL() function](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/curl.html), [JavaScript functions for Query](https://docs.couchbase.com/server/current/javascript-udfs/javascript-functions-with-couchbase.html), [Query Functions REST API](https://docs.couchbase.com/server/current/n1ql-rest-functions/index.html)
- [Introducing System One Models and Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) (TypeSafe AI)
- [Introducing ai_decide](https://www.databricks.com/blog/introducing-aidecide-make-fast-decisions-your-governed-data) (Databricks)
- [Jev and DuckDB: Plain-English Conditions in SQL](https://duckdb.org/2026/09/29/jev) (DuckDB)
- Earlier Couchbase examples of calling external AI services from SQL++: [Using Google Artificial Intelligence Services in Couchbase N1QL](https://www.odbms.org/2018/02/using-google-artificial-intelligence-services-in-couchbase-n1ql/) and [Select ChatGPT From SQL? You Bet!](https://dzone.com/articles/select-chatgpt-from-sql-you-bet)

## License

Apache 2.0. Each project folder contains its own [LICENSE](cb-jev/LICENSE).
