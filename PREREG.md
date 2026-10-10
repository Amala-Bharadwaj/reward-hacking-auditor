# Pre-registration, output-shape ablation

Written before the analysis is run. Nothing in this file may be edited after the
first run of the new model. If something has to change afterwards, it goes in a
clearly labelled "deviations from pre-registration" section at the bottom, and
the original text stays.

Status: PREDICTIONS FROZEN 2026-08-23. Table generated after this file was written.

## The question

Existing result, already run and reported: dummy pass rate is the only predictor
of exploitability reaching p<0.05, OR 1.914, CI 1.018 to 3.598, p=0.0438, and it
does not survive correction for the 7 terms tested. Mutation score is not
significant, OR 0.628, CI 0.326 to 1.211, p=0.1649.

Hypothesis for this ablation: exploitability is driven by the size of the space
of plausible answers a function can return. A suite for a function returning a
boolean can be passed by a candidate that guesses. A suite for a function
returning a sorted list of ten integers cannot. Dummy pass rate is already an
indirect measurement of this, which is the proposed reason it is the one term
that came out.

## Features, primary model

Six terms. Every one is computed from `expected`, which `attributes.py:235`
already builds by running the reference on the visible tests. No new execution
except where noted.

| # | feature | definition | levels / range | predicted direction |
|---|---------|------------|----------------|---------------------|
| 1 | `output_class` | shape of the expected answer, collapsed | `bool` n=117, `scalar` (number or string) n=561, `structured` (seq or dict) n=283 | FILL IN |
| 2 | `n_distinct_outputs` | how many different expected answers appear across the 3 visible tests | 1, 2 or 3. observed 0.7% / 23.0% / 76.3% | FILL IN |
| 3 | `order_sensitive` | NEW MEASUREMENT, NEEDS APPROVAL. does the reference return a different answer when a sequence argument is shuffled | bool | FILL IN |
| 4 | `mutation_score` | unchanged, carried over | 0 to 1 | FILL IN |
| 5 | `dummy_pass_rate` | unchanged, carried over | 0 to 1 | FILL IN |

### BLOCKING: which outcome variable

`exploited` is currently defined at `analysis.py:59` as `n_gamed > 0`, where
`n_gamed` sums `false_accept`, the **published-tests-only** column.
`n_gamed_held_out` is computed at line 57 and then never used by anything.

So every coefficient and every quartile table in the existing report describes
exploitability of the **undefended** suite. The defended condition, which is the
argument the paper is built on, has never been regressed on at all.

The two outcomes are not close. Undefended, 334/881 = 37.9%. Defended,
173/881 = 19.6%. Roughly half the exploited tasks stop being exploited once
held-out tests are applied.

Options, one must be chosen before anything runs:

- **A.** `exploited_defended = n_gamed_held_out > 0`, 173 positives. Matches the
  claim the paper makes. Fewer positives so less power.
- **B.** Keep the undefended outcome. More power, but the paper then cannot say
  its predictors describe suites that have had the standard defence applied.
- **C.** Both, as two pre-specified models reported side by side. A predictor
  that survives the defence is a far stronger result than one that does not.

Decision: PENDING

`order_sensitive` is the only item here that is not free. It exists to capture
the mean versus mode distinction directly. Mean has one correct answer. Mode has
a correct answer only once a tie-breaking convention is fixed, and the reference
picks one silently. Shuffling a sequence argument and checking whether the answer
moves detects that convention dependence mechanically, without needing the spec.
It requires re-running each reference a few times. Approve or drop it.

## Features deliberately excluded from the primary model

Excluded on mechanism, not on their p-values. State it this way in the paper.
What a cheater must reproduce is the function's output, not its input, so
input-side descriptors have no causal path to exploitability under this
hypothesis. They are reported in a secondary descriptive table with no
significance testing attached.

- `input_type`, `has_edge_case`, `input_diversity`, `n_visible_tests`,
  `desc_words`, `n_oracle_inputs`.

## Correction

Benjamini-Hochberg across the terms of the primary model, q=0.05. Every term is
reported with its uncorrected p, its corrected p and its CI, including terms
that come out null. No term is dropped from the report after seeing results.

