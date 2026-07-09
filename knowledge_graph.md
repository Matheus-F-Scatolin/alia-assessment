# Knowledge Graph — Company:Alia

Company-scoped graph. Every entity is unique per `{Label}:{Name}` within this company.
Nodes with an empty `valid_to` are **active**. Anything with a `valid_to` date has been
superseded or ended.

Refs elsewhere in this repo (`bronze/*.json`, `medallion.json`) use the form
`Label:Name` exactly as written below — case-sensitive.

---

## Nodes

### Person

#### Person:Thomas Filshill
- role: CEO / Founder
- description: Drives product, commercial, and advisor relationships. Owns the CEO-verbose Gold mode requirements and all external design-partner negotiations.
- valid_from: 2024-01-01
- valid_to:

#### Person:Bernardo Aires
- role: Engineer — Agents & Gold
- description: Owns the agent runtime and the Gold synthesis layer. Most active contributor to the medallion pipeline.
- valid_from: 2024-04-10
- valid_to:

#### Person:Lucas Quaresma
- role: Engineer — Core (moving)
- description: Joined LinkedIn outreach and Alia Meetings; migrating to core work this week with co-ownership of entity layer.
- valid_from: 2024-09-22
- valid_to:

#### Person:Henrique Silva
- role: Engineer — Entity Layer (leaving)
- description: Built the entity layer and most recent goals/OKRs extension. Leaving for a startup that acquired the CCC concept.
- valid_from: 2025-01-06
- valid_to: 2026-04-24

#### Person:Livia Kuga
- role: Operations
- description: Runs operational rhythm; co-lead on design-partner onboarding with Thomas.
- valid_from: 2024-06-03
- valid_to:

#### Person:Mati Veloso
- role: Advisor
- description: Product/design advisor. Weighing in on dashboard surfaces and evidence representation.
- valid_from: 2025-11-01
- valid_to:

#### Person:Veronica Serra
- role: Advisor
- description: Enterprise GTM advisor, pushing on design-partner pricing and positioning.
- valid_from: 2025-12-15
- valid_to:

#### Person:Lidia Mesquita
- role: Advisor
- description: UX / information-architecture advisor, reviewing ontology + alignment panel shape.
- valid_from: 2026-01-20
- valid_to:

#### Person:André Castro
- role: External Tester (Design Partner Seed)
- description: Running 4–8 Meet calls/day to validate Alia Meetings transcription.
- valid_from: 2026-03-10
- valid_to:

#### Person:João Bogado
- role: NGCash — Product Lead
- description: Primary counterparty on the NGCash design-partner negotiation. Opened at $5k/mo.
- valid_from: 2026-04-17
- valid_to:

#### Person:Anderson Queiroz
- role: VTEX — Partnerships
- description: Driving the VTEX tooling pilot; defining which internal datasets are cleared for the pilot.
- valid_from: 2026-04-10
- valid_to:

#### Person:Ariane Gomes-Santos
- role: Itaú — Innovation
- description: Champion inside Itaú for the Alia pilot; relationship carried over from ProSieve era.
- valid_from: 2025-09-11
- valid_to:

### Project

#### Project:Entity Layer
- description: Medallion-wide entity schema (people, projects, goals, objectives). PR 312 added goals + OKRs.
- valid_from: 2025-01-06
- valid_to:

#### Project:Agent Runtime
- description: The LLM agents that consume entity outputs — routing, silver generation, gold synthesis tools.
- valid_from: 2025-03-01
- valid_to:

#### Project:Gold Synthesis
- description: Narrative layer over silver. Ships today with verbose (CEO Q&A) and systematic (dashboard JSON) modes.
- valid_from: 2025-11-08
- valid_to:

#### Project:Silver Layer
- description: Structured interpretations derived from bronze. Person/project insights, deterministic workflow.
- valid_from: 2025-07-15
- valid_to:

#### Project:Alia Meetings
- description: Google Meet bot that joins calls, transcribes, feeds bronze. In pilot, 4–8 calls/day.
- valid_from: 2026-02-20
- valid_to:

#### Project:LinkedIn Outreach
- description: In-house outreach + sequencing tool built by Lucas. Replaced Lambdlist and AppFly ($600–700/mo saved).
- valid_from: 2025-12-01
- valid_to:

#### Project:NGCash Partnership
- description: Design-partner negotiation. $5k opener, pulling to $6–6.5k.
- valid_from: 2026-04-17
- valid_to:

#### Project:VTEX Partnership
- description: Tooling pilot for VTEX COO. Scope in definition, waiting on dataset whitelist.
- valid_from: 2026-04-10
- valid_to:

#### Project:Itaú Relationship
- description: Long-standing pilot conversation carried from ProSieve. Lower tempo, high relational value.
- valid_from: 2025-09-11
- valid_to:

#### Project:Knowledge Graph Production
- description: Migrating KG generation from Henrique's prototype into Bernardo/Lucas ownership, stabilizing neo4j writes.
- valid_from: 2026-04-19
- valid_to:

