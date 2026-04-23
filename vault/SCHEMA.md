# Wiki Schema

## Domain
Large Language Models, AI systems, research notes, tools, people, organizations, and implementation knowledge.

## Purpose
This vault is a compounding external memory layer for Hermes.
It is optimized for:
- long-lived knowledge accumulation
- human readability in Obsidian
- machine operability through plain Markdown files
- Git-friendly diffs and backups

## Conventions
- File names: lowercase, hyphens, no spaces
- Every wiki page starts with YAML frontmatter
- Use `[[wikilinks]]` between related notes
- When updating a page, bump `updated`
- Every new page must be added to `index.md`
- Every meaningful change must be appended to `log.md`
- `raw/` is immutable source storage; do not edit captured sources after ingest
- Keep pages concise; split pages above ~200 lines

## Frontmatter
```yaml
---
title: Page Title
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: entity | concept | comparison | query | summary
tags: [from taxonomy]
sources: [raw/articles/example.md]
---
```

## Tag Taxonomy
- model
- architecture
- training
- inference
- alignment
- evaluation
- benchmark
- dataset
- tooling
- agent
- person
- company
- lab
- product
- paper
- blog
- implementation
- systems
- memory
- retrieval
- comparison
- timeline
- glossary

Rule: if a new tag is needed, add it here before using it.

## Page Thresholds
- Create a page when a concept/entity is central to a source or recurs across sources
- Update an existing page if the topic already exists
- Do not create pages for incidental mentions

## Folder Rules
- `entities/`: people, labs, companies, models, products
- `concepts/`: technical ideas and themes
- `comparisons/`: side-by-side analyses
- `queries/`: high-value answers worth preserving
- `_meta/`: templates, operational docs, maps

## Query Policy
When Hermes answers a substantial question from this vault, preserve the answer in `queries/` if it would be expensive to reconstruct.

## Filing Threshold For Answers

- 기본 원칙: 모든 대화를 저장하지 않는다.
- 아래 조건 중 하나 이상에 해당하면 답변을 wiki에 승격할 수 있다.
  - 여러 페이지나 여러 source를 합쳐야만 나오는 답변
  - 비교표, 장단점 정리, 의사결정 근거처럼 재사용 가치가 큰 답변
  - 이후 다시 같은 질문이 나올 가능성이 높은 운영 지식
  - 기존 concept/entity/comparison 페이지를 실질적으로 갱신할 정도의 새 정리
  - 사용자가 명시적으로 "위키에 반영", "파일링", "기록"을 요청한 경우

- 아래에 해당하면 보통 wiki에 승격하지 않는다.
  - 단순 단답
  - 일회성 잡담
  - 이미 index와 기존 페이지만 읽으면 바로 복원 가능한 얕은 답변
  - 실행 과정의 임시 상태 보고

## Filing Destination Rule

- 개념이나 주제 설명이 강화되면 `concepts/`
- 사람, 조직, 제품, 모델 정보가 강화되면 `entities/`
- 둘 이상을 나란히 비교하면 `comparisons/`
- 질문에 대한 고가치 결과물 자체를 보존하려면 `queries/`

기존 페이지가 있으면 새 페이지 생성보다 갱신을 우선한다.

## Query Workflow Rule

질문을 받았을 때는 아래 순서를 따른다.

1. `SCHEMA.md`
2. `index.md`
3. 최근 `log.md`
4. 관련 wiki 페이지
5. 구조 관계나 cross-note 연결이 중요하면 Graphify 질의 계층
6. 필요할 때만 `raw/`

Graphify 질의 계층의 현재 canonical 경로:

- manifest: `%HERMES_ROUTER_ROOT%\projects\graphify-poc\graphify-corpus.manifest.json`
- query wrapper: `%HERMES_ROUTER_ROOT%\projects\graphify-poc\query_graphify.py`
- sandbox root: `%GRAPHIFY_SANDBOX_ROOT%`

현재 canonical stack에는 활성 embedding/vector fallback이 없다.
즉 query workflow에서 임베딩 검색 계층은 사용하지 않는다.

답변 후 filing 조건을 만족하면:

1. 적절한 위치에 문서를 생성하거나 기존 문서를 갱신한다.
2. `index.md`를 갱신한다.
3. `log.md`에 query 또는 update 항목을 추가한다.