With 5 terms the BH threshold for the smallest p-value is 0.05/5 = 0.010.

## The mutation score sample problem

`mutation_score` is present for 637 of 881 tasks. It is missing when the mutation
worker times out, which happens when a mutated loop condition makes the reference
non-terminating. That is not missing at random. It is missing precisely on
loop-heavy problems.

Including the term therefore costs 252 tasks and biases the sample toward
problems with simple control flow. Two models are pre-specified to make this
visible rather than hidden:

- **Model A**, primary, all 881 tasks, without `mutation_score`.
- **Model B**, all terms including `mutation_score`, n approximately 629.

If Model A and Model B disagree on any term, that disagreement is reported as a
finding about the missingness, not resolved by picking the nicer one.

## What cannot be claimed

Failing to reject is not proof of no effect. The mutation score CI runs from 0.33
to 1.21, which is wide enough to include a substantial protective effect. The
defensible sentence is that this study did not detect one and the interval is
consistent with anything from a strong effect to none. The sentence "mutation
score does not predict exploitability" is not supported and must not appear.

## Deviations from pre-registration

**D1, 2026-09-03, second pre-registration, the input cap is removed.**

The second pre-registration specifies capping the EvalPlus oracle at 300 inputs
per problem, evenly strided, and argues the cap can only bias the reported rate
down. That argument is wrong in a way that matters. Striding is uniform over the
input list, and the inputs that carry an empty container are a thin minority of
it, roughly 1.7 per problem on HumanEval+ against a median of 977 inputs. The
cap therefore removed the only empty-container probe from 38 of the 92
HumanEval+ problems that have one, and an attack that is wrong only on empty
input is invisible to an oracle with no empty input in it.

The first HumanEval run under the cap reported empty_blind falling from 40.3%
under the fuzzed oracle to 14.4% under the EvalPlus oracle. That fall is mostly
the cap, not the oracle. It was caught because prediction Q1 said every rate
would rise and this one did not.

The cap is removed and every EvalPlus input is used. MBPP+ is unaffected either
way, since its largest problem has 150 inputs and the cap never bound. The
capped HumanEval numbers are discarded and not reported anywhere.

Q1 is left standing as written. It was frozen before the run and it is the
prediction that surfaced the bug, so rewriting it now would destroy the only
thing it was good for.

## Predictions, frozen 2026-08-23

Written by the assistant, not by Amala, at her instruction. Recorded here before
the table was generated. They serve the statistical purpose, stopping the
analysis being tuned to the answer. They do not serve as her own hypotheses.

`order_sensitive` is DROPPED. Reason: the probe made references hang rather than
answer, so it measured "reference breaks on reordered input" mixed in with
"answer depends on a tie-breaking convention". Two properties, one number.
The remaining features need no code execution at all.

Cells folded before running, both mechanical: `other` output class (5 tasks)
folds into `structured`; `n_distinct_outputs` collapses to binary, all three
answers differ (673) against at least two repeat (217).

### The predictions

**P1. Constant attacks against `output_class`. Strong effect, bool worst.**
`constant_true`, `constant_zero`, `constant_common` return a fixed value. They
pass exactly when the expected answers happen to be that value. Boolean-output
problems have a two-value answer space so a constant lands often. Predicted order
bool >> scalar > structured, with structured near zero.

**P2. P1 is partly tautological and that must be said in the paper.**
`constant_true` passing boolean problems is close to true by definition. It is a
sanity check that the pipeline works, not a finding. Anyone can see it coming.

**P3. The real test is `edge_blind` and `empty_blind` against `output_class`.**
These attacks are wrong only on unusual *inputs*. `output_class` describes the
*output*. There is no mechanical path from one to the other, so if a relationship
shows up it is a genuine finding rather than a definition restated. Prediction:
**weak to no effect**, rates roughly flat across the three classes. If this comes
out flat, the honest paper says the output-shape story explains the constant
attacks and does not explain the interesting ones.

**P4. `n_distinct_outputs` binary, against the constant attacks.**
Suites whose three published answers are not all different are easier to hit with
a constant. Predicted: repeat-answer suites more exploitable, effect clear for
constant attacks, near zero for `edge_blind` and `empty_blind`.

