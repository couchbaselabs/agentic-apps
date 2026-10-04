-- Run with NO query context set, so the functions are global and usable from any scope.
-- Prerequisite: ./install.sh has uploaded the jev_lib library.

CREATE OR REPLACE FUNCTION jev(doc, cond)            LANGUAGE JAVASCRIPT AS "jev"        AT "jev_lib";
CREATE OR REPLACE FUNCTION jev_prob(doc, cond)       LANGUAGE JAVASCRIPT AS "jev_prob"   AT "jev_lib";
CREATE OR REPLACE FUNCTION jev_choice(doc, q, opts)  LANGUAGE JAVASCRIPT AS "jev_choice" AT "jev_lib";
CREATE OR REPLACE FUNCTION jev_score(doc, q, levels) LANGUAGE JAVASCRIPT AS "jev_score"  AT "jev_lib";
