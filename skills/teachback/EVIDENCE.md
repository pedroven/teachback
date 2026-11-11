# Teachback — the evidence

Why the rules in `SKILL.md` have the shape they do.

- **Anthropic, January 2026, n=52** ([study](https://www.anthropic.com/research/AI-assistance-coding-skills),
  [paper](https://arxiv.org/html/2601.20245v1)). Developers learning an
  unfamiliar library with AI scored 17% lower on an unaided comprehension
  quiz (d = 0.738, p = 0.010) — with *no* significant speed gain. Debugging
  was the worst subscore; the control group hit a median of 3 library-specific
  errors versus 1. Within the AI arm, the usage patterns that preserved
  scores were conceptual questioning and generate-then-interrogate; the ones
  that destroyed them were delegation, escalating reliance, and iterative
  AI debugging. Authors note the study used a chat interface and that
  agentic tools would likely show a larger effect.
- **Socratic guidance vs prompt refinement, 2026, n=66 then 52**
  ([paper](https://arxiv.org/abs/2607.03303)). A graduate-level course, so the
  closest thing to a competent practitioner in this literature. Two LLM tutors
  over six weeks — one structuring interaction as dialogic questioning, one
  helping formulate better prompts — then three weeks on an unconstrained LLM.
  Identical task performance during the guided phase; the questioned group
  came out with higher later learning gains and carried understanding-driven
  prompting into the unconstrained tool. They also *"perceived the tutor as
  less efficient."* Expect the user to report exactly that. It is the
  predicted subjective reading of a mode that works, not evidence against it.
- **Sankaranarayanan, ACM Learning at Scale 2026, n=78**
  ([paper](https://arxiv.org/html/2602.20206v2)). The one intervention with a
  number. An explanation gate on every AI insertion of 2+ lines. Unaided
  repair afterward: 69.2% manual, 23.1% unrestricted AI, 61.5% gated AI
  (χ²(2) = 13.8, p = .001), at a 34% time cost. The gate recovered nearly all
  the lost capability without hurting output quality.
- **Bastani et al., PNAS** ([paper](https://www.pnas.org/doi/10.1073/pnas.2422633122)).
  Unguarded GPT-4 gave students +48% while using it and −17% on the unaided
  exam versus never having access. A hints-not-answers variant largely
  erased the harm.
- **Alfieri et al. 2011 meta-analysis, 164 studies**
  ([paper](https://physics.uwyo.edu/~rudim/S14_JEduPsych_DoesDiscoveryLrngEnhance.pdf)).
  Unassisted discovery loses to explicit instruction (d = −0.38); discovery
  *with* feedback, worked examples, scaffolding and elicited explanations
  beats it (d = +0.30). Pure Socratic questioning with no support is the
  worst of the options, not the best.
- **Bisra et al. 2018 meta-analysis, 69 effect sizes**
  ([paper](https://link.springer.com/article/10.1007/s10648-018-9434-x)).
  Inducing self-explanation: g = 0.55, across conceptual and procedural
  knowledge alike.
- **Expertise reversal** ([meta-analysis](https://www.sciencedirect.com/science/article/pii/S0959475225000660)).
  Worked examples help novices and hurt the already-competent, which is why
  rule 3 is per piece rather than per session.
- **Brief but Impactful, LAK 2026, 191 students, 2,075 hours**
  ([paper](https://arxiv.org/abs/2601.09994)). Human tutor check-ins during
  math practice lifted engagement during and after a visit *"irrespective of
  visit length"*, and *"concrete, stepwise scaffolding with explicit work
  organization"* lifted it most. Middle-school math, so transfer is weak, but
  the shape it favours — several short well-timed contacts over one long one —
  is the shape rule 1 now asks for.

**Honest limitation:** the intervention studies with the cleanest numbers ran
on novices and juniors; the graduate-level result above is the closest to a
senior engineer and it measured LLM-use habits, not a real ticket. Rules 1
and 2 carry real experimental support; rule 3 is extrapolation from the
expertise-reversal literature, not a measured result; rule 5 rests on
scaffolding theory rather than a trial that fixed the fade point.