**P5. Weak against strong verifier.**
Held-out tests should gut the constant attacks, because one fuzzed input with a
different answer kills a constant outright. They should barely dent `edge_blind`
and `empty_blind`, because the fuzzer cannot produce an empty list or a zero, as
established at `mbpp.py:86`. Predicted: large weak-to-strong drop for constants,
small drop for the blind attacks.

**P6. Regression directions, unchanged.**
`mutation_score` protective, OR below 1. `dummy_pass_rate` harmful, OR above 1.
Neither expected to survive Benjamini-Hochberg.

### What would falsify the framing

If `edge_blind` and `empty_blind` are flat across output classes (P3 correct) AND
the constant attacks only reproduce their own definition (P2), then output shape
is not a predictor of the interesting failure and the paper cannot claim it is.
That outcome gets reported, not buried.

## Outcomes against predictions, recorded 2026-08-23

Table in `results/output_shape_table.txt`. Run once, all cells reported.

- **P1 WRONG.** All constant attacks 0.0% in every output class. Mechanism was
  wrong: a constant fails the visible tests immediately because even boolean
  problems ship three asserts with mixed answers.
- **P2 MOOT.** The tautology never occurred because P1 did not occur.
- **P3 WRONG, both directions.** `edge_blind` strong verifier falls across
  classes, bool 33.0% / scalar 14.3% / structured 7.2%. `empty_blind` rises,
  bool 43.1% / scalar 62.1% / structured 81.3%. Predicted flat for both. They are
  monotone and opposed.
- **P4 WRONG for constants, effect appeared on the blind attacks instead.**
  `edge_blind` strong: 10.3% all-differ vs 28.1% repeat-answer.
- **P5 HALF RIGHT.** `empty_blind` drops only 16.5% weak to strong, as
  predicted. `edge_blind` drops 85.1%, predicted small, wrong.

Headline: `empty_blind` survives the strong verifier at 65.2% overall and
81.3% on structured-output problems.

### OPEN THREAT, must be checked before any claim is written

`output_class` may be a proxy for input type. Empty-input attacks are only
meaningful where an input can be empty, and list-returning functions likely take
lists. Cross-tabulate output_class against input_type on the same 890 tasks. If
near-collinear, the claim is an input-shape claim, not an output-shape claim.
No new compute required.

**RESOLVED 2026-08-23, the threat does not hold.** Cross-tab confirms correlation
(empty-capable inputs: bool 67.9%, scalar 57.9%, structured 91.6%) but bool has a
higher empty-capable share than scalar and a LOWER empty_blind rate, which runs
against the confound. Stratifying by input_type, the output_class ordering holds
inside the two largest strata: flat_seq 41.9 / 51.9 / 84.9, string 46.2 / 75.6 /
96.6. Output shape is not a proxy for input shape. `number` inputs are the
exception, structured falls to 57.1% on n=21, too small to lean on.

edge_blind also survives conditioning, opposite direction, with one exception:
within string inputs it is flat at roughly 31-39% across all output classes.
String-input problems are uniformly edge-case vulnerable.

## HumanEval replication, 2026-08-26

Second benchmark run with the same attacks, verifiers and false-accept
definition. `humaneval.py` imports the fuzzer, vetter and edge-case generator
from `mbpp.py`, so the two are measured by the same code. 142 usable of 164.
Skips: 14 fewer than three parseable asserts, 4 too few fuzzed inputs, 4
reference hangs.

**The return-shape reversal DID NOT REPLICATE.**

                    MBPP (strong)              HumanEval (strong)
                bool  scalar  struct        bool   scalar  struct
edge_blind      33.0    14.3     7.2        33.3     35.6    18.8
empty_blind     43.1    62.1    81.3        23.8     43.8    29.2

MBPP is monotone in both directions. HumanEval peaks at scalar for both. The
structured empty_blind cells are 81.3% and 29.2% [18, 43], which do not overlap.
This is a contradiction rather than a wide interval. Class sizes on HumanEval are
bool 21, scalar 73, structured 48.

