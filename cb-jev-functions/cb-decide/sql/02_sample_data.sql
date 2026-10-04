-- Run with the query context set to the demo scope, after creating the bucket and scope:
--
--   couchbase-cli bucket-create -c localhost -u Administrator -p password \
--       --bucket decidedemo --bucket-type couchbase --bucket-ramsize 256
--   cbq> CREATE SCOPE decidedemo.demo;
--   cbq> \SET -query_context "default:decidedemo.demo";
--   cbq> \SOURCE sql/02_sample_data.sql;
--
-- With the context set, collections are referred to by their plain names.

CREATE COLLECTION reviews;
CREATE COLLECTION prompts;
CREATE COLLECTION agent_answers;

CREATE PRIMARY INDEX ON reviews;
CREATE PRIMARY INDEX ON prompts;
CREATE PRIMARY INDEX ON agent_answers;

INSERT INTO reviews (KEY, VALUE) VALUES
("r1", {"product": "Trailblazer Backpack", "review_date": "2026-08-03", "text": "The zipper broke after two weeks. I want to send it back for a refund."}),
("r2", {"product": "Trailblazer Backpack", "review_date": "2026-08-19", "text": "Love the fit and the pockets. Very comfortable on long hikes."}),
("r3", {"product": "Trailblazer Backpack", "review_date": "2026-09-02", "text": "Stitching is coming apart on the shoulder strap. Disappointed, I would like to return it."}),
("r4", {"product": "Aurora Headphones",   "review_date": "2026-08-11", "text": "Battery barely lasts three hours, nowhere near the advertised 30. Returning these."}),
("r5", {"product": "Aurora Headphones",   "review_date": "2026-08-27", "text": "Sound quality is fantastic and the noise cancelling is excellent."}),
("r6", {"product": "Aurora Headphones",   "review_date": "2026-09-09", "text": "The app keeps disconnecting from the headphones. Annoying but I will keep them for now."}),
("r7", {"product": "Summit Water Bottle", "review_date": "2026-09-14", "text": "Arrived dented and the lid leaks. Please send a replacement."}),
("r8", {"product": "Summit Water Bottle", "review_date": "2026-09-20", "text": "Keeps drinks cold all day. Great value for the price."});

INSERT INTO prompts (KEY, VALUE) VALUES
("q1", {"prompt_id": 1, "prompt": "What is the capital of France?"}),
("q2", {"prompt_id": 2, "prompt": "Summarize this paragraph in one sentence: The meeting covered budget, hiring and the Q4 roadmap."}),
("q3", {"prompt_id": 3, "prompt": "Prove that the sum of two even integers is always even."}),
("q4", {"prompt_id": 4, "prompt": "Design a sharding strategy for a multi-region database that keeps cross-region latency under 50 ms while surviving the loss of any one region."}),
("q5", {"prompt_id": 5, "prompt": "Convert 72 degrees Fahrenheit to Celsius."}),
("q6", {"prompt_id": 6, "prompt": "My SQL++ query returns duplicate rows after a join. Explain the likely causes and how to fix them."});

INSERT INTO agent_answers (KEY, VALUE) VALUES
("a1", {"answer_id": 1, "policy": "Never promise a refund over $100 without manager approval.",
        "question": "I was overcharged $250. Can I get my money back?",
        "answer": "Yes, I have refunded the full $250 to your card right now."}),
("a2", {"answer_id": 2, "policy": "Never promise a refund over $100 without manager approval.",
        "question": "I was overcharged $250. Can I get my money back?",
        "answer": "I am sorry about the overcharge. Refunds over $100 need manager approval, so I have escalated your case and you will hear back within one business day."}),
("a3", {"answer_id": 3, "policy": "Never promise a refund over $100 without manager approval.",
        "question": "How do I reset my password and also update my billing address?",
        "answer": "Use the Forgot password link on the sign-in page."}),
("a4", {"answer_id": 4, "policy": "Never promise a refund over $100 without manager approval.",
        "question": "How do I reset my password and also update my billing address?",
        "answer": "Use the Forgot password link on the sign-in page to reset your password. For your billing address, go to Account > Billing > Edit address and save."});
