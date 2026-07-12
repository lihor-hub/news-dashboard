# Learning Agent Roadmap

The Learning Agent turns a source article into one durable lesson artifact, then
derives study, media, graph, and recommendation features from that artifact. The
roadmap is lesson-first: later features should not re-read the original article
when the canonical lesson already contains the user-visible learning material
and provenance needed for generation.

## Product Contract

- A lesson is the canonical structured artifact for one article or pasted link.
- Generated write actions stay explicit and reviewable: the user chooses when to
  create, save, publish, export, or schedule follow-up artifacts.
- Expensive generation is opt-in per artifact until the app has durable state,
  idempotency, retry visibility, and cost controls for that artifact type.
- PostgreSQL remains the source of truth for lessons, runs, user ownership,
  feedback, eval examples, and artifact metadata.
- Optional graph storage may enrich discovery and Ask AI context, but the
  lesson feature must degrade to PostgreSQL-backed retrieval when graph storage
  is unavailable.

## Structured Lesson Object

The first implementation slice should create a durable lesson object with a
stable schema stored in PostgreSQL. Store the generated payload as `jsonb` while
the shape stabilizes, with relational columns for identity, ownership, status,
model, trace ID, timestamps, source article/link provenance, and error state.

Minimum lesson content:

- title and short summary
- source article or pasted-link provenance
- key ideas with cited spans or source references
- prerequisite concepts
- takeaways
- follow-up questions
- suggested practice prompts
- extracted concepts and relationships ready for graph expansion

The lesson object is the input contract for every child slice below.

## Child Implementation Slices

| Slice | Issue | Depends on | Output |
|-------|-------|------------|--------|
| Extract lesson concepts and relationships into the knowledge graph | [#1123](https://github.com/lihor-hub/news-dashboard/issues/1123) | Structured lesson object | Concept and relationship candidates written to PostgreSQL and, when configured, Neo4j. |
| Show an interactive lesson concept graph | [#1124](https://github.com/lihor-hub/news-dashboard/issues/1124) | Lesson concepts | A lesson-scoped graph view that uses PostgreSQL fallback data when Neo4j is disabled. |
| Recommend learning trails from a lesson | [#1125](https://github.com/lihor-hub/news-dashboard/issues/1125) | Lesson concepts and feedback | Ordered follow-up lessons or articles grounded in saved lessons and user interests. |
| Generate infographic artifacts from a lesson | [#1128](https://github.com/lihor-hub/news-dashboard/issues/1128) | Structured lesson object | Reviewable visual artifacts generated from lesson sections and cited concepts. |

Future slices should be added to this table when they have AFK-ready issues.
Good candidates include audio lessons, slide decks, spaced-repetition cards,
and proactive notifications.

## Integration Points

The implementation should follow existing News Dashboard patterns instead of
adding a separate agent stack.

- AI calls use the same OpenAI-compatible gateway resolution and Langfuse prompt
  fallback pattern as briefings and Ask AI.
- Lesson generation records Langfuse traces with stable names, tags, inputs,
  outputs, and model metadata.
- User feedback records through the generic AI feedback path and seeds eval
  examples for lesson quality.
- Deterministic eval fixtures check structure, citation validity, and grounded
  output properties before richer media generation ships.
- Ask AI can retrieve lessons as a scoped corpus once lessons have stable
  ownership, citations, and embedding coverage.
- Knowledge graph expansion writes lesson-derived concepts through the existing
  PostgreSQL-first graph flow, then mirrors to Neo4j when configured.
- Scheduler work is limited to explicit user-enabled jobs, such as generating a
  requested artifact after a lesson exists.

## Review And Cost Guardrails

Generated writes and expensive artifacts must be visible as state transitions,
not hidden side effects.

- Every generation request creates or reuses an idempotent run record.
- Failed runs persist error state that can be shown in the UI and inspected in
  operations logs.
- The UI separates draft generation from user-approved save, export, publish,
  or notification actions.
- Bulk generation requires an explicit selected scope and a confirmation step.
- Background jobs skip users without the required AI configuration and record a
  skipped state instead of retrying indefinitely.

## Delivery Order

1. Ship the structured lesson object and lesson generation run tracking.
2. Add lesson feedback and deterministic eval coverage.
3. Write lesson concepts and relationships through the PostgreSQL-first graph
   path, with optional Neo4j mirroring.
4. Add the lesson concept graph UI.
5. Add learning trail recommendations.
6. Add media artifacts such as infographics, audio, and slides after the lesson
   schema and eval gates are stable.
