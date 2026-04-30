<p align="center">
  <h1 align="center">🌳 OpenYggdrasil</h1>
  <p align="center">
    <strong>프로바이더 중립적 AI 코딩 에이전트 메모리 엔진</strong>
  </p>
  <p align="center">
    <em>또 다른 RAG 래퍼가 아닙니다. 프로바이더 간 축적되는<br/>
    영속적이고 생명주기 인식 가능한 지식 계층 —
    <a href="https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f">Karpathy의 LLM Wiki</a>에서 영감을 받았습니다.</em>
  </p>
  <p align="center">
    <a href="./README.md">English</a> · 한국어
  </p>
</p>

<p align="center">
  <a href="#왜-필요한가">왜 필요한가</a> •
  <a href="#작동-방식">작동 방식</a> •
  <a href="#12-모듈-체인">모듈</a> •
  <a href="#reasoning-lease">Reasoning Lease</a> •
  <a href="#프로바이더-연동--설정">설정</a> •
  <a href="#영감--감사">영감</a>
</p>

> **⚠️ 이 프로젝트는 현재 라이브 테스팅 중입니다.**
> 아키텍처 설계와 계약 정의는 완료되었으나, 엔드투엔드 파이프라인은 아직 프로덕션
> 준비가 되지 않았습니다. 브레이킹 체인지, 불완전한 통합, 거친 부분이 있을 수
> 있습니다. 공개적으로 개발 중이며, 기여와 피드백을 환영합니다.

---

## 왜 필요한가

모든 AI 코딩 도구 — Hermes, Codex, Claude Code, Cursor, Gemini CLI — 는 각자의
방식으로 "기억"합니다. 공통된 결과:

| 문제 | 현상 |
|---|---|
| **흩어진 의사결정** | 유용한 맥락이 프로바이더 채팅, 마크다운 노트, 로컬 파일에 갇힘 |
| **낡은 기억** | 이미 대체된 결정이 계속 검색 가능한 상태로 남음 |
| **프로바이더 종속** | 각 도구가 서로 다른 메모리 형식을 발명 |
| **트랜스크립트 덤프** | 가공되지 않은 세션이 "메모리"로 레포에 유입 |
| **출처 없음** | 검색 결과가 그럴듯하지만 출처, 신선도, 생명주기 상태를 증명 불가 |

**RAG는 이걸 해결하지 못합니다.** RAG는 매 질의마다 지식을 처음부터 재파생합니다.
축적도, 생명주기도, 프로바이더 간 공유도 없습니다.

**벡터 데이터베이스도 마찬가지입니다.** 인프라 의존성(Neo4j, Pinecone, 임베딩)을
추가할 뿐, 근본 문제를 해결하지 않습니다: *무엇을 기억하고, 무엇을 잊고, 무엇을
전달할지 누가 결정하는가?*

OpenYggdrasil은 다른 접근을 취합니다.

### 프로바이더 간 지식 교차 (Cross-Provider Pollination)

OpenYggdrasil의 가장 강력한 특징은 특정 도구에 종속되지 않는 **"공용 뇌(Shared Brain)"** 라는 점입니다.

- **Hermes가 씁니다:** Hermes 세션에서 아키텍처를 결정하고 Vault에 기록합니다. (출처: `provider_id: hermes`)
- **Claude Code가 읽고 갱신합니다:** 며칠 뒤 Claude Code가 켜지면, Hermes가 쓴 문서를 검색해서 읽고 그 위에서 작업을 이어갑니다. 만약 결정이 변경되면 Claude가 기존 지식을 `SUPERSEDED`(대체됨)로 밀어내고 새 지식을 씁니다.
- **다시 Hermes가 인지합니다:** 다음에 Hermes가 들어오면, 자신이 과거에 썼던 낡은 지식이 아니라 Claude Code가 최신화해 둔 지식을 읽게 됩니다.

이것이 가능한 이유는 모든 에이전트가 자신만의 내부 트랜스크립트 포맷을 버리고, OpenYggdrasil의 **엄격한 프론트매터 스키마(Markdown + YAML)** 라는 단일 진실 원천(Vault) 규격을 공유하기 때문입니다.

## 실행 모델

OpenYggdrasil은 자체 LLM이나 API 키를 갖고 있지 않습니다.
프로바이더(Hermes, Claude Code, Cursor 등)가 이 레포지토리에 진입하면
루트의 **`SKILL.md`** 를 읽고, 거기에 정의된 진입점을 자기 토큰으로 실행합니다.

```
  프로바이더 에이전트
       │
       │  레포 진입 → SKILL.md 발견
       │
       ▼
  ┌──────────────────────────────────────────────────┐
  │  SKILL.md (계약서)                                │
  │                                                  │
  │  "캡처할 때는 이 Python 스크립트를 실행하세요"       │
  │  "검색할 때는 이 진입점을 호출하세요"                │
  │  "입력 형태는 이렇고, 출력 형태는 이렇습니다"        │
  └──────────────────────────────────────────────────┘
       │
       ▼
  에이전트가 자기 쉘/도구호출로 Python 진입점 실행
  → PTC 엔진이 도구 세트와 실행 계획(Tool Plan) 제시
  → 에이전트가 도구를 순서대로 호출하여 파이프라인 관통
```

이 구조에서 빌려 쓰는 것은 두 가지입니다:

| 빌려 쓰는 것 | 설명 |
|---|---|
| **실행 컨텍스트** | 에이전트의 쉘/도구호출 능력으로 Python 스크립트 실행 |
| **추론 토큰** | PTC 계약 가드레일 통과 및 복잡한 판단에 필요한 LLM 추론 능력 |

**서브에이전트가 곧 파이프라인입니다.** 파이프라인 모듈 중 일부(작업 도구)는
순수 Python으로 결정론적 실행되지만, 핵심 판단(계약 가드레일)은 에이전트의
추론 토큰을 소비하여 동작합니다.

향후 독립적인 API 키 지정을 통해 프로바이더 없이 자체 실행하는 모드도
지원할 계획입니다.

---

## PTC (Programmatic Tool Calling) 개념과 아키텍처