### Goal

#### Goal:Ship Gold to Pilots — Q2
- description: Gold layer in production for functional and core business at 3+ pilot companies by end of Q2.
- valid_from: 2026-04-01
- valid_to:

#### Goal:Three Paid Design Partners by June
- description: Convert NGCash, VTEX, and one more (Itaú leading candidate) into paid design partners before June.
- valid_from: 2026-03-15
- valid_to:

#### Goal:Stabilize Medallion Ownership Post-Henrique
- description: No person is a single point of failure for entity layer, silver, or gold by end of April.
- valid_from: 2026-04-17
- valid_to:

#### Goal:Meetings at Production Scale
- description: Alia Meetings sustaining 20+ transcribed meetings/day across pilots by end of May.
- valid_from: 2026-03-10
- valid_to:

### Objective

#### Objective:Gold Live for Functional & Core — 2026-04-21
- description: Functional + core users of pilot companies can use Gold verbose and systematic modes today.
- valid_from: 2026-04-17
- valid_to:

#### Objective:Close NGCash at $6k+
- description: Sign NGCash as design partner at minimum $6k/mo before end of week.
- valid_from: 2026-04-19
- valid_to:

#### Objective:Entity Layer Handoff Before 2026-04-24
- description: Henrique documents goals/OKRs contract; Bernardo and Lucas take co-ownership before departure.
- valid_from: 2026-04-19
- valid_to:

#### Objective:VTEX Pilot Dataset Scope Locked
- description: Agree with Anderson on which VTEX datasets are in-scope for the first Gold pilot view.
- valid_from: 2026-04-20
- valid_to:

#### Objective:Evidence-from-Entities Dashboard Spec
- description: Resolve with advisors how entity-sourced evidence renders in the alignment panel.
- valid_from: 2026-04-20
- valid_to:

---

## Edges

### Ownership & membership

- (Person:Thomas Filshill) -[member_of]-> (Project:Gold Synthesis:Project)
  details: Product owner; defines verbose-mode requirements and CEO-facing Q&A surface.
  valid_from: 2025-11-08

- (Person:Bernardo Aires) -[member_of]-> (Project:Gold Synthesis:Project)
  details: Engineering lead on gold synthesis and the narrator/tool wiring.
  valid_from: 2025-11-08

- (Person:Bernardo Aires) -[member_of]-> (Project:Agent Runtime:Project)
  details: Owns agent routing, silver workflows, and the toolsets Gold depends on.
  valid_from: 2025-03-01

- (Person:Henrique Silva) -[member_of]-> (Project:Entity Layer:Project)
  details: Sole owner until handoff. PR 312 introduced Goal + Objective nodes.
  valid_from: 2025-01-06
  valid_to: 2026-04-24

- (Person:Lucas Quaresma) -[member_of]-> (Project:Entity Layer:Project)
  details: Joining co-ownership post-Henrique handoff.
  valid_from: 2026-04-19

- (Person:Bernardo Aires) -[member_of]-> (Project:Entity Layer:Project)
  details: Joining co-ownership post-Henrique handoff; first consumer of the goals/OKRs extension.
  valid_from: 2026-04-19

- (Person:Lucas Quaresma) -[member_of]-> (Project:Alia Meetings:Project)
  details: Built the Meet bot; primary maintainer.
  valid_from: 2026-02-20

- (Person:Lucas Quaresma) -[member_of]-> (Project:LinkedIn Outreach:Project)
  details: Sole author of the in-house outreach tool.
  valid_from: 2025-12-01

- (Person:Thomas Filshill) -[member_of]-> (Project:NGCash Partnership:Project)
  details: Leading negotiation.
  valid_from: 2026-04-17

- (Person:Livia Kuga) -[member_of]-> (Project:NGCash Partnership:Project)
  details: Operational onboarding once signed.
  valid_from: 2026-04-17

- (Person:Thomas Filshill) -[member_of]-> (Project:VTEX Partnership:Project)
  details: Lead counterpart to Anderson.
  valid_from: 2026-04-10

- (Person:Thomas Filshill) -[member_of]-> (Project:Itaú Relationship:Project)
  details: Primary contact with Ariane; warming pilot conversation.
  valid_from: 2025-09-11

- (Person:Bernardo Aires) -[member_of]-> (Project:Knowledge Graph Production:Project)
  details: Owning neo4j write stabilization post-Henrique.
  valid_from: 2026-04-19

- (Person:Lucas Quaresma) -[member_of]-> (Project:Knowledge Graph Production:Project)
  details: Co-owner as part of entity-layer handoff.
  valid_from: 2026-04-19

### External participants

- (Person:João Bogado) -[collaborates_with]-> (Person:Thomas Filshill)
  details: NGCash counterparty in design-partner negotiation.
  valid_from: 2026-04-17

- (Person:Anderson Queiroz) -[collaborates_with]-> (Person:Thomas Filshill)
  details: VTEX pilot scoping conversations.
  valid_from: 2026-04-10

