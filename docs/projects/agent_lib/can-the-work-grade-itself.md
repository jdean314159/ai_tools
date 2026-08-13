# Before You Automate It, Ask Whether the Work Can Grade Itself

## The hidden condition behind every "AI agents now work for hours" headline

If you've been following AI news this year, you've seen the numbers. Agents completing fourteen-hour coding tasks. Background agents running thirty hours on a single feature. Benchmarks showing the length of work AI can handle autonomously doubling roughly every four to seven months. The framing is consistent: autonomy has arrived, and it's compounding fast.

I don't think the numbers are fake. I think they come with a condition that almost never survives the retelling — and if you're deciding which of your company's processes to hand to an AI agent, that condition is the single most useful thing to understand.

Here it is:

**In every domain posting those long-horizon numbers, the work grades itself.**

A coding agent writes code and runs the tests. The tests pass or they fail. That's not a small detail — it's the entire mechanism. The agent doesn't need to *judge* whether it's finished, because something outside it answers that question, for free, every few minutes. It also answers two other questions: am I on the right track, and did my last move help?

Take that away, and all three questions fall back on the AI's own judgment. That turns out to be the thing that hasn't improved nearly as fast as the headlines suggest.

I spent several weeks measuring how much it hasn't. Here's what I found, and what I'd do with it if I were spending a budget.

---

## The test

I gave an AI agent a research task: answer questions about a large codebase it couldn't hold in memory all at once. Where is this thing defined? What calls it? Trace this path.

It got read-only access to search and read files, and a fixed budget — roughly the equivalent of a metered compute allowance that runs out. Then it worked on its own.

The important design choice: **there was no scorekeeper.** No test suite. Nothing in the environment could tell the agent whether it had found enough. It had to decide that for itself.

That's not an artificial handicap. That's what most business processes look like. *Find every place we handle customer data. Summarize what changed in this contract. Figure out which of these invoices is wrong. Pull together everything we know about this account before the renewal call.* None of those come with a built-in grader. Somebody has to decide when the work is done, and if you're automating, that somebody is the AI.

The failure I set out to fix was blunt and repeatable. Three of four early runs burned through the *entire* budget and never produced an answer at all.

Not because the agent was bad at the work. It found roughly 97% of the relevant material. It simply never concluded. It kept looking, past the point of having what it needed, until the money ran out.

That's the failure mode nobody puts in a demo.

---

## Two attempts to catch it, and why they failed

My first instinct was the obvious one: if the agent is going in circles, detect the circles and stop it.

That failed for a reason worth sharing, because it's a general trap. I built the detector based on a published technique — a real technique, used successfully elsewhere. But it was designed to sift through *training data* in bulk, where flagging some good material by mistake costs nothing. I was using it as an emergency brake on live work, where a mistaken stop kills a run that was about to succeed.

When I finally tested it against a run that had *succeeded*, it flagged that one too. Every time. A successful agent repeats itself just as much as a stuck one — it revisits files, reruns similar searches, follows the same patterns. The published work never ran that comparison, because nobody publishes the case where their method fires on a good run.

**Lesson one: almost no published AI technique is tested against the case where it's wrong.** If a vendor shows you their system catching a problem, ask what it does to a process that was working fine.

My second attempt watched the agent's actual behavior instead of its words — is it re-reading the same files, is it learning anything new? On recorded runs it worked perfectly. Caught all three failures, left the successful run alone.

Then I ran it live, and it sat silent while the agent burned its entire budget again.

The reason is the most useful thing I learned all year, and you don't need any technical background to see it:

> Partway through, the agent went **six straight steps** without turning up anything new — and then recovered, found what it needed, and kept going productively.
>
> At the end, it stalled out for **three steps** and never recovered. That was the fatal one.
>
> To avoid interrupting the first, you need a rule that tolerates six quiet steps. To catch the second, you need one that fires after three. **There is no number that does both.**

This isn't a tuning problem. It's not fixable with a better threshold or a smarter model. From the outside, productive struggle and terminal flailing look *identical*. A stretch of no visible progress is what real work looks like right before a breakthrough, and also what failure looks like right before a write-off.

Any human manager will recognize this immediately. It's why you can't manage knowledge work purely by activity metrics. It turns out you can't manage an AI agent that way either.

---

## The summary that was secretly cheating

Third attempt: if you can't reliably detect the stall, just cut the agent off at 70% of budget and have it write up whatever it's found.

