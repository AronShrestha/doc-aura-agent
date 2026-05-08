# Documentation Standards — A Research-Backed Reference

> **Purpose of this document.** Aura's "Living Source Suite" should not just match what most repos have. It should aspire to what the *best* technical documentation in the industry looks like. This document captures, with sources, what that bar is — the frameworks, the style guides, the categories, the examples to study, and the quality bars. It's meant to be read once by the whole team, then kept as a reference when we extend Aura post-MVP.

> **How to use it.** Part 1 covers the foundational frameworks (Diátaxis, C4, arc42, ADRs). Part 2 is the comprehensive inventory of what gold-standard documentation surfaces. Part 3 covers style and tone. Part 4 is mechanical quality bars. Part 5 is the canonical examples to study. Part 6 maps it all back to Aura — what we already cover, what we could cover next, and what we should deliberately not try to replace.

---

## Part 1 — The Foundational Frameworks

If you only learn one thing from this document, learn Diátaxis. It is the dominant modern taxonomy for technical documentation and the spine that every other consideration hangs on.

### 1.1 Diátaxis — the four-quadrant model

Diátaxis was developed by Daniele Procida (now at Canonical, formerly at Divio). It is now the official documentation framework for Django, NumPy, Cloudflare, Gatsby, OpenStack, and a long list of others. Source: https://diataxis.fr.

The thesis is that every piece of technical documentation falls into exactly one of four categories, and that confusing the categories is the single biggest reason documentation is bad. The four categories are organized along two axes: *practical vs. theoretical*, and *acquisition vs. application*.

**Tutorials** — learning-oriented. The reader is acquiring a new skill, practically, by being walked through a concrete experience. The promise is "you will be able to do X by the end." A tutorial is for someone who knows nothing yet. It must work end to end; surprise and stumbling are unacceptable. The Django tutorial, the React quickstart, "Build your first Rails app" — these are tutorials.

**How-to guides** — task-oriented. The reader has a specific real-world goal ("how do I configure CORS in FastAPI?") and wants the steps to achieve it. Unlike tutorials, the reader is already competent; they don't need pedagogy. How-to guides are recipes: focused, assume context, jump straight to actions.

**Reference** — information-oriented. The reader needs to look something up. API references, function signatures, configuration option lists, error code tables. Reference is austere. It describes the machinery, not how to use it. The OpenAPI doc is reference.

**Explanation** — understanding-oriented. The reader wants the *why* — the mental model, the trade-offs, the historical context, the architecture. "How does Aura's PR drift detection work?" is an explanation question. Explanation can wander a little, can argue for design choices, can include alternatives that were considered and rejected. It's the only quadrant where tone of voice has room.

The framework is powerful because the four categories require *different writing styles, different structures, and different reader assumptions*. When a "tutorial" sneaks reference material into the middle, the tutorial breaks. When reference docs try to be tutorials, they bloat and become unsearchable. Diátaxis tells you to keep them separate.

Aura's eight artifact categories all live in the **reference** quadrant. That's where automation can dominate. The other three quadrants need humans (or, post-MVP, much more sophisticated synthesis). This is fine — reference is the most expensive quadrant to maintain by hand, so automating it is the highest-leverage move.

### 1.2 C4 Model — architecture diagrams that don't suck

Most architecture diagrams are useless because they conflate levels of abstraction. The C4 Model, by Simon Brown, fixes this with four explicit levels of zoom. Source: https://c4model.com.

**Level 1 — System Context.** Shows the system in its environment: the people who use it and the other systems it talks to. Big boxes, no internal detail. Fits on one slide. This is the diagram for executives and external stakeholders.

**Level 2 — Containers.** A "container" is a separately-runnable thing: a web app, a mobile app, a database, a microservice, a worker. Shows how the *deployable units* communicate. This is the diagram for new engineers joining the team.

**Level 3 — Components.** Inside each container, the major modules and their relationships. This is where Aura's `Service` and `Module` artifacts live. Diagrams here change as the code changes.

**Level 4 — Code.** Class diagrams, sequence diagrams, the lowest level. Most teams skip this — modern IDEs render it on demand and a static version goes stale instantly. C4 itself recommends generating these only when needed.

The model also defines four *supplementary* diagram types — system landscape (multiple systems together), dynamic (sequence-style), deployment, and decision — that complement the four levels.

