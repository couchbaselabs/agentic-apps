-- Run with the query context set to the demo scope, after creating the bucket and scope:
--
--   couchbase-cli bucket-create -c localhost -u Administrator -p password \
--       --bucket jevdemo --bucket-type couchbase --bucket-ramsize 256
--   cbq> CREATE SCOPE jevdemo.demo;
--   cbq> \SET -query_context "default:jevdemo.demo";
--   cbq> \SOURCE sql/02_sample_data.sql;
--
-- With the context set, collections are referred to by their plain names.

CREATE COLLECTION person;
CREATE COLLECTION tickets;
CREATE COLLECTION products;

CREATE PRIMARY INDEX ON person;
CREATE PRIMARY INDEX ON tickets;
CREATE PRIMARY INDEX ON products;

INSERT INTO person (KEY, VALUE) VALUES
("p1",  {"id": 1129,  "firstName": "Carmen",   "lastName": "Lepland",  "gender": "female", "birthday": "1989-03-12"}),
("p2",  {"id": 2201,  "firstName": "Joseph",   "lastName": "Anderson", "gender": "male",   "birthday": "1984-11-02"}),
("p3",  {"id": 3310,  "firstName": "Steve",    "lastName": "Moore",    "gender": "male",   "birthday": "1991-07-21"}),
("p4",  {"id": 4402,  "firstName": "Giuseppe", "lastName": "Donati",   "gender": "male",   "birthday": "1979-01-30"}),
("p5",  {"id": 5503,  "firstName": "A. C.",    "lastName": "Bos",      "gender": "female", "birthday": "1995-05-09"}),
("p6",  {"id": 6604,  "firstName": "Wei",      "lastName": "Zhang",    "gender": "male",   "birthday": "1990-09-17"}),
("p7",  {"id": 7705,  "firstName": "Yuki",     "lastName": "Tanaka",   "gender": "female", "birthday": "1993-12-04"}),
("p8",  {"id": 8806,  "firstName": "Priya",    "lastName": "Sharma",   "gender": "female", "birthday": "1987-06-25"}),
("p9",  {"id": 9907,  "firstName": "Ahmed",    "lastName": "Hassan",   "gender": "male",   "birthday": "1982-02-14"}),
("p10", {"id": 11008, "firstName": "Olga",     "lastName": "Petrova",  "gender": "female", "birthday": "1986-08-08"}),
("p11", {"id": 12109, "firstName": "Hans",     "lastName": "Müller",   "gender": "male",   "birthday": "1975-10-19"}),
("p12", {"id": 13210, "firstName": "Chidi",    "lastName": "Okafor",   "gender": "male",   "birthday": "1992-04-03"});

INSERT INTO tickets (KEY, VALUE) VALUES
("t1",  {"ticket_id": 101, "subject": "Double charge on my card",
         "body": "I was charged twice for the same order and nobody is answering. This is unacceptable, I want my money back today."}),
("t2",  {"ticket_id": 102, "subject": "Cannot connect Stripe",
         "body": "The Stripe integration has failed for three days and I am losing sales. Please fix this ASAP."}),
("t3",  {"ticket_id": 103, "subject": "Question about annual pricing",
         "body": "Hi, could you tell me what the annual plan costs for a team of 25? No rush."}),
("t4",  {"ticket_id": 104, "subject": "Suspicious login attempts",
         "body": "I noticed several login attempts from countries I have never visited. Is my account compromised?"}),
("t5",  {"ticket_id": 105, "subject": "Thanks for the quick fix",
         "body": "Just wanted to say the outage was resolved faster than expected. Great work, thank you!"}),
("t6",  {"ticket_id": 106, "subject": "Invoice shows wrong VAT",
         "body": "The VAT number on invoice 8841 is wrong. Could you reissue it when you have a chance?"}),
("t7",  {"ticket_id": 107, "subject": "App crashes on upload",
         "body": "Every time I upload a file over 50 MB the app crashes. Seems like a bug."}),
("t8",  {"ticket_id": 108, "subject": "Upgrade to enterprise",
         "body": "We are interested in the enterprise tier and would like a call with sales about volume discounts."}),
("t9",  {"ticket_id": 109, "subject": "This is the third time I am asking",
         "body": "I have asked three times for a refund of my cancelled subscription. I am furious and considering a chargeback."}),
("t10", {"ticket_id": 110, "subject": "Password reset email never arrives",
         "body": "I requested a reset link several times but nothing shows up in my inbox or spam folder."});

INSERT INTO products (KEY, VALUE) VALUES
("g1", {"name": "Plastic Water Bottle",         "description": "Basic 500 ml bottle, pack of 12.",                      "price": 6}),
("g2", {"name": "Everyday Cotton T-Shirt",      "description": "Plain crew-neck tee in several colors.",                "price": 15}),
("g3", {"name": "Stainless Steel Cookware Set","description": "10-piece set suitable for daily home cooking.",         "price": 120}),
("g4", {"name": "Noise-Cancelling Headphones", "description": "Over-ear wireless headphones with 30-hour battery.",    "price": 299}),
("g5", {"name": "Leather Weekender Bag",       "description": "Full-grain leather bag, hand-stitched, brass hardware.","price": 450}),
("g6", {"name": "Swiss Automatic Watch",       "description": "Sapphire crystal, in-house movement, limited edition.", "price": 9500}),
("g7", {"name": "Cashmere Overcoat",           "description": "Italian-tailored coat in pure cashmere.",               "price": 1800}),
("g8", {"name": "USB-C Cable",                 "description": "1 m charging cable.",                                   "price": 9});