OpenYggdrasil의 생산 및 소비 파이프라인은 **PTC (Programmatic Tool Calling)** 아키텍처를 기반으로 동작합니다. 

**원천 SOT (Source of Truth):**
이 아키텍처는 Anthropic의 [Claude Code Tool Use / MCP (Model Context Protocol)](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use) 및 CLI REPL 생태계의 철학을 모티브로 삼고 있습니다.

### 원본 아키텍처 (Claude Code 스타일)
일반적인 에이전트 도구 호출 방식은 자유도가 매우 높습니다:
1. 에이전트가 자유롭게 Bash 명령어나 임의의 Python 스크립트를 작성하여 시스템을 제어합니다.
2. 결과를 관찰하고 다시 코드를 수정하여 실행하는 **개방형 자율 루프(Open-ended REPL)** 방식입니다.
3. 이 방식은 유연하지만, 지식을 정규화하고 엄격한 생명주기를 가진 메모리로 저장하기에는 예측 가능성이 떨어지며 런타임 환각에 취약합니다.

### OpenYggdrasil의 변형 및 내재화 (Typed PTC Engine)
OpenYggdrasil은 이 원본 아키텍처의 자율성을 의도적으로 제한하고, **타입 안정성이 보장된 체인(Typed Chain)** 으로 내재화했습니다.

1. **블랙박스 해체:** 내부 12-모듈이 보이지 않게 자동으로 도는 블랙박스 구조를 해체하고, 모든 모듈을 서브에이전트가 명시적으로 호출할 수 있는 "단일 목적 도구(Tool)"로 노출했습니다.
2. **자유도 제한 (JSON Tool Plan):** 에이전트가 마음대로 도구를 조합하거나 스크립트를 짜는 것을 막습니다. 대신, PTC 엔진이 상황에 맞는 **고정된 도구 순서(Execution Plan)** 를 JSON 형태로 에이전트에게 강제 주입합니다.
3. **이중 성격의 도구:** 도구를 '계약 가드레일'(추론 토큰 소비, 엄격한 스키마 검증)과 '작업 도구'(결정론적 Python 실행)로 분리하여 에이전트의 인지 부하를 최적화했습니다.

결과적으로, OpenYggdrasil의 PTC는 **"Claude Code의 강력한 에이전트 추론 능력"**을 빌려오면서도, **"엄격한 트랙 기반의 철도(Railway) 위에서만 달리도록 통제"**하여 데이터 무결성을 보장하는 고유한 구조를 완성했습니다.

---

## 작동 방식

OpenYggdrasil은 메모리를 **양면 엔진**으로 취급합니다 — 지식을 포착하고 큐레이션하는
**생산면(Production Side)** 과 지식을 검색하고 전달하는 **소비면(Consumption Side)**.

```
                    ┌─────────────────────────────────────────────┐
                    │           생산면 (PRODUCTION SIDE)            │
                    │                                             │
  프로바이더 신호 ──┤  ① Signal ─→ ② Gate ─→ ③ Seedkeeper        │
  (Hermes, Codex,   │       │                      │              │
   Claude Code,     │       ▼                      ▼              │
   Cursor, ...)     │  ④ Distiller ─→ ⑤ Evaluator                │
                    │                      │                      │
                    │                      ▼                      │
                    │  ⑥ Amundsen ─→ ⑦ Nursery ─→ ⑧ Map Maker   │
                    │                                    │        │
                    │                      ⑨ Gardener ◄──┘        │
                    └──────────────────────┬──────────────────────┘
                                           │
                                    ┌──────┴──────┐
                                    │    VAULT     │
                                    │  (정규 메모리) │
                                    └──────┬──────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │           소비면 (CONSUMPTION SIDE)           │
                    │                                             │
                    │  ⑫ Pathfinder ─→ 제한된 지원 번들            │
                    │       │                      │              │
                    │       ▼                      ▼              │
                    │  ⑩ Postman ─────────→ ⑪ Mailbox            │
                    │                          │                  │
                    │                          ▼                  │
                    │                   프로바이더 세션              │
                    └─────────────────────────────────────────────┘
```

### 생산면 — "무엇을 기억할 것인가"

생산 파이프라인은 모든 것을 맹목적으로 저장하지 않습니다. 프로바이더 신호를
타입이 지정된 의사결정 후보로 **증류(Distill)** 하고, 기억할 가치를
**평가(Evaluate)** 하며, 탐색 가능한 토픽 구조에 **배치(Place)** 하고,
생명주기 전환을 통해 낡은 지식을 **가지치기(Prune)** 합니다.

### 소비면 — "무엇을 전달할 것인가"

소비 파이프라인은 Vault 전체를 덤프하지 않습니다. **Pathfinder**가 설명
가능하고, 생명주기를 인식하며, 출처가 추적된 제한된 지원 번들을 구축하고,
**Postman**이 타입이 지정된 **Mailbox** 계약을 통해 전달합니다.

### 브릿지 — Vault와 Graphify의 관계

#### Vault: 정규 메모리 표면

Vault는 유일한 진실 원천(SOT)입니다. 프로바이더가 생산한 지식은
최종적으로 Vault에 기록되며, 다음 구조를 따릅니다:

```
vault/
├── SCHEMA.md           # 이 스키마 파일
├── index.md            # 전체 토픽 카탈로그 (Karpathy의 index.md)
├── log.md              # 연대기 기록 (Karpathy의 log.md)
├── concepts/           # 기술 아이디어, 패턴, 원칙, 반복 주제
├── entities/           # 사람, 조직, 제품, 모델, 시스템
├── comparisons/        # 나란히 분석, 의사결정 대면 비교
├── queries/            # 재파생 비용이 높은 고가치 답변
├── _meta/              # 운영 노트, 템플릿, 맵, 거버넌스
│   └── provenance/     # 출처 추적 기록
└── raw/                # 원본 지원 자료 (프로바이더 트랜스크립트 아님)
```

**각 페이지의 프론트매터:**

```yaml
---
title: 페이지 제목
created: 2026-04-30
updated: 2026-04-30
type: entity | concept | comparison | query | summary
tags: [분류 태그]
sources: [출처 참조 또는 공개 소스 경로]
---
```