C4 is opinionated about notation: simple shapes, clear labels (every box has a name, a type, and a one-sentence description; every line has a verb), no UML pedantry. The accompanying tool, Structurizr, generates diagrams from a DSL — it is one of the few examples of "documentation as code" that consistently produces good output.

Aura's architecture Mermaid diagram (synthesized in T12) is roughly a C4 Container or Component diagram. We should explicitly target Level 2/3 — that's the level engineers actually want.

### 1.3 arc42 — a complete architecture documentation template

Where C4 covers diagrams, arc42 covers the *whole* architecture document. Source: https://arc42.org. It is a 12-section template, originally German-origin, now widely used across Europe and increasingly elsewhere. The 12 sections are:

1. Introduction and Goals
2. Architecture Constraints
3. Context and Scope
4. Solution Strategy
5. Building Block View (this is where C4 fits)
6. Runtime View (sequence diagrams of key flows)
7. Deployment View
8. Cross-cutting Concepts (logging, error handling, security)
9. Architectural Decisions (this is where ADRs fit)
10. Quality Requirements
11. Risks and Technical Debt
12. Glossary

When to reach for arc42 vs. C4: C4 is for the diagrams; arc42 is for the document those diagrams live inside. They compose well. arc42 is heavier than most projects need — but its section list is a useful checklist of "things a serious architecture document should address."

### 1.4 ADRs — Architectural Decision Records

ADRs were popularized by Michael Nygard's 2011 blog post "Documenting Architecture Decisions." Original post: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions. They are now standard at Spotify, Atlassian, ThoughtWorks, and most well-run engineering orgs.

The format is short and rigid:

- **Title** (a short verb phrase, e.g. "Use PostgreSQL for the primary data store")
- **Status** (proposed, accepted, deprecated, superseded by ADR-NNN)
- **Context** (the forces at play — technical, political, organizational)
- **Decision** (what we are going to do)
- **Consequences** (what becomes easier, what becomes harder, what trade-offs we accept)

ADRs live in the repo, typically in `docs/adr/` or `docs/decisions/`, numbered sequentially: `0001-record-architecture-decisions.md`, `0002-use-postgresql.md`, etc. The first ADR is always the meta-decision: "we will record architectural decisions as ADRs." That sounds silly but is genuinely the convention.

ADRs are append-only history. When a decision is reversed, you don't edit the old ADR — you write a new one whose status is "Supersedes ADR-NNN" and update the old one's status to "Superseded by ADR-MMM." This preserves the *reasoning trail*, which is the whole point.

The MADR ("Markdown ADR") project at https://adr.github.io provides templates and tooling. Most teams use a slightly opinionated subset.

ADRs are also the most-requested missing piece in Aura's MVP. Drift detection tells you *what* changed; ADRs are the *why*. A post-MVP version of Aura could prompt for an ADR when a CRITICAL drift is detected.

### 1.5 Documentation as Code