- (Person:André Castro) -[collaborates_with]-> (Person:Lucas Quaresma)
  details: Testing Alia Meetings daily; primary source of Meet-integration bugs.
  valid_from: 2026-03-10

- (Person:Ariane Gomes-Santos) -[collaborates_with]-> (Person:Thomas Filshill)
  details: Itaú champion; intro-brokering to internal leaders.
  valid_from: 2025-09-11

### Peer collaboration

- (Person:Bernardo Aires) -[collaborates_with]-> (Person:Lucas Quaresma)
  details: Joint work on gold synthesis; emerging co-ownership of entity layer post-Henrique.
  valid_from: 2026-04-19

- (Person:Bernardo Aires) -[collaborates_with]-> (Person:Henrique Silva)
  details: Downstream consumer; blocked by PR 312 until handoff.
  valid_from: 2025-03-01

- (Person:Lucas Quaresma) -[collaborates_with]-> (Person:Henrique Silva)
  details: Taking over entity layer; pending handoff sync.
  valid_from: 2026-04-19

- (Person:Thomas Filshill) -[collaborates_with]-> (Person:Livia Kuga)
  details: Operational partnership; joint ownership of design-partner onboarding.
  valid_from: 2024-06-03

- (Person:Thomas Filshill) -[collaborates_with]-> (Person:Mati Veloso)
  details: Weekly advisor sync on product shape.
  valid_from: 2025-11-01

- (Person:Thomas Filshill) -[collaborates_with]-> (Person:Veronica Serra)
  details: Pricing + GTM reviews before commercial calls.
  valid_from: 2025-12-15

- (Person:Thomas Filshill) -[collaborates_with]-> (Person:Lidia Mesquita)
  details: UX sessions on ontology + alignment surfaces.
  valid_from: 2026-01-20

### Project → Goal / Objective

- (Project:Gold Synthesis:Project) -[RELATES_TO]-> (Goal:Ship Gold to Pilots — Q2:Goal)
  details: Gold synthesis is the core deliverable tracked by this goal.
  valid_from: 2026-04-01

- (Project:Gold Synthesis:Project) -[RELATES_TO]-> (Objective:Gold Live for Functional & Core — 2026-04-21:Objective)
  details: Today's ship moment.
  valid_from: 2026-04-17

- (Project:Entity Layer:Project) -[RELATES_TO]-> (Goal:Stabilize Medallion Ownership Post-Henrique:Goal)
  details: Entity layer is the single largest ownership risk.
  valid_from: 2026-04-17

- (Project:Entity Layer:Project) -[RELATES_TO]-> (Objective:Entity Layer Handoff Before 2026-04-24:Objective)
  details: Concrete deadline driven by Henrique's exit.
  valid_from: 2026-04-19

- (Project:NGCash Partnership:Project) -[RELATES_TO]-> (Goal:Three Paid Design Partners by June:Goal)
  details: First of the three named design partners.
  valid_from: 2026-03-15

- (Project:NGCash Partnership:Project) -[RELATES_TO]-> (Objective:Close NGCash at $6k+:Objective)
  details: This week's commercial target.
  valid_from: 2026-04-19

- (Project:VTEX Partnership:Project) -[RELATES_TO]-> (Goal:Three Paid Design Partners by June:Goal)
  details: Second of the three named design partners.
  valid_from: 2026-03-15

- (Project:VTEX Partnership:Project) -[RELATES_TO]-> (Objective:VTEX Pilot Dataset Scope Locked:Objective)
  details: Scoping dependency before pilot can start.
  valid_from: 2026-04-20

- (Project:Alia Meetings:Project) -[RELATES_TO]-> (Goal:Meetings at Production Scale:Goal)
  details: Production-scale Meet transcription is the scale goal.
  valid_from: 2026-03-10

- (Project:Gold Synthesis:Project) -[RELATES_TO]-> (Objective:Evidence-from-Entities Dashboard Spec:Objective)
  details: Dashboard blocker: entity-source evidence rendering.
  valid_from: 2026-04-20

### Project → Project (structural)

- (Project:Gold Synthesis:Project) -[RELATES_TO]-> (Project:Silver Layer:Project)
  details: Gold consumes silver as its primary input.
  valid_from: 2025-11-08

- (Project:Gold Synthesis:Project) -[RELATES_TO]-> (Project:Entity Layer:Project)
  details: Gold resolves participants and projects through the entity layer.
  valid_from: 2025-11-08

- (Project:Agent Runtime:Project) -[RELATES_TO]-> (Project:Entity Layer:Project)
  details: Agents deserialize entity payloads; broken by PR 312's unmapped fields.
  valid_from: 2025-03-01

- (Project:Knowledge Graph Production:Project) -[RELATES_TO]-> (Project:Entity Layer:Project)
  details: KG write pipeline depends on entity layer schema.
  valid_from: 2026-04-19