**Vault 승격 규칙 — 기록되려면:**
- 영속적이고, 사소하지 않고, 재파생이 어렵고, 미래 세션에서 재사용 가능해야 함
- 일시적 대화, 사소한 응답, 원시 세션 덤프는 기록 금지

#### Graphify: 파생 가시성 계층

Vault 위에 그래프/위키/인덱스 뷰를 구축하는 **파생 계층**입니다.
**Graphify가 실패해도 핵심 파이프라인(캡처, 생명주기, Mailbox)은 영향받지 않습니다.**

**왜 Graphify를 채택했는가:**

| 문제 | Graphify의 해결 |
|---|---|
| Vault 페이지가 쌓이면 탐색 불가 | 노드/엣지 그래프로 관계 시각화 |
| "이 개념이 어디에 연결되지?" | Leiden 커뮤니티 클러스터링으로 토픽 군집 자동 탐지 |
| 검색 결과에 구조적 맥락 부재 | God Node, Surprising Connection 분석으로 핵심 허브 식별 |
| 외부 인프라(벡터 DB, 임베딩 서비스) 의존 | 순수 Python + NetworkX, 로컬 오프라인 실행 |

**Graphify 파생 파이프라인:**

```
  Vault (정규 메모리)
       │
       │  stage_graphify_input.py
       │  → Vault에서 승격된 페이지를 입력 코퍼스로 스테이징
       │
       ▼
  ┌─ Graphify 7-단계 파이프라인 ─────────────────────────────┐
  │                                                          │
  │  detect    → 코퍼스 파일 탐지                              │
  │  extract   → AST/구조 추출                                │
  │  semantic  → 의미 관계 추출 (프로바이더 토큰 사용)           │
  │  build     → NetworkX 그래프 구축                          │
  │  cluster   → Leiden 커뮤니티 클러스터링                     │
  │  analyze   → God Node, Surprising Connection 분석         │
  │  report    → GRAPH_REPORT.md + graph.json + graph.html    │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
       │
       ▼
  파생 산출물 (진실 원천 아님):
  ├── GRAPH_REPORT.md    # 분석 리포트
  ├── graph.json         # 기계 판독 가능 그래프
  ├── graph.html         # 시각적 탐색 인터페이스
  └── summary.json       # 노드/엣지/커뮤니티 요약
```

**핵심 경계:**

```
  ┌───────────────────────────────────────────────────────┐
  │  Vault (SOT)                                          │
  │  • 정규 메모리 — 유일한 진실 원천                        │
  │  • 생명주기 상태 (ACTIVE / SUPERSEDED / STALE)          │
  │  • 출처 추적 (source_ref, origin_locator)              │
  │  • 프론트매터 스키마 강제                                │
  └────────────────────┬──────────────────────────────────┘
                       │ 파생 (단방향)
                       ▼
  ┌───────────────────────────────────────────────────────┐
  │  Graphify (파생 뷰)                                    │
  │  • 그래프/위키/인덱스 — 가시성 계층                      │
  │  • 실패해도 코어 파이프라인 차단 안 함                    │
  │  • Pathfinder에 힌트 제공 (검증 필수)                   │
  │  • Vault를 수정하지 않음 (읽기 전용)                     │
  └───────────────────────────────────────────────────────┘
```

Graphify 산출물은 Pathfinder의 검색 품질을 향상시키지만,
**Pathfinder는 Graphify 힌트를 항상 Vault 원본과 교차 검증합니다.**
Graphify가 제안한 관계가 Vault에서 확인되지 않으면 무시됩니다.

---

## 운영 흐름 — 트리거에서 전달까지

위 다이어그램은 내부 체인을 보여주지만, 진짜 질문은:
**프로바이더가 이 시스템을 실제로 어떻게 호출하는가?**

두 가지 호출 경로가 있습니다 — 지식을 **기록**하는 경로(생산 트리거)와
지식을 **읽는** 경로(소비 트리거).

> **⚠️ 현재 추론 모델:**
> OpenYggdrasil은 현재 **프로바이더의 추론 토큰을 빌려서 사용**합니다.
> 별도의 API 키나 자체 LLM 인프라를 보유하지 않습니다.
> 향후 독립적인 API 키 지정을 통한 자체 추론 지원도 계획되어 있습니다.

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                    전체 생명주기 개요                                     │
  │                                                                        │
  │  ① 프로바이더가 SKILL.md를 읽음                                          │
  │  ② 프로바이더 에이전트가 판단: "캡처" 또는 "검색"                           │
  │                                                                        │
  │  캡처 경로 (생산)                         검색 경로 (소비)                 │
  │  ──────────────                         ──────────────                  │
  │  ③ 에이전트가 캡처 진입점 호출              ③ 에이전트가 검색 진입점 호출     │
  │     (구조화된 신호와 함께)                     (질의와 함께)                │
  │  ④ Signal → 12-모듈 체인                  ④ Pathfinder → Vault 스캔      │
  │  ⑤ Vault 갱신                            ⑤ 지원 번들 조립                │
  │  ⑥ Postman → Mailbox 수신증               ⑥ Mailbox → 에이전트가          │
  │                                              제한된 검색 결과 수신         │
  └─────────────────────────────────────────────────────────────────────────┘
```

### 생산 트리거 — 프로바이더가 지식을 포착하는 방법

프로바이더 세션이 기억할 가치가 있는 의사결정 — 설계 선택, 디버깅 인사이트,
해결된 트레이드오프 — 을 생산하면, 프로바이더의 에이전트가
**OpenYggdrasil을 스킬로 호출**하여 이를 포착합니다.

```
  프로바이더 에이전트 (예: Hermes, Claude Code, Cursor)
       │
       │  ① 레포 루트의 SKILL.md를 읽음
       │     → 진입점, 입력 형태, 경계 발견
       │
       │  ② Session Structure Signal 구성:
       │     {
       │       provider_id:         "hermes"
       │       provider_session_id: "session-2026-04-30-abc123"
       │       trigger_type:        "hard_trigger"
       │       surface_reason:      "게이트웨이 패턴 사용 결정..."
       │       turn_range:          { from: 12, to: 18 }
       │       source_ref:          { path_hint: "sessions/abc123.jsonl" }
       │     }
       │
       │  ③ SKILL.md에 정의된 캡처 진입점 호출
       │     → OpenYggdrasil이 콜드스타트, 신호 처리, 종료
       │
       ▼
  OpenYggdrasil 생산 파이프라인이 신호를 수신