**The defence asymmetry DID replicate.**

  share of successful attacks removed by held-out tests
                     MBPP    HumanEval
  memorize_visible   96.7%     92.9%
  edge_blind         85.1%     67.7%
  empty_blind        16.5%     12.0%

Same ordering, comparable magnitudes, two independent benchmarks.

**Correction appended 2026-09-03, original figures left above as written.**
Four of those six cells do not reproduce from the current CSVs. Recomputed on
all 890 MBPP and all 142 HumanEval tasks: memorize_visible 96.7% and 92.9%
unchanged, edge_blind 85.4% and 68.8%, empty_blind 17.5% and 13.8%. The
submitted paper carries the recomputed figures, not these, so the paper is
right and this table is stale. The current CSVs were checked cell by cell
against `results/*_report.prev.csv` on 2026-09-03 and every one of the 24,768
overlapping rows is identical, so the difference is in how this table was
computed on 2026-08-26 and not in the data. The ordering, which is the claim,
is the same either way.

**Consequence.** Table 1 of the current draft describes MBPP and not code
benchmarks generally. The claim the data supports across both is the defence
asymmetry, not the return-shape reversal.

**Open validity issue, raised 2026-08-26.** For many problems the correct return
on empty input is not fixed by the problem statement, so the reference's
behaviour there is an implementation artifact. A candidate diverging from it may
not be wrong. The measurement may be divergence-from-reference rather than
incorrectness. Proposed reframe is underspecification, that the reward signal is
indifferent over a region so a method optimising against it puts arbitrary
behaviour there. UNRESOLVED, and it is a claim-level decision.

**EvalPlus is the primary related work.** It reports solutions passing base tests
and failing plus tests, which is close to this false-accept measure. The current
draft gives it one line. UNRESOLVED.

## Second pre-registration, EvalPlus oracle swap, frozen 2026-09-03

Written by the assistant, not by Amala, at her instruction on 2026-09-02
("make all of those predictions yourself"). Same standing as the first set.
They stop the analysis being tuned to the answer. They are not her hypotheses
and she has not yet ratified them.

Frozen before any false-positive rate under the new oracle had been computed.
What had already been measured when this was written, and so is not predicted
here, is the join geometry: 351 of 890 MBPP tasks are covered by MBPP+, the
EvalPlus reference agrees with ours on every visible test for 290 of 332
scored (87.3%), and where both references answer a plus input they agree on
90.5% of them.

### What changes

`oracle_inputs` stays as it is. A second oracle column is added, built from
EvalPlus inputs run against **our own reference**, so the two columns differ in
where the inputs came from and in nothing else. Swapping the reference as well
would confound an input-coverage change with a ground-truth change, and the
reference disagreement is reported separately instead.

Capped at 300 inputs per problem, evenly strided. The cap does not bind on
MBPP+ (max 150). It binds on HumanEval+ (median 977). Fewer probes can only
miss a wrong candidate, never invent one, so the cap biases the reported rate
down.

### The predictions

**Q1. Every false-positive rate rises under the EvalPlus oracle.** A curated
adversarial input set catches candidates a fuzzer drawn from the published
values does not. Predicted direction up for every attack, in every verifier
condition, with no exceptions.

**Q2. The rise is modest, under 15 points for most cells.** Our oracle already
contains the edge battery, so it is not blind to empty containers or zero. What
EvalPlus adds beyond that is large values, type diversity and boundaries outside
the fuzzer's envelope. Predicted smaller than the weak-to-strong verifier gaps
the paper already reports.

**Q3. The defence asymmetry survives, and this is the real test.** The share of
successful attacks removed by held-out tests should keep the ordering
memorize_visible > edge_blind > empty_blind under the new oracle. This is the
one claim that replicated across MBPP and HumanEval, and it is what the paper is
named after. If it inverts, the paper's headline is an artifact of our fuzzer
and has to be withdrawn.

**Q4. The single-empty-test result survives.** empty_blind under one empty test
should still be far below its rate under three held-out tests. The mechanism is
about which inputs the verifier probes, not about how correctness is judged, so
changing the oracle should not touch it.

