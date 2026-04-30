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
  에이전트가 자기 쉘/도구호출로 Python 스크립트 실행
  → 12-모듈 체인이 결정론적으로 동작
  → 결과를 에이전트가 받아감
```

이 구조에서 빌려 쓰는 것은 두 가지입니다:

| 빌려 쓰는 것 | 설명 |
|---|---|
| **실행 컨텍스트** | 에이전트의 쉘/도구호출 능력으로 Python 스크립트를 실행 |
| **추론 토큰** | Reasoning Lease에서 LLM 판단이 필요할 때 에이전트의 토큰 사용 |

12-모듈 체인 자체는 순수 Python이라 LLM 추론 없이 돌아갑니다.
추론 토큰이 필요한 건 Reasoning Lease 단계뿐입니다.

향후 독립적인 API 키 지정을 통해 프로바이더 없이 자체 실행하는 모드도
지원할 계획입니다.

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

### 브릿지 — Vault가 단일 진실 원천

Vault는 유일한 정규 메모리 표면입니다. Graphify가 그 위에 파생된
그래프/위키/인덱스 뷰를 구축하지만, **Graphify는 절대 진실 원천이 아닙니다** —
파생된 가시성 계층일 뿐입니다.

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

### 생산 파이프라인 — Signal에서 Vault까지

신호가 시스템에 진입하면 12-모듈 체인을 통해 흐릅니다:

```
  Session Structure Signal
       │
       ▼
  ┌─ Distiller (증류기) ─────────────────────────────────────┐
  │  원시 신호 → 구조화된 의사결정 후보                         │
  │  추출: decision_text, rationale, alternatives,           │
  │        confidence_score, stability_state                 │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Evaluator (평가자) ─────────────────────────────────────┐
  │  승격 가치 평가                                           │
  │  검사: 의미적 유효성, 중복 제거, 임계값 게이트              │
  │  출력: evaluator_verdict → ready_for_amundsen            │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Amundsen (탐험가) ──────────────────────────────────────┐
  │  카테고리 & 새로움 분류                                    │
  │  "이 토픽은 알려진 것인가, 새로운 대륙인가?"                 │
  │  출력: continent_route + topic_route                      │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Seedkeeper (씨앗 관리자) ───────────────────────────────┐
  │  출처 고리 부착: source_ref, origin_locator,              │
  │  turn_range, dedup_key, integrity_status                 │
  │  출력: planting_ready 플래그가 포함된 보존 세그먼트          │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Nursery (묘목장) ───────────────────────────────────────┐
  │  모든 상류 산출물로부터 최종 각인 씨앗 조합                  │
  │  산출물: verdict + route + segment                        │
  │  출력: seed_identity_key가 포함된 engraved_seed           │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Gardener (정원사) ──────────────────────────────────────┐
  │  심기 계획 → 라우팅 구축 → Vault에 기록                    │
  │  생성: 토픽 페이지 + 출처 추적 페이지                       │
  │  생명주기: ACTIVE → SUPERSEDED → STALE 전환               │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Map Maker (지도 제작자) ────────────────────────────────┐
  │  위상 갱신: 대륙/토픽/에피소드 배치                         │
  │  인접 키 및 브릿지 토폴로지 유지                            │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Postman (우체부) ───────────────────────────────────────┐
  │  전달 핸드오프 구축 → Mailbox에 제출                        │
  │  클리어링하우스 이벤트 + 푸시 전달 기록                      │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
                                          Vault 갱신 완료
                                     Mailbox 수신증 기록 완료