```

**핵심 규칙:**
- 프로바이더 에이전트는 **반드시 `SKILL.md`를 읽어** 유효한 진입점을 발견해야 합니다.
  내부 경로를 추측하거나 하드코딩하지 않습니다.
- 신호는 반드시 **`source_ref`** 를 포함해야 합니다 — 출처는 필수이며 선택이 아닙니다.
  출처 참조가 없는 신호는 게이트에서 거부됩니다.
- OpenYggdrasil은 **요청 시 콜드스타트**됩니다. 백그라운드 데몬이 없습니다.
  프로바이더가 호출하면 실행되고, 완료되면 종료됩니다.

### 생산 파이프라인 — 서브에이전트가 지식을 기록하는 과정

소비면과 마찬가지로, **서브에이전트가 곧 파이프라인입니다.**
PTC 엔진은 서브에이전트에게 8개 도구를 제공하고, 서브에이전트가
코드를 조합하여 순서대로 호출합니다.

도구는 두 가지 성격으로 나뉩니다:

- **계약 가드레일** (3개) — 서브에이전트의 추론을 구조화된 출력으로
  유도합니다. 서브에이전트가 추론 토큰을 소비하지만, 가드레일이
  출력 형태와 판단 기준을 제약합니다.
- **작업 도구** (5개) — 서브에이전트가 가드레일을 통과한 결과물을
  스트레스 없이 정규화·기록·포장할 수 있게 돕는 Python 유틸리티입니다.
  추론 불필요 — 서브에이전트가 Python 스크립트를 호출하면 됩니다.

```
  서브에이전트 (프로바이더가 빌려준 LLM)
       │
       │  ① SKILL.md에서 캡처 진입점 확인
       │  ② Provider Capability 선언 (자기 모델 추론 능력)
       │  ③ Effort Manifest 확인 (모듈별 추론 깊이)
       │
       ▼
  PTC 엔진에 신호 전달
       │
       │  ④ PTC가 8개 도구와 실행 계획을 제시
       │  ⑤ 서브에이전트가 코드를 조합하여 도구를 순서대로 호출
       │
       ▼
  ┌─ PTC Engine (생산면) — 8개 도구 ──────────────────────────┐
  │                                                          │
  │  [계약 가드레일 — 서브에이전트의 추론을 구조화]              │
  │                                                          │
  │  ┌─ distill_signal ─────────────────────────────────┐    │
  │  │  원시 신호 → 구조화된 의사결정 후보 추출             │    │
  │  │  추론 깊이: HIGH                                   │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ evaluate_candidate ─────────────────────────────┐    │
  │  │  승격 가치 평가, 중복 제거, 임계값 게이트            │    │
  │  │  추론 깊이: MEDIUM                                  │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ classify_novelty ───────────────────────────────┐    │
  │  │  카테고리 & 새로움 분류                              │    │
  │  │  추론 깊이: HIGH                                   │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  [작업 도구 — 반죽·굽기·포장을 돕는 Python 유틸리티]       │
  │                                                          │
  │  ┌─ stamp_provenance ───────────────────────────────┐    │
  │  │  출처 고리 부착: source_ref, origin_locator        │    │
  │  │  추론 깊이: NONE (결정론적)                         │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ compose_seed ───────────────────────────────────┐    │
  │  │  상류 산출물 → 최종 각인 씨앗 조합                   │    │
  │  │  추론 깊이: NONE (결정론적)                         │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ plant_to_vault ─────────────────────────────────┐    │
  │  │  심기 계획 → Vault에 기록, 생명주기 전환             │    │
  │  │  추론 깊이: NONE (결정론적)                         │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ update_topology ────────────────────────────────┐    │
  │  │  대륙/토픽/에피소드 위상 갱신                        │    │
  │  │  추론 깊이: NONE (결정론적)                         │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ deliver_receipt ────────────────────────────────┐    │
  │  │  Mailbox 수신증 발행                               │    │
  │  │  추론 깊이: NONE (결정론적)                         │    │
  │  └──────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────┘
       │
       ▼
  서브에이전트가 수신증을 갖고 프로바이더 세션으로 복귀