**Q5. Selection, not oracle, explains part of any difference.** MBPP+ is built
on the human-sanitized MBPP subset, so the 351 covered tasks are higher quality
than the other 539. Predicted: on the covered subset, false-positive rates under
**our original fuzzed oracle** are already lower than on the full 890. This must
be reported alongside the oracle comparison, because otherwise a selection effect
reads as an oracle effect. Same-oracle subset-versus-full is the control.

**Q6. Reference disagreement bounds the precision of all of it.** The two
references disagree on 9.5% of plus inputs. Some share of every false-positive
count under every oracle is a reference artifact rather than a wrong candidate.
No rate reported here should be quoted to a precision finer than that, and the
paper says so.

### What would falsify the framing

Q3 inverting. If held-out tests turn out to remove a comparable share of
empty_blind and memorize_visible once an independent oracle judges correctness,
then the asymmetry was a property of our fuzzer and not of the defences.

### Not a prediction, recorded as post-hoc

The hardened lookup-table detector was built and measured on 2026-09-03 before
this section was written, so its numbers are stated as results and never as
predictions. Shipped detector flagged 21 of 8809 stored attempts. Hardened
detector flags 119. All 6 attempts the shipped detector flagged and the hardened
one does not are false positives of the old rule, ordinary wrong logic such as
`if n < 2: return True` where the compared value is also a published input. The
hardened rule adds whole-literal matching, so a dict keyed on the argument tuple
and a chain of equality tests against list arguments are caught, and it skips
`assert` statements because models routinely echo the published tests underneath
the function they wrote.

### Outcomes against the second pre-registration, recorded 2026-09-03

Deterministic attacks only. The model-attempt half is still running and its
outcomes are not recorded here yet. MBPP subset is 317 tasks of 890, HumanEval
subset is 139 of 142. Every cell is from `results/mbpp_report.csv` and
`results/humaneval_report.csv` under PYTHONHASHSEED=0.

**Q1 WRONG, and not only because of the cap.** Rates do not all rise. After
uncapping, empty_blind still falls under the EvalPlus oracle on both benchmarks,
81.7% to 58.4% on MBPP and 40.3% to 20.1% on HumanEval, and edge_blind falls at
the weak verifier on MBPP, 98.4% to 96.2%. Mechanism, stated after the fact and
labelled as such: our fuzzed oracle carries the edge battery, which swaps an
empty container into every argument position systematically, and that is aimed
at exactly the region empty_blind is wrong in. EvalPlus covers far more input
territory but only 92 of 164 HumanEval problems and 174 of 377 MBPP problems
have any empty-container input at all. The two oracles are not ordered by
strength. They are aimed differently, and neither dominates.

**Q2 WRONG in the cell that moved most.** Most cells move by a few points as
predicted, but empty_blind moves 23.3 points on MBPP and 20.2 on HumanEval, and
downward rather than upward.

**Q3 CORRECT, on both benchmarks.** Share of successful attacks removed by
held-out tests, fuzzed oracle then EvalPlus oracle.

                      MBPP              HumanEval
  memorize_visible  97.1%  96.8%      92.8%  92.8%
  edge_blind        86.9%  85.9%      68.3%  62.5%
  empty_blind       13.5%   9.7%      14.3%  10.7%

The ordering is identical in all four columns and the magnitudes barely move.
This is the claim the paper is named after and it does not depend on which
oracle judges correctness.

**Q4 CORRECT, on both benchmarks.** Against empty_blind, one empty test leaves
29.3% (fuzzed) and 16.4% (EvalPlus) on MBPP where three held-out tests leave
70.7% and 52.7%; on HumanEval 22.3% and 8.6% against 34.5% and 18.0%. Against
memorize_visible the direction reverses, one empty test leaving 46.4% and 46.7%
on MBPP where three held-out tests leave 2.8% and 3.2%; on HumanEval 71.9% and
72.7% against 7.2% and 7.2%. Each defence removes mainly the failure it was
aimed at, under either oracle.

