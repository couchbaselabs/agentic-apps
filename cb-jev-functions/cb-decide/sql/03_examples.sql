-- Run with the query context set to "default:decidedemo.demo".
-- Each query below makes one API call per row it evaluates.

-- 1. One call, several questions about the same text
SELECT cb_decide(
  "The battery dies in an hour and I want my money back.",
  {
    "issue":        {"type": "choice", "instructions": "What is the main issue?",
                     "criteria": {"battery": "Battery life or charging", "screen": "Display problems",
                                  "shipping": "Delivery or damage", "other": "Anything else"}},
    "wants_return": {"type": "noul", "instructions": "Does the customer want to return the product?"}
  }
) AS decision;

-- 2. Review tagging: tag each review once, then aggregate by product and month
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

-- 3. Model routing: judge each prompt, then pick a model tier
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

-- 4. Agent evaluation: does each answer follow the policy, and how complete is it?
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

-- 5. Single-question helpers
SELECT r.product,
       cb_decide_prob(r.text, 'The customer is satisfied.') AS satisfied,
       cb_decide_choice(r.text, 'Which part of the product is discussed?',
                        ['fit and comfort', 'durability', 'battery', 'sound', 'software', 'other']) AS topic
FROM reviews AS r
LIMIT 4;