```

### PTC 실행 계획 — 서브에이전트가 받는 것 (캡처)

서브에이전트는 JSON Tool Plan을 받고, 이에 따라 코드를 조합하여
8개 도구를 순서대로 호출합니다:

```json
[
  { "step_id": "distill",   "capability_id": "distill_signal",     "effort": "high",   "input": { "raw_signal": "..." } },
  { "step_id": "evaluate",  "capability_id": "evaluate_candidate", "effort": "medium", "input": { "candidate": "←distill" } },
  { "step_id": "classify",  "capability_id": "classify_novelty",   "effort": "high",   "input": { "candidate": "←distill", "verdict": "←evaluate" } },
  { "step_id": "stamp",     "capability_id": "stamp_provenance",   "effort": "none",   "input": { "candidate": "←distill", "route": "←classify" } },
  { "step_id": "seed",      "capability_id": "compose_seed",       "effort": "none",   "input": { "verdict": "←evaluate", "route": "←classify", "segment": "←stamp" } },
  { "step_id": "plant",     "capability_id": "plant_to_vault",     "effort": "none",   "input": { "seed": "←seed" } },
  { "step_id": "topology",  "capability_id": "update_topology",    "effort": "none",   "input": { "seed": "←seed", "vault_path": "←plant" } },
  { "step_id": "receipt",   "capability_id": "deliver_receipt",     "effort": "none",   "input": { "seed": "←seed", "vault_path": "←plant" } }
]
```

서브에이전트는 **모든 도구를 직접 호출**합니다. 계약 가드레일(3개)에서
추론 토큰이 소비되고, 작업 도구(5개)에서는 서브에이전트가 Python
스크립트를 호출하기만 하면 결정론적으로 처리됩니다.

**계획 생성 모드 3가지:**

| 모드 | 언제 | 서브에이전트 추론 소비 |
|---|---|---|
| `deterministic` | 신호가 단순 (hard_trigger + 명확한 결정) | 최소 (LOW로 다운그레이드 가능) |
| `lease_backed_llm` | 신호가 복잡 (모호한 트레이드오프) | 풀 추론 (HIGH 3회) |
| `fallback` | LLM 추론 실패 시 | 보수적 기본 판정 적용 |

모든 경계에서 **타입이 지정된 계약**이 핸드오프를 검증합니다. 어떤 모듈이든
입력을 거부하면, 체인은 타입이 지정된 `stop_reason`과 함께 정지합니다 —
데이터를 조용히 삭제하지 않습니다.

### 소비 트리거 — 프로바이더가 과거 지식을 검색하는 방법

프로바이더 세션이 과거 의사결정의 맥락이 필요할 때 — "게이트웨이 패턴에 대해
뭘 결정했었지?" — 프로바이더의 에이전트가 **OpenYggdrasil을 서브에이전트로
호출**하여 축적된 지식을 검색합니다.

```
  프로바이더 에이전트 (새 작업 수행 중)
       │
       │  ① 에이전트가 과거 맥락이 필요함을 인식
       │     예: "이 패턴을 전에 논의했었는데..."
       │
       │  ② SKILL.md 읽기 → 검색 진입점 발견
       │
       │  ③ 질의와 함께 검색 진입점 호출:
       │     {
       │       query_text:  "게이트웨이 계약 설계가 뭐였지?"
       │       profile:     "yggdrasilfgpoc"
       │       session_id:  "session-2026-04-30-xyz789"
       │     }
       │
       │  ④ OpenYggdrasil이 Pathfinder를 콜드스타트
       │     → Vault에서 일치하는 토픽 스캔
       │     → 제한된 지원 번들 조립
       │     → 생명주기 인식, 출처 추적된 결과 리턴
       │
       ▼
  에이전트가 Pathfinder 검색 결과 수신:
  {
    status:           "completed"
    pathfinder_bundle: {
      anchor_type:    "topic"
      topic_id:       "topic:gateway-contract"
      support_facts:  ["프로바이더 소유 게이트웨이 사용 결정..."]
      source_paths:   ["vault/queries/gateway-contract.md"]
    }
    lifecycle_records: [{ state: "ACTIVE", valid_from: "..." }]
  }
```

**핵심 규칙:**
- 에이전트는 원시 Vault 덤프가 아닌 **제한된 지원 번들**을 받습니다.
  번들 내 모든 사실은 출처와 생명주기 상태를 함께 전달합니다.
- 토픽이 **SUPERSEDED** 또는 **STALE**이면, 검색 결과가 이를 명시적으로
  표시합니다 — 에이전트에게 조용히 오래된 맥락을 제공하지 않습니다.
- **출처 참조는 필수입니다.** 검색 결과는 항상 해당 지식을 생산한 원래
  프로바이더 세션으로 링크합니다.
- 이것이 **LLM Wiki** 패턴입니다: 프로바이더가 원시 트랜스크립트에서 지식을
  재파생하지 않고, 점진적으로 구축되고 생명주기가 관리되는 지식 표면을 질의합니다.

### 소비 파이프라인 — 서브에이전트가 Vault를 검색하는 과정

여기서 핵심을 이해해야 합니다: **서브에이전트 = Pathfinder입니다.**
별도의 검색 시스템이 존재하는 게 아닙니다. 프로바이더가 빌려준 서브에이전트가
자기 추론 토큰으로 Python 스크립트를 실행하고, 그 결과를 자기가 가져갑니다.

```
  서브에이전트 (프로바이더가 빌려준 LLM)
       │
       │  ① SKILL.md에서 검색 진입점 확인
       │
       │  ② PTC 엔진에 질의 전달
       │     → PTC가 질의를 분석하여 실행 계획(JSON Tool Plan) 생성
       │
       │  ③ 서브에이전트가 PTC 계획에 따라 도구를 순서대로 호출
       │     (서브에이전트의 추론 토큰으로 실행)
       │
       ▼
  ┌─ PTC Engine ─────────────────────────────────────────────┐
  │                                                          │
  │  PTC는 서브에이전트에게 8개의 도구(capability)를 제공:      │
  │                                                          │
  │  ┌─ locate_region ──────────────────────────────────┐    │
  │  │  질의에서 대륙/지역 식별                            │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ select_topic_anchor ────────────────────────────┐    │
  │  │  지역 내에서 토픽 앵커 선택                         │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ read_origin_claims ─────────────────────────────┐    │
  │  │  해당 토픽의 최초 기원 주장 읽기                     │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ read_recent_claims ─────────────────────────────┐    │
  │  │  해당 토픽의 최근 에피소드 읽기                      │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ collect_claim_ids ──────────────────────────────┐    │
  │  │  주장 ID 수집                                      │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ read_source_paths ──────────────────────────────┐    │
  │  │  원본 출처 경로 조회                                │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ assemble_support_bundle ────────────────────────┐    │
  │  │  지원 번들 조립 (앵커된 경우)                        │    │
  │  └──────────────────────────────────────────────────┘    │
  │                                                          │
  │  토픽을 못 찾으면:                                        │
  │  ┌─ assemble_unanchored_bundle ─────────────────────┐    │
  │  │  비앵커 번들 리턴 (anchor_type: "none")             │    │
  │  └──────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────┘
       │
       ▼
  서브에이전트가 결과를 받아 프로바이더 세션으로 복귀
