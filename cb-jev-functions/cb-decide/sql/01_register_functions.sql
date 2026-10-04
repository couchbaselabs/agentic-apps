-- Run with NO query context set, so the functions are global and usable from any scope.
-- Prerequisite: ./install.sh has uploaded the decide_lib library.

CREATE OR REPLACE FUNCTION cb_decide(state, questions)         LANGUAGE JAVASCRIPT AS "cb_decide"        AT "decide_lib";
CREATE OR REPLACE FUNCTION cb_decide_prob(state, question)     LANGUAGE JAVASCRIPT AS "cb_decide_prob"   AT "decide_lib";
CREATE OR REPLACE FUNCTION cb_decide_choice(state, q, opts)    LANGUAGE JAVASCRIPT AS "cb_decide_choice" AT "decide_lib";
CREATE OR REPLACE FUNCTION cb_decide_score(state, q, levels)   LANGUAGE JAVASCRIPT AS "cb_decide_score"  AT "decide_lib";