This worked beautifully. I compressed everything the agent had gathered into a compact briefing — about a sixteenth of the raw material — and it produced a near-complete answer, cheaply. Roughly 22% savings, same quality.

Then I noticed the compression step was using hints derived from knowing what the right answer looked like. I had, without quite intending to, told it what to keep.

So I rebuilt it honestly, with no knowledge of the answer. Just: keep everything the agent actually observed, deduplicated.

The briefing got **2.8 times larger**. And the answer got *worse* — more material in, less accuracy out. Worse still, the bigger briefing no longer fit in the budget left at the point where the agent's research was most complete. The method destroyed itself.

**Lesson two: efficiency gains that depend on knowing the answer aren't efficiency gains.** This is worth holding onto when you evaluate demos. If a system summarizes, filters, or prioritizes impressively, ask what it's using to decide what matters — and whether that information will exist when the task is real and nobody knows the answer yet.

---

## What actually worked, and by how much

One thing helped. Not a detector — a change to how the agent works.

I required it to maintain an explicit checklist: here is what I've been asked to find, here's what's still open, here's what I've resolved and the specific evidence that resolved it. The system refuses to let it finish while anything is still open.

Then I ran a proper experiment: fourteen tasks, selected mechanically so I couldn't cherry-pick favorable ones, each run twice — once with the checklist, once without. Everything else identical. I wrote down what would count as success *before* seeing any results.

On the hardest six tasks:

| | Without checklist | With checklist |
|---|---|---|
| **Produced any answer at all** | 0 of 6 | 3 of 6 |
| **Answer was correct** | 0 of 6 | 0 of 6 |
| **Cost** | — | ~20% less |

Read both rows.

Without the checklist, the agent finished *zero* of six. With it, half. That's a real, meaningful improvement in the thing I was trying to fix, and it came 20% cheaper.

And not one answer was fully correct either way. The ones that terminated cited sloppy evidence — pointing at a whole page to support a claim that lives on one line — and one confidently asserted something the source didn't say.

Structure bought me **control**. It did not buy me **judgment**. The agent stopped running away. It did not start being right.

By my own pre-written standard, the result was *inconclusive*. The numbers lean favorable and I'm reporting it as inconclusive anyway, because I decided what would count before I looked. I'd encourage you to be suspicious of anyone who can't say the same about their numbers.

---

## What this means for your automation shortlist

Sort your candidate processes by one question: **does something outside the AI check the work?**

**Tasks that grade themselves** — writing code with a test suite, filling forms a validator accepts or rejects, data entry that reconciles against a control total, anything where a downstream system says yes or no. These are the regime the headline numbers describe. Expect them to roughly hold. Automate here first.

**Tasks that don't** — research, review, synthesis, "find everything about X," judgment calls, anything where a person is the only check. Expect long-horizon claims not to transfer. The agent may do 97% of the work and still never tell you it's finished, or finish confidently while wrong.

That second bucket isn't off-limits. It's where you keep a person in the loop, cap the scope, and build a checklist into the process — which is exactly what the experiment above measured, at exactly the modest improvement it found.

Three things worth asking any vendor:

1. **What happens when your system is wrong about a process that was working?** Not the success case. The false alarm.
2. **What does your system use to decide what's important?** If it needs to know the answer, it won't help on real work.
3. **What did you decide would count as success, and when did you decide it?**

---

## What I'm not claiming

One model, running locally on my own hardware — not a frontier system. I never compared model sizes, so I can't tell you whether a bigger model fixes this. One suggestive data point says it's not that simple: in a separate test, a model more than four times larger performed *worse* at exactly this kind of judgment.

One task type, one run each, no repetition. Nothing here is a statistical result — it's an engineering finding from a controlled setup, which is a lower bar than a study and a much higher one than a demo.

And it's worth noting the sober sources agree. The most cited benchmark's famous horizon figure is a *50% reliability* number — a coin flip at that duration. Its 80%-reliability figure is a small fraction as long. The benchmark closest to my setup finds frontier models completing only about 62% of tasks past twenty steps. This year's International AI Safety Report states plainly that current agents reliably fail on longer tasks and lose track of their progress.

The technology is genuinely improving, quickly. But "agents work autonomously for hours" is a claim about a specific kind of work, in a specific kind of environment, at a specific and often unstated level of reliability.

Before you buy it, check whether your work looks like that work.