```

### PTC 실행 계획 — 서브에이전트가 받는 것

PTC 엔진은 서브에이전트에게 JSON Tool Plan을 제공합니다. 서브에이전트는
이 계획에 따라 도구를 순서대로 호출합니다:

```json
[
  { "step_id": "region",    "capability_id": "locate_region",           "input": { "query_text": "..." } },
  { "step_id": "anchor",    "capability_id": "select_topic_anchor",     "input": { "query_text": "...", "region_id": "←region" } },
  { "step_id": "origin",    "capability_id": "read_origin_claims",      "input": { "topic_id": "←anchor" } },
  { "step_id": "recent",    "capability_id": "read_recent_claims",      "input": { "topic_id": "←anchor", "limit": 3 } },
  { "step_id": "claim_ids", "capability_id": "collect_claim_ids",       "input": { "recent_rows": "←recent", "origin_rows": "←origin" } },
  { "step_id": "sources",   "capability_id": "read_source_paths",       "input": { "topic_id": "←anchor", "claim_ids": "←claim_ids" } },
  { "step_id": "bundle",    "capability_id": "assemble_support_bundle", "input": { "..." } }
]
```

**계획 생성 모드 3가지:**

| 모드 | 언제 | 서브에이전트 추론 소비 |
|---|---|---|
| `deterministic` | 질의 신호만으로 계획 결정 가능 | 없음 (순수 Python) |
| `lease_backed_llm` | Reasoning Lease로 LLM이 계획 생성 | 서브에이전트 토큰 소비 |
| `fallback` | LLM 계획 생성 실패 시 기본 계획 | 없음 (결정론적 폴백) |

### 서브에이전트 시점의 전체 검색 여정

```
  프로바이더 에이전트
  "게이트웨이 패턴에 대해 뭘 결정했었지?"
       │
       ▼
  서브에이전트 스폰 (프로바이더의 추론 토큰 차용)
       │
       │  ① SKILL.md 읽기 → 검색 진입점 확인
       │  ② Provider Capability 선언 (자기 모델 추론 능력)
       │  ③ Effort Manifest 확인 (모듈별 추론 깊이)
       │
       ▼
  PTC 엔진에 질의 전달
       │
       │  ④ 질의 분석 → 실행 계획(JSON Tool Plan) 생성
       │  ⑤ 도구 7개를 순서대로 호출
       │     locate_region → select_topic_anchor → read_origin_claims
       │     → read_recent_claims → collect_claim_ids → read_source_paths
       │     → assemble_support_bundle
       │
       ▼
  Origin Shortcut: 출처 파일 물리적 존재 확인
       │  없으면 → "origin_missing"으로 정지
       │
       ▼
  Lifecycle Filter: ACTIVE 상태만 필터링
       │  SUPERSEDED/STALE는 명시적 표시
       │
       ▼
  서브에이전트가 결과를 갖고 프로바이더 세션으로 복귀
  → 프로바이더는 출처와 생명주기가 증명된 맥락을 받음
