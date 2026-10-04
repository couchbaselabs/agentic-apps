-- Run with the query context set to "default:jevdemo.demo".
-- Each query below makes one API call per row it evaluates.

-- 0. Smoke test on literals (no collection needed)
SELECT jev_prob({"firstName": "Giuseppe", "lastName": "Donati"}, 'the name is European') AS p_eu,
       jev_prob({"firstName": "Wei",      "lastName": "Zhang"},  'the name is European') AS p_other,
       jev({"firstName": "Giuseppe", "lastName": "Donati"},      'the name is European') AS is_eu;

-- 1. Filter with a plain-English condition
SELECT id, firstName, lastName
FROM person
WHERE jev(person, 'the name is European')
LIMIT 5;

-- 2. Run the cheap predicate first, so only matching rows are sent to the API
SELECT p.id, p.firstName, p.lastName
FROM (
  SELECT person.*
  FROM person
  WHERE person.gender = "female"
) AS p
WHERE jev(p, 'the name is European');

-- 3. Rank by probability
SELECT t.subject, jev_prob(t, 'the customer is angry') AS p
FROM tickets AS t
ORDER BY p DESC
LIMIT 5;

-- 4. Classify each ticket
SELECT t.ticket_id, t.subject,
       jev_choice(t, 'which team should handle this?',
                  ['billing', 'technical', 'security', 'sales']) AS team
FROM tickets AS t
ORDER BY t.ticket_id;

-- 5. Classify, then group (compute the label once per row in a subquery)
SELECT c.team, COUNT(*) AS n
FROM (
  SELECT jev_choice(t, 'which team should handle this?',
                    ['billing', 'technical', 'security', 'sales']) AS team
  FROM tickets AS t
) AS c
GROUP BY c.team
ORDER BY n DESC;

-- 6. Describe each option to sharpen borderline cases
SELECT t.ticket_id,
       jev_choice(t, 'which team should handle this?', {
         "billing":   "Payments, refunds, invoices, VAT",
         "technical": "Bugs, crashes, integrations, outages",
         "security":  "Account compromise, suspicious activity, password resets",
         "sales":     "Pricing, upgrades, volume discounts"
       }) AS team
FROM tickets AS t;

-- 7. Score on an ordered rubric (the score is numeric; higher means further up the rubric)
SELECT s.name, s.price, s.luxury
FROM (
  SELECT g.name, g.price,
         jev_score(g, 'how luxurious is this product?',
                   ['budget', 'mid-range', 'premium', 'luxury']) AS luxury
  FROM products AS g
) AS s
ORDER BY s.luxury DESC, s.price DESC;

-- 8. Use your own threshold instead of 0.5
SELECT r.ticket_id, r.subject, r.angry
FROM (
  SELECT t.ticket_id, t.subject, jev_prob(t, 'the customer is angry') AS angry
  FROM tickets AS t
) AS r
WHERE r.angry > 0.8
ORDER BY r.angry DESC;