```

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

### 소비 파이프라인 — Vault에서 프로바이더 세션까지

검색 질의가 시스템에 진입하면:

```
  검색 질의
       │
       ▼
  ┌─ Pathfinder (길잡이) ────────────────────────────────────┐
  │  질의 → Vault 스캔 → 토픽 앵커 해결                       │
  │  모드: "topic-page-recent-origin" (앵커됨)                │
  │        "unanchored" (일치하는 토픽 없음)                   │
  │  출력: support_facts, source_paths,                      │
  │        episode_ids, claim_ids가 포함된 pathfinder_bundle  │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Origin Shortcut (출처 단축) ────────────────────────────┐
  │  source_ref → 물리적 파일 존재 확인으로 해결               │
  │  원본 파일이 없으면 → "origin_missing"으로 정지            │
  │  출처는 주장만이 아니라 검증 가능해야 함                     │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Lifecycle Filter (생명주기 필터) ───────────────────────┐
  │  생명주기 상태에 따라 검색 결과 필터링                      │
  │  기본: ACTIVE만                                          │
  │  선택: SUPERSEDED/STALE 포함하여 히스토리 조회              │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Product Route (제품 경로) ──────────────────────────────┐
  │  전달 형식 및 Graphify 힌트 상태 결정                      │
  │  가드: 출력에 금지된 텍스트 패턴 없음                       │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
  ┌─ Mailbox Delivery (우편함 전달) ────────────────────────┐
  │  Pathfinder 검색 결과 → inbox JSONL                      │
  │  라우팅: profile + session_id 기준                        │
  │  프로바이더 에이전트가 자신의 inbox에서 읽음                 │
  └──────────────────────────────────────────────┬───────────┘
                                                 ▼
                                     프로바이더 에이전트가
                                   제한되고 설명 가능한 맥락 수신
```

소비면은 **절대 맥락을 조작하지 않습니다.** Vault가 비어있으면 Pathfinder는
정직하게 `anchor_type: "none"` 결과를 리턴합니다. 출처를 검증할 수 없으면
`origin_shortcut_missing`으로 정지합니다. 에이전트는 항상 자신이 무엇을
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

일부 작업은 결정론적 파이프라인 실행 이상을 요구합니다 — 시간 예산과
격리 보장이 있는 확장된 LLM 추론이 필요합니다.

OpenYggdrasil은 이를 **Reasoning Lease** 계층으로 분리합니다:

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

기본 파이프라인은 추론 기능이 불가능할 때도 작동합니다 —
결정론적 모듈은 선택적 LLM 추론에 의존하지 않습니다.

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


---

## Reasoning Lease

Some tasks require more than deterministic pipeline execution — they need
extended LLM reasoning with time budgets and isolation guarantees.

OpenYggdrasil separates this as an **optional Reasoning Lease** layer:

```
┌───────────────────────────────────────────────────────────┐
│  Reasoning Lease = 3 patterns combined                    │
│                                                           │
│  ┌─────────────────┐                                     │
│  │ Time-Budgeted   │  Fixed time budget per task          │
│  │ Autonomous Loop  │  Agent works without human presence  │
│  └─────────────────┘                                     │
│           +                                               │
│  ┌─────────────────┐                                     │
│  │ Sandbox         │  Untrusted code runs in isolation     │
│  │ Isolation       │  Failure → rollback, not corruption   │
│  └─────────────────┘                                     │
│           +                                               │
│  ┌─────────────────┐                                     │
│  │ Typed Contract  │  Results flow back through contracts  │
│  │ Integration     │  Not raw stdout or untyped artifacts  │
│  └─────────────────┘                                     │
└───────────────────────────────────────────────────────────┘
```

The base pipeline keeps working when reasoning capability is unavailable —
deterministic modules never depend on optional LLM reasoning.

---

## Provider Integration & Setup

OpenYggdrasil operates as a cold-started skill attached to your AI provider (e.g., Hermes, Claude Code, Cursor). You do not need to start background daemons or manage separate server processes. 

### 1. How Providers Recognize OpenYggdrasil

Providers attach to OpenYggdrasil by reading the **`SKILL.md`** manifest at the repository root. To initiate the connection:
- Point your agent's skill configuration to the absolute path of `SKILL.md`.
- The agent reads this contract, which defines the exact entrypoints, command shapes, and boundaries for memory retrieval and capture.

### 2. System Requirements & Dependency Installation

OpenYggdrasil runs purely locally. The core runtime relies almost entirely on the Python Standard Library, but the Graphify-derived views and Sandbox isolations require the following minimal dependency stack:

**Supported Operating Systems:**
- **Windows / macOS / Linux**: Full support for the core memory pipeline (Vault curation, Graphify derived views, and Pathfinder retrieval).
- **Linux / WSL2 (Windows Subsystem for Linux)**: Exclusively required if you use the optional **Reasoning Lease Sandbox**. This feature relies on `bubblewrap` for unprivileged isolation. Windows/macOS users can still use the entire base pipeline without it.

**Core Prerequisite:**
- **`Python 3.10+`**: Must be installed and accessible in the local environment.

**Python Packages (via pip):**
- **`graphifyy`**: the core companion package for structural analysis and graph building
- **`networkx`**: for graph derivation, node indexing, and traversal
- **`leidenalg` & `igraph`**: for community detection and topic clustering
- **`jsonschema`**: for strictly validating provider contracts and mailbox schemas
- **`pyyaml`**: for reading/writing configuration and manifest files
- **`pytest`**: for local contract verification and smoke tests

**System Dependencies:**
- **`bubblewrap`** (`bwrap`): required for unprivileged sandbox isolation during Reasoning Lease execution (Linux/WSL only).

**These dependencies must be installed in the user's local environment.**

> **⚠️ Mandatory Rule for Providers:**
> Before executing the cold-start skill for the first time, the provider **MUST ask the user for explicit permission** to install these dependencies.
> 
> 1. Provider detects that dependencies are missing.
> 2. Provider halts and prompts the user: *"OpenYggdrasil requires Python dependencies (listed in requirements) to be installed locally. Do you allow this?"*
> 3. Only upon user approval, the provider installs the requirements. **Silent or unprompted installations are strictly forbidden.**

### 3. One-Touch Cold Start

Once dependencies are approved and installed, the provider can execute the skill entrypoints defined in `SKILL.md`. The OpenYggdrasil runtime **cold-starts itself on demand**, executes the required memory transaction, and shuts down cleanly.

### Verify Installation Manually

If you prefer to verify the installation before attaching a provider:

```bash
# Clone the repository
git clone https://github.com/INTEGRITY2077/openyggdrasil.git
cd openyggdrasil