```

소비면은 **절대 맥락을 조작하지 않습니다.** Vault가 비어있으면 Pathfinder는
정직하게 `anchor_type: "none"` 결과를 리턴합니다. 출처를 검증할 수 없으면
`origin_shortcut_missing`으로 정지합니다. 서브에이전트는 항상 자신이 무엇을
받고 있고 왜 받는지 정확히 알 수 있습니다.

---

## 12-모듈 체인

| # | 모듈 | 역할 | 핵심 인사이트 |
|---|---|---|---|
| ① | **Signal** | 원시 프로바이더/세션 이벤트 포착 | 원본 신호를 변형 없이 보존 |
| ② | **Admission Gate** | 신호에서 노이즈 필터링 | 모든 것이 기억될 자격이 있는 것은 아님 |
| ③ | **Seedkeeper** | 각 후보에 출처 스탬프 부착 | 모든 기억은 어디서 왔는지 알아야 함 |
| ④ | **Distiller** | 원시 신호에서 구조화된 의사결정 추출 | 트랜스크립트가 아니라 의사결정이 메모리의 단위 |
| ⑤ | **Evaluator** | 승격 가치 평가 | 구문적 유효성 ≠ 기억할 가치 |
| ⑥ | **Amundsen** | 카테고리와 새로움 판단 | 알려진 토픽인가, 새로운 개척지인가? |
| ⑦ | **Nursery** | 수용된 후보 배양 | 새 지식은 승격 전 인큐베이션 필요 |
| ⑧ | **Map Maker** | 토픽/커뮤니티 구조에 메모리 배치 | 평면 덤프가 아닌 탐색 가능한 구조 |
| ⑨ | **Gardener** | 생명주기 전환: ACTIVE → SUPERSEDED → STALE | 지식은 축적만이 아니라 가지치기도 필요 |
| ⑩ | **Postman** | 제한된 지원 번들 라우팅 | 전달은 부수효과가 아닌 계약 |
| ⑪ | **Mailbox** | 프로바이더 세션 수신함 | 타입 안전 소비 표면 |
| ⑫ | **Pathfinder** | 설명 가능한 지원 자료 검색 | 모든 검색 결과는 출처와 생명주기 증거를 수반 |

---

## Reasoning Lease

일부 복잡한 신호나 모호한 트레이드오프는 단순한 PTC 도구 호출을 넘어섭니다 —
시간 예산과 격리 보장이 있는 확장된 LLM 추론이 필요합니다.

OpenYggdrasil은 이를 **Reasoning Lease** 계층으로 처리합니다. PTC 엔진의
`lease_backed_llm` 모드가 활성화되면 이 계층이 동작합니다:

```
┌───────────────────────────────────────────────────────────┐
│  Reasoning Lease = 3가지 패턴의 조합                        │
│                                                           │
│  ┌─────────────────┐                                     │
│  │ 시간 예산 기반    │  작업당 고정 시간 예산                 │
│  │ 자율 루프        │  에이전트가 사람 없이 작업              │
│  └─────────────────┘                                     │
│           +                                               │
│  ┌─────────────────┐                                     │
│  │ 샌드박스        │  신뢰할 수 없는 코드가 격리 실행         │
│  │ 격리           │  실패 → 롤백, 손상 아님                  │
│  └─────────────────┘                                     │
│           +                                               │
│  ┌─────────────────┐                                     │
│  │ 타입 계약       │  결과가 계약을 통해 흐름                 │
│  │ 통합           │  원시 stdout이나 비타입 산출물 아님       │
│  └─────────────────┘                                     │
└───────────────────────────────────────────────────────────┘
```

Reasoning Lease는 필수 의존성인 `bubblewrap`을 통해 비특권 샌드박스에서
실행되어, 서브에이전트의 복잡한 자율 루프가 메인 시스템을 오염시키지 않도록
안전하게 격리합니다.

---

## 프로바이더 연동 & 설정

OpenYggdrasil은 AI 프로바이더(예: Hermes, Claude Code, Cursor)에 부착되는
콜드스타트 스킬로 동작합니다. 백그라운드 데몬을 시작하거나 별도 서버
프로세스를 관리할 필요가 없습니다.

> **⚠️ 추론 토큰 모델:**
> OpenYggdrasil은 현재 **프로바이더의 추론 토큰을 빌려서 사용**합니다.
> 자체 API 키나 LLM 인프라를 보유하지 않습니다.
> 향후 독립적인 API 키 지정을 통한 자체 추론 지원도 계획되어 있습니다.

### 1. 프로바이더가 OpenYggdrasil을 인식하는 방법

프로바이더는 레포지토리 루트의 **`SKILL.md`** 매니페스트를 읽어 OpenYggdrasil에
연결합니다:
- 에이전트의 스킬 설정을 `SKILL.md`의 절대 경로로 지정합니다.
- 에이전트가 이 계약을 읽으면, 메모리 검색 및 캡처를 위한 정확한 진입점,
  명령 형태, 경계를 파악합니다.

### 2. 시스템 요구사항 & 의존성 설치

OpenYggdrasil은 순수 로컬에서 실행됩니다. 코어 런타임은 Python 표준
라이브러리에 거의 전적으로 의존하지만, Graphify 파생 뷰와 샌드박스 격리에
다음 의존성 스택이 필요합니다:

**지원 운영체제:**
- **Windows / macOS / Linux**: 코어 메모리 파이프라인 전체 지원 (Vault 큐레이션, Graphify 파생 뷰, Pathfinder 검색).
- **Linux / WSL2 (Windows Subsystem for Linux)**: **필수.** Reasoning Lease 샌드박스는 `bubblewrap`을 통한 비특권 격리에 의존하며, 이는 프로덕션 파이프라인의 필수 의존성입니다. Windows/macOS 사용자는 반드시 WSL2를 통해 이 요구사항을 충족해야 합니다.

**코어 선행 요건:**
- **`Python 3.10+`**: 로컬 환경에 설치되어 접근 가능해야 합니다.

**Python 패키지 (pip):**
- **`graphifyy`**: 구조 분석 및 그래프 구축을 위한 코어 동반 패키지
- **`networkx`**: 그래프 파생, 노드 인덱싱, 탐색용
- **`leidenalg` & `igraph`**: 커뮤니티 탐지 및 토픽 클러스터링용
- **`jsonschema`**: 프로바이더 계약 및 메일박스 스키마의 엄격한 검증용
- **`pyyaml`**: 설정 및 매니페스트 파일 읽기/쓰기용
- **`pytest`**: 로컬 계약 검증 및 스모크 테스트용

**시스템 의존성:**
- **`bubblewrap`** (`bwrap`): Reasoning Lease 실행 시 비특권 샌드박스 격리에 **필수** (Linux/WSL).

**이 의존성들은 사용자의 로컬 환경에 설치되어야 합니다.**

> **⚠️ 프로바이더 필수 규칙:**
> 콜드스타트 스킬을 처음 실행하기 전에, 프로바이더는 **반드시 사용자에게 명시적 허가를 요청**해야 합니다.
>
> 1. 프로바이더가 의존성 누락을 감지합니다.
> 2. 프로바이더가 중단하고 사용자에게 프롬프트: *"OpenYggdrasil은 로컬에 설치할 Python 의존성이 필요합니다. 허용하시겠습니까?"*
> 3. 사용자 승인 시에만 의존성을 설치합니다. **무단 또는 프롬프트 없는 설치는 엄격히 금지됩니다.**

### 3. 원터치 콜드스타트

의존성이 승인되고 설치되면, 프로바이더가 `SKILL.md`에 정의된 스킬 진입점을
실행할 수 있습니다. OpenYggdrasil 런타임은 **요청 시 콜드스타트**되고,
필요한 메모리 트랜잭션을 실행한 후, 깔끔하게 종료됩니다.

### 수동 설치 확인

프로바이더를 연결하기 전에 설치를 확인하려면:

```bash
# 레포지토리 클론
git clone https://github.com/INTEGRITY2077/openyggdrasil.git
cd openyggdrasil

# 의존성 설치 (사용자 주도)
pip install -r requirements.txt