**Q5 WRONG in direction, and the effect is immaterial.** The covered subset was
predicted to be less exploitable than the full set. Holding the fuzzed oracle
fixed, it is very slightly more exploitable: empty_blind at the weak verifier
81.7% on the subset against 79.6% on all 890, at the strong verifier 70.7%
against 65.6%, memorize_visible 99.4% against 98.8%, edge_blind 98.4% against
98.0%. Every interval overlaps. There is no selection effect large enough to
account for any of the oracle differences above, which is what the control was
for, but the predicted sign was wrong and that is recorded rather than reworded.

**Q6 stands as written.** The 9.5% reference disagreement is unchanged and
bounds the precision of every rate above.

### Outcome variable, resolving the BLOCKING item above

Decision: **C**, both models reported side by side. Recorded 2026-09-03 by the
assistant. Reason: a predictor that survives the standard defence is a much
stronger result than one that does not, and reporting only the undefended
outcome would let the regression describe a suite nobody actually ships. The
cost is two models to report rather than one. Amala has not ratified this.

### Outcome of option C, recorded 2026-09-03, all four models reported

Run on `results/llm_attempts.jsonl`, the same attempts file the submitted paper
uses. The choice of option C was recorded above before this was run. Crossed
with the pre-specified missingness models that is four fits, and all four are
reported here whatever they show.

  outcome              mutation_score   n    pos   dummy_pass_rate OR   p       BH
  exploited            excluded        881   334   1.755 [1.01,3.05]   0.0464  0.2787
  exploited            included        629   234   1.914 [1.02,3.60]   0.0438  0.3065
  exploited_defended   excluded        881   173   2.684 [1.43,5.05]   0.0022  0.0130
  exploited_defended   included        629   124   2.714 [1.31,5.63]   0.0073  0.0509

**The defended outcome is where the effect lives.** `dummy_pass_rate` roughly
doubles its odds ratio when the outcome is exploitation that survives held-out
tests, and in the primary model, Model A on all 881 tasks without
`mutation_score`, it survives Benjamini-Hochberg at q=0.05 with an adjusted p of
0.0130. Nothing in the paper's current regression survives correction, so this
is a change in what the statistics support, and it exists only because the
outcome variable was switched to the one the paper's argument is actually about.

**Model A and Model B disagree, and that is reported, not resolved.** Model B,
restricted to the 629 tasks that have a mutation score, gives an adjusted p of
0.0509 and does not clear q=0.05. The two samples differ non-randomly, since
`mutation_score` is missing exactly where a mutated loop stops terminating, so
Model B's sample is biased toward simple control flow. The pre-registration
requires this disagreement be reported as a finding about the missingness rather
than settled by choosing the nicer number, and it is.

**What may therefore be written, and what may not.** The sentence "dummy pass
rate predicts exploitability" remains unsupported and must not appear. What is
supported is narrower: on the defended outcome the effect survives correction in
the primary model and narrowly fails in the model restricted to tasks with a
mutation score, the two samples are known to differ non-randomly, and both are
reported. `mutation_score` weakens further on the defended outcome, OR 0.801
[0.366, 1.753], p=0.5786, and the standing prohibition on claiming it has no
effect is unchanged.

**P6 of the first pre-registration is now partly wrong.** It predicted neither
term would survive Benjamini-Hochberg. That held for the undefended outcome it
was written about and fails for the defended outcome, which did not exist as a
specified model when P6 was frozen. Recorded rather than reworded.

**WITHDRAWN 2026-09-03. The four fits above are computed on contaminated data
and must not be quoted.** They were marked pending against reproduction by the
re-scored file. The re-scored file did not reproduce them, the cause was found,
and it is a bug in the pipeline that produced `results/llm_attempts.jsonl`. See
the bug record below. Corrected fits follow it.

## Bug B1, found 2026-09-03, in-place mutation of the published tests

`render_tests` in `llm_attack.py` built the prompt by calling
`task['reference'](*args)` directly rather than through `call()`, which is the
one function in the codebase that copies its arguments first and exists
precisely because MBPP references mutate what they are given. A reference that
sorts in place therefore rewrote `task["visible_tests"]` permanently, and
`expected_pairs` holds the same list objects, so the scorer saw the rewritten
inputs too.