A cluster of practices, championed by the Write the Docs community (https://www.writethedocs.org). The core ideas:

- Documentation lives in the same repo as the code, in plain text (Markdown, AsciiDoc, reST).
- Documentation changes go through pull requests, code review, and CI.
- Code examples in documentation are *executed* in CI, not just stared at.
- Versioned documentation is generated from versioned source.
- Reference documentation is *generated* from the code where possible (OpenAPI from FastAPI, JSDoc from JS, rustdoc from Rust).

Aura is fundamentally a docs-as-code tool. The Living Source Suite is a docs-as-code artifact, just one whose primary author is an LLM rather than a human.

---

## Part 2 — The Complete Documentation Inventory

This is the comprehensive list of what gold-standard documentation surfaces. It is organized in tiers because not every project needs every tier. A small open-source library needs Tier 1 plus a slice of Tier 2. A SaaS platform needs all six tiers.

### Tier 1 — Repository docs (the universal floor)

These should exist in *every* serious repo. If they're missing, Aura's reviewer-onboarding pitch lands hard.

**README.md** — the front door. The anatomy of a great README, distilled from studying dozens of widely-starred repos:

1. A one-sentence description, immediately under the title. Tells someone arriving from a Google search or a tweet whether to keep reading.
2. Status badges: build status, current version, license, package manager (npm/PyPI), maybe a link to docs site. Six is plenty; thirty is hostile.
3. A demo — animated GIF or screenshot. For CLI tools, an asciinema recording. For UI projects, a 5-second clip. Linked rather than embedded, to keep clones fast.
4. **Why this exists.** One paragraph. The most-skipped section, and the one that matters most. What problem does this solve? Who is it for?
5. **Install.** Copy-pasteable. One command if possible.
6. **Quickstart.** The smallest piece of code that produces a visible result. Five to fifteen lines. The reader should run it and feel "ah, I get it."
7. Links to deeper documentation. Don't fold the whole manual into the README.
8. Contributing pointer.
9. License.

The art of a great README is restraint. Stripe's open-source SDK READMEs, the React README, the Django README — all short. Long READMEs are usually compensating for missing docs elsewhere.

**LICENSE** — non-negotiable. Use SPDX identifiers (`MIT`, `Apache-2.0`). The choice matters legally; ChooseALicense.com is a defensible reference. Lacking a license file means the code is "all rights reserved" by default in most jurisdictions, making contribution and use legally fraught.

**CONTRIBUTING.md** — explains how to set up, run tests, what the branch model is, what gets accepted. Saves hundreds of hours of repeated questions over a project's lifetime. GitHub surfaces it automatically when someone opens an issue or PR.

**CODE_OF_CONDUCT.md** — for any project taking outside contributions, this signals norms. The Contributor Covenant (https://www.contributor-covenant.org) is the de facto standard, used by Linux, Rails, Node, Kubernetes.

**SECURITY.md** — describes how to report vulnerabilities responsibly. GitHub surfaces it on the security tab. A fifteen-line file with an email address and a response-time commitment is enough.

**CHANGELOG.md** — the "Keep a Changelog" format at https://keepachangelog.com is the standard. Versions in reverse chronological order; under each version, sections for `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. Pairs naturally with Semantic Versioning (https://semver.org). Auto-generated changelogs from commit messages tend to be lower quality; the best changelogs are hand-curated, even if assisted by tooling.

**Issue and PR templates** — `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE.md`. They look like bureaucracy but are high-leverage: they deflect bad bug reports and orient first-time contributors.

**Auxiliary files** — `.editorconfig` (cross-IDE indentation rules), `.gitignore`, `.gitattributes`, `.pre-commit-config.yaml`. Each one is small but signals seriousness.

### Tier 2 — API and library reference

For anything with a programmable surface.

**OpenAPI / AsyncAPI / GraphQL schema** — the machine-readable contract. OpenAPI 3.1 (https://spec.openapis.org/oas/v3.1.0) is the dominant standard for REST. AsyncAPI for event-driven; GraphQL has its own SDL. The spec file should be checked into the repo, generated from code where possible, and rendered into a navigable reference site (Redocly, Swagger UI, or custom — Stripe's reference is custom and worth studying).

**Authentication.** A dedicated page. Covers: how tokens are obtained, token lifetimes, scope/permission model, refresh flows, header format, error responses for auth failures. This page is the most-bookmarked page in any API's docs.

**Errors.** A canonical list of error codes, what each one means, what the user should do about it, and what happens if they retry. Twilio's error code reference (https://www.twilio.com/docs/api/errors) is the gold standard — every error has its own URL, suggested causes, and remediation steps.

**Rate limits and quotas.** What the limits are, how they're computed (per-user, per-IP, per-token, sliding window vs. fixed), what response code they return, how to read remaining-quota headers, and what happens when you exceed.

**Pagination.** API design 101 says you must commit to a pagination model and document it. Cursor-based and offset-based both work; mixing them does not. Document the parameter names, the format of the cursor, and how to detect the last page.

**Versioning policy.** How are versions numbered? Are there breaking changes? What is the deprecation timeline? How long are old versions supported? Stripe's date-based API versioning (every account is pinned to a date, breaking changes only ship behind a new date) is admired but rare; most APIs use `v1`, `v2`, in the URL.

**Migration guides.** Whenever a major version ships, the docs need a side-by-side guide showing every breaking change, the old syntax, the new syntax, and a codemod or sed command if possible.

**Webhooks.** If the API has webhooks: payload schemas, signature verification, retry behavior, idempotency keys, and a way to inspect recent deliveries. GitHub's webhook docs are exemplary.

**SDK / client library docs.** Each language gets its own quickstart and reference. Generated docs (Sphinx, JSDoc, rustdoc, godoc) are the floor; gold-standard SDK docs include hand-written examples for the top 20 use cases.

### Tier 3 — User-facing product documentation

For SaaS, dev tools, anything with non-trivial user surface.

**Quickstart** — the *fastest* path from "I have an account" to "I have something working." Five to fifteen minutes max. This is the quadrant boundary between "tutorial" and "how-to" — slightly tutorial-shaped, slightly how-to-shaped. Aim for "ten lines and a smile."

**Tutorials.** Plural. Pedagogy-first walks through realistic scenarios. They build in difficulty. The Django tutorial famously walks the reader through building a polling app over six lessons; the value is not the polling app, it's the *journey* of seeing every Django subsystem in context.

**How-to guides.** Task-organized library. Each one starts with a goal and gets to the point. Title format: "How to X" or "Configure X" or "Migrate from X to Y." Each one stands alone — no narrative threading required.

**Concepts.** The "explanation" quadrant. Covers the mental model: what is a "user," what is a "session," what is a "workspace," how do they relate? Diagrams, often. Deliberately discursive. Tailwind's "Adding Custom Styles" page is a good example — it explains the tension between utility classes and custom CSS at length, with no apology for the digression.

**FAQ.** Answers to questions that genuinely keep coming up. Don't write FAQs preemptively; harvest them from real support tickets, Discord channels, GitHub issues. A made-up FAQ is worse than no FAQ.

**Glossary.** A list of terms and their precise definitions. Sounds boring; saves arguments. Especially important when the product invents new terms ("organization" vs. "team" vs. "workspace") or repurposes common ones ("token" can mean half a dozen different things).

**Troubleshooting.** Symptom → diagnosis → fix. Often overlapping with FAQ but more action-oriented. A great troubleshooting page surfaces logs to look at and commands to run.

**Status page.** Live operational status, historical incident timeline, scheduled maintenance. Statuspage.io is the dominant hosted option; many teams roll their own with Cachet or similar. Independent of the docs site, but linked from it.

### Tier 4 — Architecture and design docs

For teams of more than ~5 engineers, or any project taking outside architectural contributions.

**System overview.** A C4 Level 1 (Context) diagram and one paragraph. This is what new engineers read on day one.

**Container and component diagrams** (C4 Levels 2 and 3). Generated where possible; updated when major components change.

**ADR log.** As described in Part 1. The ADR folder is the single most useful artifact for an engineer trying to understand "why is this thing the way it is?"

**Data model / ERD.** Entity-relationship diagram. dbdocs.io and dbdiagram.io can render these from a DSL; many teams generate them from migrations. The ERD is also one of Aura's outputs (the `DataModel` artifact category, particularly when foreign-key relationships are surfaced).

**Sequence diagrams of key flows.** Two to five hand-picked flows. Signup, payment, the most-traveled API path. Mermaid sequence diagrams render natively on GitHub. Aura's `Flow` artifact category produces exactly these.

**Deployment topology.** What runs where? Kubernetes namespaces, AWS regions, edge nodes, queues, datastores. Most teams have this somewhere; few keep it current. Inspecting infrastructure as code (Terraform, CloudFormation, Pulumi) is the closest thing to "living" deployment docs.

**Threat model.** Following STRIDE or another systematic approach. Identifies trust boundaries, attack surfaces, and the controls that mitigate each threat. Worth the effort for any system handling money, PII, or production access. OWASP's Threat Modeling Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html) is a workable starting point.

### Tier 5 — Operational and SRE docs

For anything that runs in production with real users depending on it.

**Runbooks.** Per service, per common alert. Each runbook is a specific procedure: "alert X has fired; do Y, Z, then escalate to person W." The point of a runbook is that the *least experienced person on call* can resolve the issue. Runbooks live close to the alert that triggers them — most teams link directly from PagerDuty alerts to a runbook URL.

**On-call playbook.** Higher-level: how does on-call work, what's the rotation, what's the response-time SLA, when is it OK to wake someone up at 3 AM? Onboarding for new on-call engineers depends on this document being honest.

**Postmortems.** After every significant incident. The format Google promotes (https://sre.google/workbook/postmortem-culture/) is widely copied: blameless framing, a timeline, what happened, why, what went well, what went poorly, action items with owners. Postmortems are most valuable when they're collected and re-read — Etsy's "Morgue" tool was the canonical implementation; today GitHub Issues with a `postmortem` label suffices.

**SLOs and SLIs.** What the service's users can expect (availability, latency, error rate). Defined precisely enough that a query against telemetry can confirm or deny the claim. The SRE Workbook (free at sre.google) covers this thoroughly.

**Capacity planning notes.** Current load, headroom, scaling strategy. Often a single living document per service.

**Recovery procedures.** What to do when the database is corrupted? When a region is down? When the deploy pipeline is broken? Game-day exercises validate these.

### Tier 6 — Process and contributor docs

For active projects with multiple contributors.

**Development environment setup.** What we covered in Aura's `00_SETUP.md` — exactly this.

**Build and test instructions.** How to run tests, how to run a subset, how to run them in watch mode, how to debug a failing test. The cost of a confused contributor is hours of someone else's time, usually a senior engineer's.

**Coding style guide.** Or, more accurately, links to: which automated tools enforce style? When a human-judgment call is needed, what's the team's preference? "We use Prettier with default config; for naming things, see this internal wiki page" is enough.

**Branching strategy.** trunk-based, GitHub Flow, GitFlow, environment branches — pick one and document. Tightly coupled to the release process.

**Release process.** Who can release? When? What's the manual checklist? What's automated? Most teams under-document this until the lead release engineer takes a vacation.

**Roadmap.** Public or internal. Public roadmaps build trust with users; internal roadmaps align engineering. Both go stale fast — quarterly is the realistic update cadence.

---

## Part 3 — Style and Tone

### 3.1 The major style guides

Choose one as the team's reference. Don't write your own from scratch; reference an established one and add a few project-specific overrides.

**Google Developer Documentation Style Guide** at https://developers.google.com/style. The most thorough free option for technical docs specifically. Covers everything from punctuation to inclusive language to how to write a procedure. Default recommendation for engineering-led teams.

**Microsoft Writing Style Guide** at https://learn.microsoft.com/en-us/style-guide/welcome/. Slightly more "consumer-product" tone than Google's. Excellent on UI terminology — "select" vs. "click," when to use "tap." Strong on accessibility language.

**Apple Style Guide** at https://support.apple.com/guide/applestyleguide/welcome/web. Marketing-leaning; less directly applicable to internal engineering docs but interesting on consistency.

**Mailchimp Content Style Guide** at https://styleguide.mailchimp.com. Brand-flavored but the "Voice and Tone" section is genuinely useful and widely copied.

**The Chicago Manual of Style.** Not free, but the reference of last resort for any English question your project's style guide doesn't cover.

**A11y / inclusive language references.** The Conscious Style Guide (https://consciousstyleguide.com) and Google's inclusive-language section are good starting points. A docs site that uses outdated terms ("blacklist," "master/slave") looks sloppy and signals a team that hasn't paid attention.

### 3.2 Universal principles

Across every guide, the same handful of principles surface.

**Front-load the answer.** The first sentence or paragraph should answer the most likely reader question. Hide the qualifications, exceptions, and prerequisites further down. Ten readers in eleven will leave after the first paragraph; serve them.

**Active voice, second person.** "You can configure rate limits in the dashboard," not "Rate limits can be configured by users in the dashboard." Direct address creates the implicit dialogue that makes good docs feel helpful.

**Sentence case for headings.** "Configure rate limits," not "Configure Rate Limits." Title Case looks dated and is harder to read.

**Code samples that run.** Every code block should be tested in CI — ideally via a doctest-like mechanism, at minimum via copy-paste into a clean environment. Stripe's docs run their code samples on every commit.

**One canonical example per concept.** When five examples could illustrate the same thing, pick one, name its variables consistently throughout the docs, and reuse them. Readers internalize the example; switching examples each page wastes their cognition.

**Show, don't tell.** A working code snippet beats a paragraph of description. A diagram beats a paragraph of architectural text. An animated GIF beats a paragraph of UI description.

**Avoid "simply," "just," and "easily."** They're either dishonest (the thing is not, in fact, simple) or condescending (the reader should be able to figure it out). Either way they damage credibility. The Google guide is explicit about this.

**Signal what version, what platform.** Where the answer differs by Python version, OS, or service plan, say so before the reader runs the wrong command.

**Last-updated visible.** Every page shows when it was last touched. Readers calibrate trust based on staleness.

---

## Part 4 — Mechanical Quality Bars

Things that don't show up in any one page but separate gold-standard docs from the rest.

**Every code example tested.** Most static-site generators support some form of doctest — Sphinx does, mkdocs has plugins, Mintlify has snippet-runner integrations. The bar to clear: someone changes an internal API, and the docs build *fails* until the example is updated.

**Every link checked.** Lychee, htmltest, or markdown-link-check, run in CI on every PR. Internal-link rot is the most common form of docs decay.

**Last-updated and authored-by metadata.** Either generated from git (last commit to touch the file) or written into front-matter. Both have failure modes; the former drifts when files are refactored, the latter goes stale unless someone updates it. Pick one and own its caveats.

**Search that works.** Algolia DocSearch (https://docsearch.algolia.com) is free for open-source docs sites and is the industry standard. Self-hosted alternatives: Typesense, MeiliSearch. The bar: typing three characters surfaces the answer in under 200ms.

**Mobile responsive.** Half the readers are on phones. Code blocks must scroll horizontally without breaking the page; sidebars must collapse; tables must reflow.

**Accessibility (WCAG 2.1 AA at minimum).** Color contrast, keyboard navigation, alt text on every image, semantic headings. Lighthouse and axe-core in CI. Documentation is read by people on assistive tech every day; it's also read in low-light, in bright sunlight, on poor screens — a11y rigor pays off broadly.

**Performance budget.** Docs sites should load in under two seconds on 3G. Most don't. The biggest culprits are: client-side JS frameworks for what is fundamentally a static site, oversized hero images, and poorly-scoped third-party widgets (chat bots especially). Static site generators (Astro, Hugo, Eleventy, Docusaurus, MkDocs, Sphinx) all handle this well if not abused.

**Versioned URLs.** `/docs/v3/quickstart` rather than `/docs/quickstart`. The day a v4 ships, the v3 link in someone's old blog post still works. Docusaurus and Mintlify handle this natively.

**Open Graph / metadata.** Every page has a unique title, description, and (ideally) social-share image. Not vanity — these are what Google indexes and what AI agents extract.

**llms.txt — the emerging AI-agent standard.** A new convention defined at https://llmstxt.org. A `/llms.txt` file at the site root, in Markdown, listing the most important pages for an LLM to read. As of 2025–2026 it is increasingly adopted (Anthropic, Cloudflare, Vercel, Stripe, Mintlify all publish one). Aura should both *consume* `llms.txt` files when present in repos it onboards, and *publish* one for its own dashboard.

**No hostile interruptions.** No popup-on-load asking for an email. No autoplaying video. No cookie banner that occupies a quarter of the screen. The Permitted Cookie Banner is the small one. Docs sites that respect the reader's time get read.

---

## Part 5 — Examples to Study

When you need to know what excellence looks like, go look at it. Each of the following is consistently named in industry "best docs" lists, with cited reasons.

**Stripe** at https://docs.stripe.com. The reigning champion. Reasons to study: the API reference's three-column layout (description, code samples, request/response examples) is widely copied. Code samples are language-switchable, runnable, and stay in sync with the SDKs because they're generated from the same OpenAPI spec. The error reference, the migration guides, and the changelog are all exemplary. Stripe employs documentation engineers — people who write code and prose.

**Twilio** at https://www.twilio.com/docs. The pioneer of "quickstart culture." Every product has a five-minute quickstart in every supported language. The error reference (one URL per error) is the model. Twilio is also exceptionally good at the boundary between conceptual ("what is a TwiML application?") and reference.

**Tailwind CSS** at https://tailwindcss.com/docs. Interactive examples that you can edit and see the result. Excellent at the *concepts* quadrant — the philosophy of utility classes is explained at length, with grace. The visual design of the docs site is itself a design exercise worth studying.

**Vercel** at https://vercel.com/docs. The benchmark for design polish. Light/dark consistency, type system, navigation IA. Read this for what *good UX of documentation* looks like, separate from the words.

**Linear** at https://linear.app/docs. Task-oriented, opinionated, terse. Linear's docs are short — they prioritize *enough* over *exhaustive*. Worth studying for editorial restraint.

**Cloudflare** at https://developers.cloudflare.com. A textbook Diátaxis implementation across an enormous product surface. The information architecture (left-rail navigation, breadcrumbs, sectioning) holds up at scale.

**Django** at https://docs.djangoproject.com. Where Diátaxis was first applied to a major framework. The four-section split (tutorial, topic guides, reference, how-to) is visible in the navigation. Long, dense, accurate. The tutorial in particular is widely imitated.

**React** at https://react.dev. Heavily explanation-leaning — the page on hooks is a small essay on closures and rendering. Demonstrates that explanation can be longform and still excellent.

**Kubernetes** at https://kubernetes.io/docs. The case study in *what scales*. Despite the surface-area problem (Kubernetes is enormous), the docs maintain consistent structure across topics. The "concepts" section, in particular, is what good explanation looks like at scale.

**MDN Web Docs** at https://developer.mozilla.org. The reference for a vast surface. Worth studying for: the consistent compatibility-table convention, the "Examples" section on every page, and the contribution model that has kept it accurate for two decades.

**GitHub's own docs** at https://docs.github.com. Worth studying as a counter-example in places — sheer volume sometimes obscures findability — but the webhook docs and the REST API reference are excellent.

**Honorable mentions worth a click each:** PostgreSQL, Rust, Stripe Connect (separate from the main Stripe docs and instructive on how to do "advanced topics" without losing beginners), Apollo GraphQL, Honeycomb, Datadog.

---

## Part 6 — How This Maps to Aura

The point of all this research is to make a deliberate choice about what Aura tries to produce versus what it leaves to humans. The Living Source Suite cannot generate every kind of documentation listed above, nor should it. The right framing is: **Aura automates the reference quadrant, so that human writers can spend their time on the other three quadrants where they have leverage.**

### What Aura already covers

The eight artifact categories Aura produces map cleanly onto Diátaxis's reference quadrant and onto specific tiers of the inventory above:

- `Endpoint` corresponds to API reference (Tier 2).
- `DataModel` corresponds to data model documentation and ERD (Tier 4).
- `Function` and `Module` correspond to code reference (Tier 2).
- `Service` corresponds to C4 Container/Component view (Tier 4).
- `Flow` corresponds to runtime view sequence diagrams (Tier 4).
- `EnvVar` corresponds to configuration reference (Tier 2).
- `Config` corresponds to deployment topology reference (Tier 4).

The architecture Mermaid (T12 output) corresponds to a C4 Level 2/3 diagram. The PR drift comment (T17 output) corresponds to a *change-by-change reference*, which is roughly an automated changelog at the level of individual PRs.

### Gaps Aura could fill (post-MVP)

These are categories Aura *could* extend into without changing its fundamental nature.

**Auto-generated changelog from drift history.** Once Aura has analyzed dozens of PRs against a repo, the drift reports are the raw material for a high-quality changelog. The format is a near-perfect match for Keep a Changelog conventions.

**ADR stubs from CRITICAL drift events.** When a CRITICAL drift is detected, Aura could prompt the PR author to fill in an ADR. The ADR template would be pre-filled with the *Context* section auto-generated from the drift.

**Glossary from data model field names.** Recurring identifiers across data models ("organization," "workspace," "tenant") are candidates for glossary entries. Synthesis can detect these and propose definitions.

**Quickstart synthesis.** From the README's first heading, the entry-point endpoint, and the first test in the test suite, Aura could synthesize a five-line copy-pasteable quickstart and flag if the repo lacks one.

**Operational runbook stubs.** From the env-var list, the config files, and the error response patterns in the API, Aura can generate the *skeleton* of a runbook ("if `STRIPE_API_KEY` is unset, expect 503 from `/billing/charge`"). A human owner fills in the response procedure.

**Threat model surface mapping.** From the endpoint list, the auth requirements, and the env-var secret heuristic, Aura can list the externally-reachable surface and the secrets it depends on. This is the input to a threat model, not the model itself.

**Coverage gap report.** A meta-artifact: of the documentation surfaces standard for a project of this kind, which ones are missing? "This repo has no SECURITY.md, no CHANGELOG, and the README has no quickstart section." A directly actionable readout.

### What Aura should not try to replace

These categories belong to humans and will reliably look bad if automated.

**Tutorials.** Pedagogy is a human craft. The *order* in which a tutorial introduces concepts, the *pace* of difficulty increase, the *small encouragements* between sections — these are what makes a tutorial work. An LLM-generated tutorial is competent and forgettable.

**Strategic and "why" content.** Why this product exists, who it's for, what problem it really solves at the level of a market or a customer's lived experience. An LLM cannot know this from the code.

**The *responsibility* sentence on a Service.** Aura does generate this (in T12), but it's a synthesis based on what the code does, not what the team intends the service to do. The two often diverge — the team has a plan that the code hasn't caught up to yet. Aura's responsibility sentence should be *editable* by humans, with the human version winning on conflict.

**Marketing pages and landing pages.** The first impression of a product. Voice, brand, and positioning belong to humans.

**Code of Conduct, Contributing Guidelines.** These need the project's own voice and the team's own commitments. A generic template here is worse than nothing.

**Migration guides between major versions.** Aura can detect what changed; framing it as a migration narrative ("here's what you need to do, in what order, with what gotchas") is a writing task that needs editorial judgment.

### A recommended gradient

Think of Aura's value as *high-confidence, lower-frequency-of-update* material on the left, and *low-confidence, high-touch* material on the right:

On the **left** (Aura is excellent): API reference, data model reference, dependency graphs, env var lists, configuration reference, drift detection, change-by-change PR analysis. These are mechanical, high-volume, and miserable to maintain by hand. Aura is exceptional here.

In the **middle** (Aura assists, humans approve): service responsibilities, flow descriptions, glossary candidates, ADR stubs, runbook skeletons, coverage gap reports. Aura proposes; humans accept, edit, or reject.

On the **right** (humans own, Aura supports): tutorials, strategic positioning, voice and tone, branding, contributing guidelines, code of conduct, migration narratives, threat models. Aura's role here is to *surface the inputs* (what changed, what depends on what) so humans can write better; not to replace the writing.

The MVP is firmly on the left. Post-MVP work points to the middle. The right is forever a frontier and should be approached with humility.

---

## Part 7 — Recommended Reading

Curated rather than comprehensive. If you want to deepen on documentation practice, here are the highest-leverage starting points.

**Books**

- *Docs for Developers* by Jared Bhatti, Zachary Sarah Corleissen, Jen Lambourne, David Nunez, Heidi Waterhouse (Apress, 2021). The single best book on technical writing for engineers. Practical, opinionated, current.
- *Every Page Is Page One* by Mark Baker (XML Press, 2013). Pre-Diátaxis but anticipated many of its ideas. The phrase itself ("every page is page one") is a permanent corrective to the assumption that readers arrive at chapter one.
- *Modern Technical Writing* by Andrew Etter (self-published, 2016). Short, free online (https://github.com/aetter/modern-technical-writing). The case for docs-as-code, distilled.
- *The Product is Docs* by Christopher Gales and the Splunk Documentation team (2020). For SaaS-product documentation specifically.
- *Site Reliability Engineering* and *The Site Reliability Workbook* by Google (free at sre.google). Chapters on documentation, postmortems, and runbooks are required reading for operational docs.
- *Designing the Obvious* and *Don't Make Me Think* (Steve Krug) — about UX, but transferable to docs IA.

**Essays and talks**

- "Documenting Architecture Decisions" — Michael Nygard (2011). The original ADR post. https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- "What nobody tells you about documentation" — Daniele Procida (2017). The talk that introduced Diátaxis. https://www.youtube.com/watch?v=t4vKPhjcMZg
- "Docs as Code" — Andrew Etter. The principles in essay form.
- "The C4 model for visualising software architecture" — Simon Brown. https://c4model.com — the site is itself the canonical reference.
- The Write the Docs conference archives at https://www.writethedocs.org/conf/ — many of the talks are excellent and freely available.

**Communities**

- Write the Docs at https://www.writethedocs.org. Slack, conferences, mailing list. The most active docs-practitioner community.
- The CNCF TAG-Contributor-Strategy docs working group, for those interested in OSS documentation practice at scale.

**Style guides referenced in this document**

- Google Developer Documentation Style Guide — https://developers.google.com/style
- Microsoft Writing Style Guide — https://learn.microsoft.com/en-us/style-guide/welcome/
- Apple Style Guide — https://support.apple.com/guide/applestyleguide/welcome/web
- Mailchimp Content Style Guide — https://styleguide.mailchimp.com
- Conscious Style Guide — https://consciousstyleguide.com

**Frameworks referenced in this document**

- Diátaxis — https://diataxis.fr
- C4 Model — https://c4model.com
- arc42 — https://arc42.org
- ADR / MADR — https://adr.github.io
- Keep a Changelog — https://keepachangelog.com
- Semantic Versioning — https://semver.org
- Contributor Covenant — https://www.contributor-covenant.org
- llms.txt — https://llmstxt.org
- OpenAPI — https://spec.openapis.org

---

*This document is itself an exercise in the practice it advocates. It is a piece of explanation-quadrant documentation: discursive, opinionated, motivated by reasoning rather than reference. If you find yourself reaching for it as reference, that's a signal it should be split — and the split version should live in Aura's own docs, written by a human, with examples drawn from the codebase Aura built.*