# Install dependencies (user-initiated)
pip install -r requirements.txt # (assuming requirements exist)

# Run import smoke test
python runtime/import_smoke.py
```

### Repository Structure

```
openyggdrasil/
├── contracts/          # JSON schemas — the API between modules
├── runtime/
│   ├── admission/      # Gate, Seedkeeper, Amundsen handoff
│   ├── capture/        # Signal capture, Decision Distiller
│   ├── evaluation/     # Evaluator, promotion worthiness
│   ├── cultivation/    # Nursery, Gardener, lifecycle
│   ├── placement/      # Map Maker, topic/episode placement
│   ├── provenance/     # Source tracking, temporal edges
│   ├── retrieval/      # Pathfinder, PTC tools, Graphify adapters
│   ├── delivery/       # Postman, Mailbox, support bundles
│   ├── reasoning/      # Reasoning Lease, provider gates
│   ├── runner/         # Orchestration, regression entrypoints
│   ├── ptc/            # Programmatic Tool Calling engine
│   └── governance/     # Phase automation
├── common/graphify/    # Derived graph/wiki/index views (non-SOT)
├── providers/hermes/   # Hermes public adapter
├── vault/              # Canonical project memory
└── tests/              # 510+ tests
```

---

## Inspirations & Acknowledgements

OpenYggdrasil stands on the shoulders of two key ideas.

### Andrej Karpathy's [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

Karpathy articulated the core insight: instead of re-deriving knowledge via RAG
on every query, have the LLM **incrementally build and maintain a persistent
wiki**. OpenYggdrasil absorbed this philosophy directly:

| LLM Wiki Concept | OpenYggdrasil Absorption |
|---|---|
| **Raw Sources** (immutable originals) | → Provider Signal (①) — originals are never mutated |
| **The Wiki** (LLM-maintained knowledge) | → Vault — canonical memory with lifecycle states |
| **The Schema** (CLAUDE.md/AGENTS.md rules) | → `contracts/` — machine-readable boundaries |
| **Ingest** operation | → Production pipeline (Signal → Gardener) |
| **Query** operation | → Consumption pipeline (Pathfinder → Mailbox) |
| **Lint** operation | → Gardener pruning + Amundsen consistency checks |
| **`index.md`** catalog | → Pathfinder's index-based retrieval |
| **`log.md`** chronological record | → Provenance store with temporal edges |

> *"The wiki keeps getting richer with every source you add. The human's job is
> to curate sources and ask good questions. The LLM's job is everything else."*
> — Karpathy

OpenYggdrasil extends this from single-user/single-LLM to
**multi-provider/multi-agent** with typed contracts, lifecycle governance, and
provider-neutral sharing.

### [Graphify](https://github.com/safishamsi/graphify) (v5)

Graphify provides the structural analysis layer — turning codebases and knowledge
into navigable graphs:

| Graphify Concept | OpenYggdrasil Absorption |
|---|---|
| `detect → extract → build_graph → cluster → analyze → report → export` pipeline | → `common/graphify/` derived view engine |
| NetworkX + Leiden community clustering | → Topic/community structure for Map Maker |
| Confidence labels (EXTRACTED / INFERRED / AMBIGUOUS) | → Provenance confidence in retrieval results |
| Pure Python, local, offline | → **No external infrastructure dependency** |

---

## Design Principles

1. **Memory is an engine, not a text pile.** Every piece of memory has a source,
   a lifecycle state, and a typed contract.

2. **Deterministic base, optional reasoning.** The pipeline works without LLM
   reasoning. Reasoning Lease is an opt-in enhancement.

3. **Provider-neutral by default.** No provider gets special access to the vault.
   Hermes, Codex, Claude Code, and future providers share the same contracts.

4. **No external infrastructure.** Pure Python, NetworkX for graphs, filesystem
   for storage. No database, no vector store, no Docker required for the base
   pipeline.

5. **Fail-closed, not fail-open.** When evidence is missing, the system reports
   typed unavailability — it never fabricates readiness.

6. **Derived views are never source of truth.** Graphify indexes, graph views,
   and wiki pages are derived surfaces. The vault is the only canonical surface.

---

## Current State — Live Testing

> **This project is not production-ready.** We are live-testing the architecture
> and iterating in public.

The module chain architecture is designed with 37,000+ lines of runtime code
and 510+ passing tests — but the end-to-end pipeline does not yet pass through
from signal to mailbox.

**What exists:**
- 12-module chain contract definitions and internal logic
- Provider-neutral capture, evaluation, cultivation, and retrieval implementations
- Pathfinder retrieval with PTC (Programmatic Tool Calling) support
- Graphify-derived snapshot views
- Hermes provider adapter (foreground)

**What does not work yet:**
- Top-level facade wiring (35 stubs need to be connected to internal logic)
- End-to-end pipeline pass-through (signal → mailbox)
- Mailbox async delegation loop
- Bubblewrap sandbox runner integration
- Safe provider-owned gateway contract

See the [SKILL.md](./SKILL.md) for the provider-facing operating contract.

---

## Contributing

Contributions are welcome. Please read the existing `contracts/` schemas before
proposing new module interfaces — the typed contract boundary is the most
important architectural decision in the project.

## License & Brand Guidelines

This project is open-source and released under the [Apache License 2.0](./LICENSE).
You are free to use, modify, and distribute the code under the terms of this license.

**Trademark & Brand Protection (Section 6):**
While the code is open-source, the brand names **"OpenYggdrasil"** and **"INTEGRITY2077"**, along with their associated logos and trade dress, are strictly protected. The Apache 2.0 License explicitly **does not grant** permission to use these trademarks. 

If you fork or distribute a modified version of this project, you must change the name and cannot use the OpenYggdrasil or INTEGRITY2077 branding to identify your version.

See [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) for companion dependency notices.