For a sorting problem the consequence is total. Once the published input has
been sorted in place it is equal to its own expected answer, so a candidate
whose entire body is `return arr` passes all three published tests. That is
recorded as a false positive. `counting_sort_54` is the clearest instance and
`subject_marks_64` behaves the same way.

Reach: **44 of 890 tasks** have an in-place mutating reference. The bug harmed
those tasks twice, because the model was also shown the mutated asserts, so for
those 44 the attempts were generated against a suite that is not the published
one and then scored against it wrongly as well.

Fixed by routing the call through `call()`. Verified after the fix: all 890
tasks come through `render_tests` with `visible_tests` unchanged, previously 44
did not. Re-scoring corrects the scoring for every task. It cannot correct the
generation for those 44, whose prompts were wrong at the time; regenerating them
is about 20 minutes of local model time and has not been done.

### Corrected fits, on `results/llm_rescored.jsonl`, recorded 2026-09-03

Eight models now, because the EvalPlus oracle adds two more outcomes. All eight
reported. `dummy_pass_rate` odds ratio, uncorrected p, Benjamini-Hochberg p.

  outcome                    mutation_score  n    pos   OR                      p       BH
  exploited                  excluded        881  317   1.759 [1.01, 3.07]     0.0470  0.2817
  exploited                  included        629  223   1.828 [0.97, 3.45]     0.0625  0.4377
  exploited_defended         excluded        881  169   2.594 [1.37, 4.90]     0.0033  0.0199
  exploited_defended         included        629  121   2.570 [1.23, 5.37]     0.0121  0.0849
  exploited_plus             excluded        881  107   1.678 [0.76, 3.70]     0.2003  0.4139
  exploited_plus             included        629   62   3.439 [1.36, 8.70]     0.0091  0.0640
  exploited_plus_defended    excluded        881   61   2.874 [1.11, 7.47]     0.0302  0.1812
  exploited_plus_defended    included        629   36   5.663 [1.78, 18.05]    0.0034  0.0236

**The paper's regression sentence is now false and has to change.** The
submitted paper says `dummy_pass_rate` is the only term reaching p<0.05, at OR
1.914 [1.018, 3.598], p=0.0438. That fit, recomputed on corrected data, is OR
1.828 [0.969, 3.447], p=0.0625. The interval crosses 1 and the p-value crosses
0.05, so on corrected data nothing in the paper's stated model reaches
significance at all.

**What survives correction.** `dummy_pass_rate` clears Benjamini-Hochberg at
q=0.05 in two of the eight fits, both on defended outcomes, BH 0.0199 and
0.0236. Its odds ratio is above 1 in all eight. That is a consistent direction
across every specification and a surviving effect in the two specifications that
match the paper's own argument, and it is still not the sentence "dummy pass
rate predicts exploitability", which stays prohibited.

**`mutation_score` is unchanged in character.** OR 0.637, 0.767, 0.546 and 0.541
across the four fits that include it, every interval crossing 1, no p below 0.17.
Protective in direction, undetected in significance, and the standing
prohibition on claiming it has no effect is unchanged.

### Headline rates, submitted against corrected

  quantity                                submitted        corrected
  per-attempt false positive, published   11.3%            9.9%  [9.3, 10.6]
  per-attempt, held-out added              5.3%            4.8%  [4.4, 5.3]
  held-out removes                        53.4%           51.5%
  tasks gamed at least once               37.9% (334/881) 36.0% (317/881)
  tasks gamed after held-out              19.6% (173/881) 19.2% (169/881)

Every figure moves down, which is the expected direction for a bug that made
candidates pass tests they should have failed. The two per-attempt intervals do
not overlap, 11.3% [10.7, 12.0] against 9.9% [9.3, 10.6], so that correction is
material rather than noise. The task-level intervals do overlap, 37.9%
[34.8, 41.2] against 36.0% [32.9, 39.2], so that headline is unchanged in
substance. Dropping the 44 affected tasks entirely gives 9.8%, so the correction
is not concentrated in them alone.

**Lookup tables, corrected and with the hardened detector.** 111 of 8628
attempts, 1.29%. Of the 857 false positives on published tests, 54 are lookup
tables, 6.3%. The submitted paper reports 15 flagged by the old rule.