# 임포트 스모크 테스트
python runtime/import_smoke.py
```

### 레포지토리 구조

```
openyggdrasil/
├── contracts/          # JSON 스키마 — 모듈 간 API
├── runtime/
│   ├── admission/      # Gate, Seedkeeper, Amundsen 핸드오프
│   ├── capture/        # Signal 캡처, Decision Distiller
│   ├── evaluation/     # Evaluator, 승격 가치 평가
│   ├── cultivation/    # Nursery, Gardener, 생명주기
│   ├── placement/      # Map Maker, 토픽/에피소드 배치
│   ├── provenance/     # 출처 추적, 시간 엣지
│   ├── retrieval/      # Pathfinder, PTC 도구, Graphify 어댑터
│   ├── delivery/       # Postman, Mailbox, 지원 번들
│   ├── reasoning/      # Reasoning Lease, 프로바이더 게이트
│   ├── runner/         # 오케스트레이션, 회귀 진입점
│   ├── ptc/            # Programmatic Tool Calling 엔진
│   └── governance/     # 페이즈 자동화
├── common/graphify/    # 파생 그래프/위키/인덱스 뷰 (비SOT)
├── providers/hermes/   # Hermes 공개 어댑터
├── vault/              # 정규 프로젝트 메모리
└── tests/              # 510+ 테스트
```

---

## 영감 & 감사

OpenYggdrasil은 두 가지 핵심 아이디어 위에 서 있습니다.

### Andrej Karpathy의 [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

Karpathy는 핵심 인사이트를 명확히 했습니다: 매 질의마다 RAG로 지식을 재파생하는
대신, LLM이 **점진적으로 영속적인 위키를 구축하고 유지**하게 하라.
OpenYggdrasil은 이 철학을 직접 흡수했습니다:

| LLM Wiki 개념 | OpenYggdrasil 흡수 |
|---|---|
| **Raw Sources** (불변 원본) | → Provider Signal (①) — 원본은 절대 변형되지 않음 |
| **The Wiki** (LLM이 유지하는 지식) | → Vault — 생명주기 상태가 있는 정규 메모리 |
| **The Schema** (CLAUDE.md/AGENTS.md 규칙) | → `contracts/` — 기계 판독 가능한 경계 |
| **Ingest** 연산 | → 생산 파이프라인 (Signal → Gardener) |
| **Query** 연산 | → 소비 파이프라인 (Pathfinder → Mailbox) |
| **Lint** 연산 | → Gardener 가지치기 + Amundsen 일관성 검사 |
| **`index.md`** 카탈로그 | → Pathfinder의 인덱스 기반 검색 |
| **`log.md`** 연대기 기록 | → 시간 엣지가 있는 출처 저장소 |

> *"위키는 소스를 추가할 때마다 더 풍부해집니다. 사람의 일은 소스를 큐레이션하고
> 좋은 질문을 하는 것입니다. LLM의 일은 나머지 전부입니다."*
> — Karpathy

OpenYggdrasil은 이를 단일 사용자/단일 LLM에서
타입 계약, 생명주기 거버넌스, 프로바이더 중립 공유가 있는
**멀티 프로바이더/멀티 에이전트**로 확장합니다.

### [Graphify](https://github.com/safishamsi/graphify) (v5)

Graphify는 구조 분석 계층을 제공합니다 — 코드베이스와 지식을
탐색 가능한 그래프로 변환:

| Graphify 개념 | OpenYggdrasil 흡수 |
|---|---|
| `detect → extract → build_graph → cluster → analyze → report → export` 파이프라인 | → `common/graphify/` 파생 뷰 엔진 |
| NetworkX + Leiden 커뮤니티 클러스터링 | → Map Maker를 위한 토픽/커뮤니티 구조 |
| 신뢰도 라벨 (EXTRACTED / INFERRED / AMBIGUOUS) | → 검색 결과의 출처 신뢰도 |
| 순수 Python, 로컬, 오프라인 | → **외부 인프라 의존성 없음** |

---

## 설계 원칙

1. **메모리는 엔진이지, 텍스트 더미가 아닙니다.** 모든 메모리 조각에는 출처,
   생명주기 상태, 타입 계약이 있습니다.

2. **결정론적 기반, 선택적 추론.** 파이프라인은 LLM 추론 없이도 작동합니다.
   Reasoning Lease는 옵트인 강화입니다.

3. **기본적으로 프로바이더 중립.** 어떤 프로바이더도 Vault에 특별한 접근권을
   갖지 않습니다. Hermes, Codex, Claude Code, 미래의 프로바이더가 동일한
   계약을 공유합니다.

4. **외부 인프라 없음.** 순수 Python, 그래프에는 NetworkX, 저장에는 파일시스템.
   기본 파이프라인에 데이터베이스, 벡터 스토어, Docker 불필요.

5. **Fail-closed, not fail-open.** 증거가 없으면 시스템은 타입이 지정된
   불가용성을 보고합니다 — 절대 준비 상태를 조작하지 않습니다.

6. **파생 뷰는 절대 진실 원천이 아닙니다.** Graphify 인덱스, 그래프 뷰,
   위키 페이지는 파생 표면입니다. Vault만이 유일한 정규 표면입니다.

---

## 현재 상태 — 라이브 테스팅

> **이 프로젝트는 프로덕션 준비가 되지 않았습니다.** 아키텍처를 라이브
> 테스팅하고 공개적으로 반복하고 있습니다.

모듈 체인 아키텍처는 37,000줄 이상의 런타임 코드와 510개 이상의 통과
테스트로 설계되었지만, 엔드투엔드 파이프라인은 아직 signal에서 mailbox까지
관통하지 않습니다.

**존재하는 것:**
- 12-모듈 체인 계약 정의 및 내부 로직
- 프로바이더 중립적 캡처, 평가, 재배, 검색 구현
- PTC (Programmatic Tool Calling) 지원 Pathfinder 검색
- Graphify 파생 스냅샷 뷰
- Hermes 프로바이더 어댑터 (포그라운드)

**아직 작동하지 않는 것:**
- 최상위 파사드 와이어링 (35개 스텁이 내부 로직에 연결 필요)
- 엔드투엔드 파이프라인 관통 (signal → mailbox)
- Mailbox 비동기 위임 루프
- Bubblewrap 샌드박스 러너 통합
- 안전한 프로바이더 소유 게이트웨이 계약

프로바이더 대면 운영 계약은 [SKILL.md](./SKILL.md)를 참조하세요.

---

## 기여

기여를 환영합니다. 새 모듈 인터페이스를 제안하기 전에 기존 `contracts/`
스키마를 읽어주세요 — 타입 계약 경계가 프로젝트에서 가장 중요한
아키텍처 결정입니다.

## 라이선스 & 브랜드 가이드라인

이 프로젝트는 오픈소스이며 [Apache License 2.0](./LICENSE) 하에 배포됩니다.
이 라이선스 조건에 따라 코드를 자유롭게 사용, 수정, 배포할 수 있습니다.

**상표 & 브랜드 보호 (제6조):**
코드는 오픈소스이지만, 브랜드명 **"OpenYggdrasil"** 과 **"INTEGRITY2077"**,
그리고 관련 로고와 트레이드 드레스는 엄격히 보호됩니다. Apache 2.0
라이선스는 이러한 상표의 사용 권한을 명시적으로 **부여하지 않습니다**.

이 프로젝트를 포크하거나 수정된 버전을 배포하는 경우, 이름을 변경해야 하며
OpenYggdrasil 또는 INTEGRITY2077 브랜딩을 사용하여 해당 버전을 식별할 수 없습니다.

동반 의존성 고지는 [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)를 참조하세요.
