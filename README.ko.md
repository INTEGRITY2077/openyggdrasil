<p align="center">
  <h1 align="center">🌳 openyggdrasil</h1>
  <p align="center">
    <strong>프로바이더 중립적 AI 코딩 에이전트 메모리 엔진</strong>
  </p>
  <p align="center">
    <em>프로바이더 간 축적되는<br/>
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

### 📊 현재 상태 — 아키텍처 정렬도 스코어카드 (2026-05-03, POC Phase 1-6 완료)

> **⚠️ 이 프로젝트는 프로덕션 준비가 되지 않았습니다.**
> 9차 로드맵(CQRS 오퍼레이터 세션 루프 + 메일링 프로토콜 기반 목표 아키텍처)을 향해 런타임 코드를 라이브 테스팅하며 공개적으로 반복하고 있습니다.
> **Effort normalizer는 공식 퇴역**하고, 페르소나(Persona) 문서 기반 아키텍처로 전환되었습니다.
> **멀티프로바이더 메일박스 POC Phase 1-6 전 구간 검증 완료 (18/18 PASS).**

아래 표는 본 README에 기술된 아키텍처와 실제 구현 간의 정렬도를 정량화한 것입니다. 오해를 방지하기 위해, 각 블록의 현재 상태를 4단계(LIVE / PARTIAL / STUB / ABSENT)로 명시합니다.

| 등급 | 의미 |
|---|---|
| 🟢 **LIVE** | 런타임 코드 존재, 테스트 PASS 또는 핵심 검증 완료 |
| 🟡 **PARTIAL** | 코드/계약 존재, 엔드투엔드 관통 미검증 또는 오퍼레이터 세션 통합 중 |
| 🟠 **STUB** | 파일/개념만 존재하거나 뼈대 코드만 스텁 상태 |
| 🔴 **ABSENT** | 코드 미존재, 설계 문서만 있거나 없음 |

#### 생산면 (Production Side)
| 모듈 | 상태 | 비고 |
|---|---|---|
| Session Structure Signal | 🟢 LIVE | 나이테 확립. Same-Run Typed Ref Source 검증 완료 |
| Admission Gate | 🟡 PARTIAL | `source_ref` 계약 검증 동작. Quality Gate P0 이슈 발행됨 |
| Distiller | 🟡 PARTIAL | 가드레일 + 페르소나 존재. SPO 추출(`build_spo_triples`) 구현 완료 |
| Evaluator | 🟡 PARTIAL | PTC Execution Trace Packet 빌더 구현 완료 |
| Amundsen | 🟡 PARTIAL | 대륙 분기 스키마 + 런타임 + 페르소나 구현 |
| Map Maker | 🟡 PARTIAL | 위상 계산 + 페르소나 구현. Q05 엣지 판정(`_determine_edge_type`) 결정론적 구현 완료 |
| Gardener | 🟡 PARTIAL | 물리적 식재 + 페르소나 신규 추가. 자동 치유 미완 |
| Postman | 🟢 LIVE | `deliver_receipt` 구현 완료 + `run_producer`/`run_consumer` 통합. POC Phase 1-6 18/18 PASS |
| 수동 편집 보호 | 🟢 LIVE | `wiki_write_guard.py` 콘텐츠 해시 가드 + atomic write. 5개 테스트 PASS |
| 피드백 루프 | 🟠 STUB | P1 이슈 발행됨. 런타임 코드 미착수 |

#### 소비면 (Consumption Side)
| 모듈 | 상태 | 비고 |
|---|---|---|
| Pathfinder | 🟡 PARTIAL | 페르소나 존재. `search_vault_bm25` 스터브 구현 (Q02 기반, QMD 연동 전 폴백) |
| Support Bundle | 🟡 PARTIAL | 3-tier 나이테 추적. Bounded bundle (max 3 facts) 라이브 검증 완료 |
| Mailbox | 🟢 LIVE | 멀티프로바이더 POC Phase 1-6 18/18 PASS. `status.json`+`manifest.json` 운영. Reverse Push 영수증 동작 |
| Lifecycle Filter | 🟢 LIVE | 프론트매터 파싱 및 ACTIVE/SUPERSEDED 상태 필터링 완벽 작동 |

#### 인프라 / 크로스커팅
| 모듈 | 상태 | 비고 |
|---|---|---|
| SKILL.md 콜드스타트 | 🟢 LIVE | 프로바이더 자동 인식 및 진입점 호출 동작 |
| Typed PTC Engine | 🟡 PARTIAL | `primitives.py` SPO+엣지+BM25 스터브 추가 (+300줄). 과대주장 교정 유지 |
| Persona System (9역할) | 🟢 LIVE | 9개 페르소나 완비 (effort normalizer 대체) |
| Reasoning Lease | 🟡 PARTIAL | Multi-OS 샌드박스 (Mac/WSL2) 클린룸 제안. Windows 미지원 공식 확정 |
| Vault (SOT) | 🟡 PARTIAL | 디렉토리 동작. Atomic write guard + 콘텐츠 해시 보호 (wiki_write_guard.py) |
| Graphify 파생 뷰 | 🟡 PARTIAL | 커뮤니티 파생 스크립트 동작 (GPL 의존성 제거 완료) |
| Cross-Provider | 🟡 PARTIAL | 교차 메모리 접근 테스트 PASS |
| Hermes Adapter | 🟡 PARTIAL | Background gateway contract bounded verification PASS |
| i18n 파이프라인 | 🟡 PARTIAL | `wiki_capture_signal.py` language_code fail-closed 검증. 1개 테스트 PASS |
| 인라인 출처 마킹 | 🟡 PARTIAL | `wiki_production_safety_gate.py` provenance_refs 게이트 + source_trace_path. 2개 테스트 PASS |
| 원자적 롤백 | 🟡 PARTIAL | `atomic_write_wiki_page` temp file + os.replace + guard-before-write. 2개 테스트 PASS |

#### 총 정렬도 요약
| 영역 | 블록 수 | 🟢 LIVE | 🟡 PARTIAL | 🟠 STUB | 🔴 ABSENT | 정렬률 |
|---|---|---|---|---|---|---|
| 생산면 | 10 | 3 | 6 | 1 | 0 | 93% |
| 소비면 | 4 | 2 | 2 | 0 | 0 | 91% |
| 인프라 | 11 | 2 | 9 | 0 | 0 | 90% |
| **전체** | **25** | **7** | **17** | **1** | **0** | **91%** |


## 시스템 요구사항 및 설정

openyggdrasil은 AI 프로바이더(예: Hermes, Claude Code, Cursor)에 부착되는
콜드스타트 스킬로 동작합니다. 백그라운드 데몬을 시작하거나 별도 서버
프로세스를 관리할 필요가 없습니다.

> **⚠️ 추론 토큰 임대 모델 (비동기 다중화 / Asynchronous Multiplexing):**
> openyggdrasil은 자체 API 키를 가지지 않으며, **프로바이더 본체(IDE)의 추론 토큰을 역으로 빌려서(Lease) 작동**합니다.
> 사용자와의 대화를 방해하지 않기 위해 오퍼레이터는 비동기 백그라운드 작업으로 스폰됩니다. 따라서, 프로바이더가 환경 변수로 자신의 API 키를 넘겨주어 오퍼레이터가 자율 실행하게 하거나, 오퍼레이터가 표준 출력(Stdout)으로 뱉어내는 **프롬프트(Task Contract)**를 프로바이더가 백그라운드에서 비동기로 감지하고 대답을 밀어넣는(Multiplexing) 논블로킹 '역호출 핑퐁' 구조로 작동합니다.

### 1. 프로바이더가 openyggdrasil을 인식하는 방법

프로바이더는 레포지토리 루트의 **`SKILL.md`** 매니페스트를 읽어 openyggdrasil에
연결합니다:
- 에이전트의 스킬 설정을 `SKILL.md`의 절대 경로로 지정합니다.
- 에이전트가 이 계약을 읽으면, 메모리 검색 및 캡처를 위한 정확한 진입점,
  명령 형태, 경계를 파악합니다.

### 2. 시스템 요구사항 & 의존성 설치

openyggdrasil은 순수 로컬에서 실행됩니다. 코어 런타임은 Python 표준
라이브러리에 거의 전적으로 의존하지만, Graphify 파생 뷰와 샌드박스 격리에
다음 의존성 스택이 필요합니다:

**지원 운영체제:**
- **Linux / WSL2 전용**: openyggdrasil의 핵심인 Reasoning Lease 샌드박스는 `bubblewrap`을 통한 비특권 리눅스 컨테이너 격리 환경에 의존합니다.
  - **주의 (Cross-OS 교차 실행):** Windows 네이티브 환경에 설치된 프로바이더에서 WSL2 내부의 openyggdrasil을 호출하는 교차 실행(Cross-border Tunneling)은 물리적으로 가능하지만 **강력히 비권장(Not Recommended)**합니다. Windows-WSL2 간 경로 번역(Path Translation)의 복잡성, 9P 프로토콜에 의한 I/O 성능의 급격한 저하, 그리고 파이프(Stdin/Stdout) 인코딩 차이로 인한 데드락 발생 확률이 매우 높기 때문입니다. 안정적인 작동을 위해 프로바이더 본체 역시 가급적 WSL2 내부에서 직접 실행하는 것을 권장합니다.

**코어 선행 요건:**
- **`Python 3.10+`**: 로컬 환경에 설치되어 접근 가능해야 합니다.

**Python 패키지 (pip):**
- **`graphifyy`**: (주의: 개념적 이름은 Graphify(v5)이나 PyPI 패키지명은 `graphifyy`입니다) 구조 분석 및 그래프 구축을 위한 코어 동반 패키지
- **`networkx`**: 그래프 파생, 노드 인덱싱, 탐색, Louvain 커뮤니티 탐지용
- **`jsonschema`**: 프로바이더 계약 및 메일박스 스키마의 엄격한 검증용
- **`pyyaml`**: 설정 및 매니페스트 파일 읽기/쓰기용
- **`pytest`**: 로컬 계약 검증 및 스모크 테스트용

**시스템 의존성:**
- **`bubblewrap`** (`bwrap`): Reasoning Lease 실행 시 비특권 샌드박스 격리에 **필수** (Linux/WSL).

**이 의존성들은 사용자의 로컬 환경에 설치되어야 합니다.**

> **⚠️ 프로바이더 필수 규칙:**
> 초기 셋업(Cold Start) 스킬을 처음 실행하기 전에, 프로바이더는 **반드시 사용자에게 명시적 허가를 요청**해야 합니다.
>
> 1. 프로바이더가 의존성 누락을 감지합니다.
> 2. 프로바이더가 중단하고 사용자에게 프롬프트: *"openyggdrasil은 로컬에 설치할 Python 의존성이 필요합니다. 허용하시겠습니까?"*
> 3. 사용자 승인 시에만 의존성을 설치합니다. **무단 또는 프롬프트 없는 설치는 엄격히 금지됩니다.**

### 3. 세션 스코프 콜드스타트 (Session-Scoped Cold Start)

의존성이 승인되고 설치되면, 프로바이더가 `SKILL.md`에 정의된 스킬 진입점을
실행할 수 있습니다. openyggdrasil 런타임은 **프로바이더 세션 단위로 콜드스타트**됩니다.
시스템 레벨 백그라운드 데몬은 없지만, 프로바이더 세션에 바인딩된 오퍼레이터 세션이
세션 수명 동안 메일박스를 통해 상주할 수 있습니다. 작업이 완료되거나 타임아웃 시
깔끔하게 종료됩니다.

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

> **근본적 차이 — 인지 비용을 언제 지불하는가:**
> - **RAG (Read-time):** 원본을 날것 그대로 청크 → 임베딩 → 벡터 DB. **쿼리 시점**에 유사도 검색. 검색 품질의 천장은 **인제스트 품질**에 바운딩됩니다. 저장된 것 자체가 비구조적이면, 아무리 임베딩이 좋아도 검색 결과도 비구조적입니다.
> - **openyggdrasil (Write-time):** 프로바이더가 의뢰(save intent) → 오퍼레이터가 **생산 시점**에 증류(Distill) → 평가(Evaluate) → 분류(Classify) → 식재(Plant). 검색은 **이미 구조화된 지식**에 대해 수행됩니다.
>
> Karpathy의 비유: RAG는 매번 소스코드를 grep하는 것. openyggdrasil은 **미리 컴파일된 바이너리**를 실행하는 것.

**벡터 데이터베이스도 마찬가지입니다.** 인프라 의존성(Neo4j, Pinecone, 임베딩)을
추가할 뿐, 근본 문제를 해결하지 않습니다: *무엇을 기억하고, 무엇을 잊고, 무엇을
전달할지 누가 결정하는가?*

openyggdrasil은 다른 접근을 취합니다.

### 🛡️ 3-Tier 벡터 대체 전략 (Vector Replacement)
순수 로컬 시스템에서 다음 3계층의 필터링을 통해 검색 효율성을 높입니다.

1. **L1 구조적 필터링 (YAML Frontmatter)**: `python-frontmatter`를 사용하여 문서의 메타데이터(`status`, `tags`, `type`)를 필터링합니다. 이를 통해 'SUPERSEDED' 상태의 문서가 검색에 포함되는 것을 방지합니다.
2. **L2 그래프 탐색 (NetworkX Topology)**: 문서 간의 `Sources` 속성을 NetworkX 그래프로 변환합니다. Louvain 커뮤니티 감지 알고리즘을 사용하여 연관된 토픽 클러스터를 식별합니다.
3. **L3 프로그래매틱 스캔 (PTC 기반 Full-text)**: Python 스크립트(PTC)가 검색된 후보 문서들을 로컬에서 직접 스캔합니다. 필요한 코드 스니펫이나 변수명 등의 결과만 추출하여 LLM에 반환함으로써 컨텍스트 윈도우의 토큰 사용량을 최소화합니다.

### 프로바이더 간 지식 교차 (Cross-Provider Pollination)

openyggdrasil은 특정 도구에 종속되지 않는 공용 지식 저장소로 작동합니다.

- **프로바이더 A(예: Cursor)가 씁니다:** 아키텍처를 결정하고 Vault에 기록합니다. (출처: `provider_id: cursor`)
- **프로바이더 B(예: Claude Code)가 읽고 갱신합니다:** 며칠 뒤 다른 에이전트가 켜지면, 앞선 에이전트가 쓴 문서를 검색해서 읽고 작업을 이어갑니다. 만약 결정이 변경되면 기존 지식을 `SUPERSEDED`(대체됨)로 밀어내고 새 지식을 씁니다.
- **다시 프로바이더 A가 인지합니다:** 다음에 처음 접속했던 에이전트가 들어오면, 자신이 과거에 썼던 낡은 지식이 아니라 다른 에이전트가 최신화해 둔 지식을 읽게 됩니다.

이것이 가능한 이유는 모든 에이전트가 자신만의 내부 트랜스크립트 포맷을 버리고, openyggdrasil의 **엄격한 프론트매터 스키마(Markdown + YAML)** 라는 단일 진실 원천(Vault) 규격을 공유하기 때문입니다.

## 핵심 철학

openyggdrasil은 파편화된 멀티-에이전트 환경에서 "기억의 마모"를 막기 위해 다음 4가지 핵심 철학을 융합했습니다.

### 1. 영속적 지식 베이스 (LLM Wiki)
Andrej Karpathy의 [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 인사이트에서 출발합니다. 매번 프롬프트(RAG)로 맥락을 주입하는 대신, "LLM이 스스로 영속적인 위키(SOT)를 구축하고 큐레이션하게" 합니다. 하지만 단순한 플랫(flat) 위키는 거시적 맥락을 탐색하기 어렵다는 한계가 있습니다.

### 2. 도메인 분리 = 대륙의 정의 (Continents & Terrain)
openyggdrasil에서 카테고리는 단순한 폴더가 아니라 **독립된 지식 도메인(대륙)**을 의미합니다. 지식이 섞이는 것을 막기 위해 철저한 역할 분담을 수행합니다.
- **Amundsen**은 새로 들어온 지식이 기존 도메인('알려진 대륙')에 속하는지, 완전히 새로운 도메인('신대륙')인지 판별하여 경계를 긋습니다.
- **Map Maker**는 해당 도메인 내에서 지식 간의 위상과 참조 좌표를 기획합니다.
- **Gardener**는 지식이 잘못된 도메인에 저장되지 않도록 분류 체계를 보호하며 물리적인 파일 식재(I/O)를 담당합니다.

### 3. 출처 추적과 진화의 계통수 (Tree Rings & Lineage)
최신 문서만 덮어쓰는 구조에서는 과거의 중요한 근원(Origin) 정보가 서서히 소실됩니다. *"시간은 선형으로 흐르지만, 맥락은 선형으로 진화하지 않기 때문입니다."* 이를 방지하기 위해 지식을 진화하는 **계통수(Evolution Tree)**로 취급합니다.
- **나이테(Ring) 각인:** 저장되는 모든 지식 블록에는 기원 정보(`provider_id`, `session_uid`, `timestamp`)가 데이터 모델 레벨에서 영구적으로 각인됩니다.
- 가장 기초가 되는 결정(Root/Trunk)은 보존되고, 폐기된 로직(Branch)은 물리적 삭제 대신 명시적으로 무효화(`SUPERSEDED`) 처리됩니다. 이를 통해 어떤 프로바이더가 접속하든 지식의 변경 이력을 완벽하게 역추적할 수 있습니다.

### 4. 구조적 관계망 (Graphify 연동)
Safi Shamsi의 [Graphify (v5)](https://github.com/safishamsi/graphify) 개념을 적용하여 마크다운 문서를 NetworkX 그래프 및 Louvain 커뮤니티로 변환합니다. 이를 통해 디렉토리가 달라도 의미적으로 연결된 지식을 탐색할 수 있습니다.

---

> *"위키는 소스를 추가할 때마다 더 풍부해집니다. 사람의 일은 소스를 큐레이션하고 좋은 질문을 하는 것입니다. LLM의 일은 나머지 전부입니다."* — Karpathy

openyggdrasil은 외부 Vector DB 없이 작동하는 순수 로컬 기반의 멀티-에이전트 메모리 시스템입니다.


### 추론 의사결정 재구조화 (9차 북극성)

> **[9차 로드맵 핵심 전환]** 추론 파이프라인의 중심축이 `effort` 기반 정규화에서
> **LLM-facing 어포던스 계약** 기반으로 전환되었으며, 오퍼레이터가 CQRS 분리된
> Producer/Consumer 세션에서 SKILL 어포던스 아래 PTC 도구를 자유롭게 조합합니다.

**기존 관점:** *"이 작업은 high effort인가 medium effort인가?"*
**새 관점:** *"이 판단은 누가, 어떤 역할로, 어떤 근거를 보고, 언제 멈춰야 하는가?"*

이 전환을 관통하는 3계층 원칙:

```
┌─────────────────────────────────────────────────────────────────┐
│  Schema validates    — JSON 스키마가 구조를 기계적으로 강제      │
│  Persona persuades   — 자연어 어포던스가 LLM의 판단을 설득       │
│  Runtime enforces    — Reject Hook이 시스템 안전 경계를 집행     │
└─────────────────────────────────────────────────────────────────┘
```

**어포던스 계약(Affordance Contract):**

각 PTC 도구와 추론 모듈은 JSON 시그니처 강제 대신, LLM이 스스로 판단할 수
있도록 자연어 어포던스 문구를 제공합니다:

| 어포던스 필드 | 역할 |
|---|---|
| `Use this when` | 도구/판단 사용 상황 |
| `Do NOT use this when` | 사용하면 안 되는 상황 |
| `If ambiguous` | 모호할 때의 기본 행동 |
| `Typed unavailable when` | 도구가 기능할 수 없는 조건 |
| `Hard nonclaims` | 이 도구/판단이 보증하지 않는 내용 |

**effort의 격하:** `effort`는 호환성 메타데이터로 격하되었으며,
추론 품질의 판단 근거는 페르소나 어포던스 계약이 담당합니다.

**Hard Nonclaims 모델:**
글로벌 규칙은 모든 패킷에 적용되고, 패킷 특수 규칙은 추가만 가능합니다. 글로벌 규칙을 완화하는 것은 불가능합니다.

### 브릿지 — Vault와 Graphify의 관계

이 시스템은 정적인 파일 스토리지(Vault)와 이를 연결하는 동적 관계망(Graphify)을 엄격하게 분리하여 관리합니다.

```text
┌────────────────────────────────────────┐
│  Graphify (파생 위상 계층 / 비SOT)     │ 
│  [수학적 노드] ──(관계망)── [클러스터] │  <-- 언제든 삭제 후 재생성 가능
└─────────────────▲──────────────────────┘
                  │ (실시간 추출 및 검증)
        [ skill_frontmatter_parser.py ] 
                  │
┌─────────────────▼──────────────────────┐
│  Vault (단일 진실 원천 / 영구 SOT)     │ 
│  ├── concepts/   (--- YAML ---)        │  <-- 절대 불변하는 마크다운 파일들
│  └── entities/   (--- YAML ---)        │
└────────────────────────────────────────┘
```

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
status: ACTIVE | SUPERSEDED
tags: [분류 태그]
sources: [출처 참조 또는 공개 소스 경로]
---
```

**코드베이스 구현 (Frontmatter Parser):**
`runtime/retrieval/skill_frontmatter_parser.py`를 통해 마크다운 파일의 YAML 프론트매터를 추출하고 JSON Schema로 검증합니다. Graphify와 Pathfinder는 이 데이터를 기반으로 동작합니다.

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
| "이 개념이 어디에 연결되지?" | NetworkX Louvain 커뮤니티 탐지로 토픽 군집 자동 탐지 |
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
  │  cluster   → NetworkX Louvain 커뮤니티 탐지                  │
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

## 시스템 아키텍처

### 양면 엔진 + CQRS 오퍼레이터 세션 루프 (9차 북극성)

이 철학을 바탕으로, openyggdrasil은 메모리를 포착하고 큐레이션하는 **생산면(Production Side)** 과 지식을 검색하고 전달하는 **소비면(Consumption Side)** 이라는 양면 엔진으로 작동합니다.

9차 북극성부터 백그라운드 실행 주체를 **오퍼레이터 세션(Operator Session)** 으로 명명합니다. "세션"이라는 용어는 이 주체가 명확한 시작/종료 수명과 프로바이더 세션과의 1:1 페어링 관계를 가짐을 강조합니다.
오퍼레이터 세션은 **CQRS(Command Query Responsibility Segregation)** 원칙에 따라 물리적으로 분리된 독립 백그라운드 프로세스에서 실행되며, 프로바이더 에이전트와는 오직 **Mailbox**를 통해서만 통신합니다.

```text
  [ Front-stage ]
  👤 사용자 ↔ 🤖 프로바이더 에이전트 (예: Hermes, Cursor)
                 │ 대화 중 의사결정 감지 (SKILL.md 참조)
                 │ save-intent / query-intent 발행
                 ▼
  ┌─────────────────────────────────────────────────────────┐
  │                    MAILBOX (JSONL)                       │
  │  (프로바이더 세션과 오퍼레이터 세션 간의 유일한 통신 채널)         │
  └────────────────┬───────────────────┬────────────────────┘
                   │  save-intent      │  query-intent
                   ▼                   ▼
  [ Back-stage ]   
  ┌───────────────────────────┐  ┌───────────────────────────┐
  │  Producer 오퍼레이터 세션    │  │  Consumer 오퍼레이터 세션    │
  │  (독립된 백그라운드 프로세스)│  │  (독립된 백그라운드 프로세스)│
  │                           │  │                           │
  │  PTC primitive를 조합하여  │  │  PTC primitive를 조합하여  │
  │  S-P-O 추출 및 Vault 적재  │  │  Vault 검색 및 번들 포매팅 │
  └───────────┬───────────────┘  └───────────┬───────────────┘
              │                              │
              ▼                              ▼
  ┌───────────────────────────┐  ┌───────────────────────────┐
  │     VAULT (SOT)           │  │  영수증 → Mailbox         │
  │  생산된 노드 및 위상 저장  │  │  → 프로바이더 에이전트 수신│
  └───────────────────────────┘  └───────────────────────────┘
```

**핵심 제약:** 오퍼레이터 세션(Producer/Consumer)은 프로바이더 세션과 물리적으로 다른 컨텍스트 윈도우(PID)에서 실행되며, 메모리를 공유하지 않습니다.
Mailbox(JSONL 파일시스템)만이 유일한 통신 채널입니다. (POC 30/30 PASS 검증 완료)

#### 세션 정의 (Session Definitions)

| 용어 | 정의 | 물리적 경계 |
|---|---|---|
| **프로바이더 세션** | 프로바이더 대화 윈도우의 PID | 유저가 Hermes를 3개 실행하면 → 독립적인 프로바이더 세션 3개 |
| **오퍼레이터 세션** | 프로바이더가 소환한 백그라운드 독립형 프로세스 | Producer와 Consumer는 각각 별도의 오퍼레이터 세션 (CQRS) |

**스케일링 모델:** 프로바이더 N개가 각각 오퍼레이터를 소환하면, 최대 **N×2** 개의 오퍼레이터 세션이 동시 존재합니다.

**시작 유형 구분:**

| 유형 | 의미 | 발생 시점 |
|---|---|---|
| **Cold Start (셋업)** | 최초 1회. SKILL.md 인식, 의존성 설치, Vault 초기화 | 레포 클론 직후 |
| **Session Start (초회 소환)** | 당일 프로바이더 워커가 SKILL을 통해 오퍼레이터를 처음 소환 | 프로바이더 세션 시작 시 |

**SKILL.md와 Mailbox의 역할 구분:**

| | SKILL.md | Mailbox |
|---|---|---|
| 성격 | **정적** 리마인더 | **동적** 상태 인지 채널 |
| 역할 | 오퍼레이터의 존재를 알려줌 | 오퍼레이터의 현재 상태를 전달 |
| 한계 | 최신 상태를 알 수 없음 | — |

SKILL만으로는 프로바이더가 "내 오퍼레이터가 살아있나? 뭘 처리했나?"를 알 수 없습니다.
프로바이더가 약결합된 오퍼레이터의 상태를 인지하는 **유일한 채널이 Mailbox**이므로,
**Mailbox의 위생 상태(Hygiene)가 전체 시스템의 건강을 결정합니다.**

### 생산면 — "무엇을 기억할 것인가"

생산 파이프라인은 모든 것을 맹목적으로 저장하지 않습니다. 프로바이더 신호를
타입이 지정된 의사결정 후보로 **증류(Distill)** 하고, 기억할 가치를
**평가(Evaluate)** 하며, 탐색 가능한 토픽 구조에 **배치(Place)** 하고,
생명주기 전환을 통해 낡은 지식을 **가지치기(Prune)** 합니다.

### 소비면 — "무엇을 전달할 것인가"

소비 파이프라인은 Vault 전체를 덤프하지 않습니다. **Pathfinder**가 설명
가능하고, 생명주기를 인식하며, **출처가 추적된 제한된 지원 번들(Provenance-tracked Bounded Support Bundle)**을 구축합니다.

단순한 지식 요약본이 아니라, 이 번들(`support_bundle.v1.schema.json` 계약) 내부에는 원본 맥락을 100% 복원할 수 있는 **3단계 출처 추적 장치**가 구조적으로 포함됩니다:
1. **Breadcrumb (`source_paths`)**: 지식이 추출된 원천 파일의 URI 배열.
2. **Topology ID (`episode_ids`, `claim_ids`)**: Vault/Graphify 내에서 해당 지식이 생성된 맥락적 위상 좌표.
3. **Evidence Refs (`safe_ref`)**: 필요 시 원시 대화 로그(Conversation Logs)나 터미널 실행 결과 원본으로 곧바로 찾아갈 수 있는 안전한 포인터.

결과적으로 에이전트는 요약본과 함께 "최초의 탄생 맥락으로 언제든 돌아갈 수 있는 명시적 주소"를 한 번에 제공받아, **Postman**을 통해 타입이 지정된 **Mailbox** 계약으로 안전하게 수신합니다.


## PTC (Programmatic Tool Calling) 개념과 아키텍처

openyggdrasil의 생산 및 소비 파이프라인은 **PTC (Programmatic Tool Calling)** 아키텍처를 기반으로 동작합니다. 

**원천 SOT (Source of Truth):**
이 아키텍처는 Anthropic의 [Programmatic Tool Calling](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/programmatic-tool-calling) (PTC) 기능과 개방형 에이전트 루프(REPL) 철학을 모티브로 삼고 있습니다.

### 원본 아키텍처 (Claude PTC)

```
  ┌──────────────────────────────────────────────────────────────┐
  │          Anthropic Programmatic Tool Calling (PTC)           │
  │                                                              │
  │  1. Agent: `server_tool_use` 발생 (name: code_execution)      │
  │  2. Sandbox: Python 스크립트 실행 시작                          │
  │  3. Script: 내부에서 `await target_tool()` 호출                 │
  │  4. API: Sandbox 일시정지, Host에 `tool_use` 발생             │
  │     (payload: `caller: { type: code_execution_... }`)        │
  │  5. Host: `tool_result` 반환                                 │
  │  6. Sandbox: 스크립트 실행 재개 및 중간 데이터 필터링/루프 처리 │
  │  7. Sandbox: `code_execution_tool_result` 반환                │
  └──────────────────────────────┬───────────────────────────────┘
                                 │ Contract: allowed_callers=["code_execution..."]
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                     Host (Client Tools)                      │
  │              (Database, File system, APIs 등)                │
  └──────────────────────────────────────────────────────────────┘
```

일반적인 PTC는 샌드박스 내부에서 에이전트가 자유롭게 Python 코드를 작성하여 여러 도구를 제어합니다:
1. 에이전트가 스스로 루프(Loop)와 조건문(If-else)을 포함한 임의의 Python 스크립트를 작성합니다.
2. 스크립트가 실행되며 여러 도구를 연속적으로 호출하고, 중간 데이터를 필터링하여 토큰과 지연 시간을 절약합니다.
3. 이 방식은 효율적이고 유연하지만, 지식을 정규화하고 엄격한 생명주기를 가진 메모리로 저장하기에는 에이전트가 작성한 스크립트의 로직 무결성에 의존해야 하므로 예측 가능성이 떨어지고 런타임 환각에 취약합니다.

### openyggdrasil의 변형 및 내재화 (Typed PTC Engine)

```
  ┌──────────────────────────────────────────────────────────────┐
  │               openyggdrasil (Typed PTC Engine)               │
  │                                                              │
  │  1. PTC Engine: `JSON Execution Plan` 강제 주입               │
  │     (예: ["distill_signal", "evaluate_candidate", ...])      │
  │  2. Agent: 도구 #1 호출 (엄격한 JSON Schema 준수 필요)         │
  │  3. Guardrail: 추론 토큰 소비 및 스키마 유효성 검사             │
  │  4. Utility: 도구 #2 이후는 결정론적 Python 함수 자동 통과     │
  │  5. Pipeline: `stop_reason` 발생 또는 체인 완료              │
  └──────────────────────────────┬───────────────────────────────┘
                                 │ Contract: Strict JSON Schema / Typed Payloads
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │                 openyggdrasil 8-Tool Chain                   │
  │           (결정론적, 타입 안정성, 생명주기가 관리됨)               │
  └──────────────────────────────────────────────────────────────┘
```

openyggdrasil은 이 원본 아키텍처의 자율성을 **타입 안정성이 보장된 체인(Typed Chain)** 으로 내재화했습니다.

1. **블랙박스 해체:** 내부 12-모듈이 보이지 않게 자동으로 도는 블랙박스 구조를 해체하고, 모든 모듈을 오퍼레이터 세션이 명시적으로 호출할 수 있는 "단일 목적 도구(Tool)"로 노출했습니다.
2. **PTC Primitive 조합:** 도구는 기계적 원시 연산(primitive)이되, 오퍼레이터 SKILL이 이 primitive들을 어떤 순서로 조합할지 결정합니다. 고정된 실행 순서를 강제하지 않습니다.
3. **이중 성격의 도구:** 도구를 '계약 가드레일'(추론 토큰 소비, 엄격한 스키마 검증)과 '작업 도구'(결정론적 Python 실행)로 분리하여 에이전트의 인지 부하를 최적화했습니다.

결과적으로, openyggdrasil의 PTC 모델은 기계적 도구를 primitive로 제공하고, 오퍼레이터 SKILL이 이를 조합하여 의미적 판단을 수행하는 구조로 설계되었습니다.

### PTC 도입 배경: 기존 Vector DB / ElasticSearch와의 차별점 (토큰 효율성)

전통적인 RAG(검색 증강 생성) 방식은 Vector DB나 ElasticSearch에 의존하여 대량의 문서를 검색하고, 수천~수만 개의 텍스트 토큰을 에이전트의 컨텍스트 윈도우에 그대로 욱여넣습니다. 이는 **비용이 비싸고, 지연 시간(Latency)이 길며, 핵심 정보를 놓치는 현상(Lost in the middle)을 유발**합니다.

openyggdrasil이 **순수 로컬 파일시스템 기반의 PTC 아키텍처**를 도입한 주된 이유는 **토큰 효율성과 데이터 필터링**을 위해서입니다:

- **중간 처리의 컨텍스트 배제:** 에이전트가 `scan_topology`나 `filter_lifecycle` 같은 Utility 도구를 호출할 때, 수많은 중간 데이터(예: 20개의 Vault 문서 스캔)는 에이전트의 컨텍스트 윈도우에 적재되지 않습니다. 오직 순수 Python 메모리 내에서만 처리(필터링, 집계)됩니다.
- **도구 호출 오버헤드 감소:** PTC를 통해 하나의 코드 블록 내에서 여러 문서를 읽고 처리함으로써 LLM 반복 호출을 줄이고 토큰 사용량을 절약합니다.
- **정제된 결과 반환:** 검색 중 발생하는 중간 데이터 대신 정제된 `support bundle`만 반환합니다.


## 실행 모델

openyggdrasil은 자체 LLM이나 API 키를 갖고 있지 않습니다.
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

**오퍼레이터 세션이 곧 파이프라인입니다.** 파이프라인 모듈 중 일부(작업 도구)는
순수 Python으로 결정론적 실행되지만, 핵심 판단(계약 가드레일)은 에이전트의
추론 토큰을 소비하여 동작합니다.

향후 독립적인 API 키 지정을 통해 프로바이더 없이 자체 실행하는 모드도
지원할 계획입니다.

---
## 운영 흐름 — 트리거에서 전달까지

위 다이어그램은 내부 체인을 보여주지만, 진짜 질문은:
**프로바이더가 이 시스템을 실제로 어떻게 호출하는가?**

두 가지 호출 경로가 있습니다 — 지식을 **기록**하는 경로(생산 트리거)와
지식을 **읽는** 경로(소비 트리거).


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

### 생산 트리거 — 프로바이더 에이전트의 맥락 인지와 의뢰 (1차 구조화)

프로바이더 에이전트(예: Hermes, Claude Code)는 사용자와 대화하며 **"이 아키텍처 결정이나 디버깅 맥락은 영구적인 지식(Wiki)으로 기록해야 한다"**는 니즈를 능동적으로 인지합니다. 

이때 프로바이더 에이전트는 무거운 전체 텍스트를 복사하여 넘기지 않습니다. 대신 `SKILL.md`를 참고하여 **어디를 읽으면 되는지 가리키는 원본 포인터(jsonl)와 얕은 요약본**으로 구성된 `Session Structure Signal`을 생성해 오퍼레이터 세션에게 의뢰를 주입합니다.

```text
  🤖 프로바이더 에이전트 (사용자와 직접 대화하는 Front-stage 주체)
       │
       │  ① 대화 중 기억할 맥락을 인지 (Wiki화 니즈 발생)
       │
       │  ② 레포 루트의 SKILL.md를 참고하여 진입점과 규칙 확인
       │
       │  ③ Session Structure Signal (얕은 의뢰서) 구성:
       │     {
       │       provider_id:         "hermes"
       │       provider_session_id: "session-2026-04-30-abc123"
       │       trigger_type:        "hard_trigger"
       │       surface_reason:      "게이트웨이 패턴 사용 결정 (얕은 요약)"
       │       turn_range:          { from: 12, to: 18 }
       │       source_ref:          { path_hint: "sessions/abc123.jsonl" } // ⭐️ 핵심: 원본 포인터
       │     }
       │
       │  ④ 메일박스에 Intent 발행 후 오퍼레이터 비동기 스폰 (Fire-and-Forget)
       │     → 프로바이더는 즉시 대화창으로 복귀 (Non-blocking)
       │
       ▼
  🌳 오퍼레이터 세션 (백그라운드에서 비동기로 Mailbox를 수신하고 동작하는 주체)
```

**핵심 규칙:**
- **포인터 기반 의뢰 (`source_ref` 필수):** 프로바이더 에이전트는 원본 대화를 훼손하거나 복제하지 않습니다. 반드시 `turn_delta.v1.jsonl` 등의 로그 파일 위치를 가리키는 `source_ref` 포인터를 넘겨야 합니다. 이를 누락한 신호는 Admission Gate에서 거부됩니다.
- **비동기 콜드스타트 (Non-blocking):** openyggdrasil은 프로바이더를 멈추지 않습니다. 메일박스(어포던스)를 통한 비동기 위임 후 백그라운드에서 조용히 실행되며, 시스템을 점유하는 영구 데몬 없이 작업이 끝나면 영수증을 남기고 종료됩니다.
- **추론 자원 임대 (Reasoning Lease):** 오퍼레이터가 백그라운드에서 심층 구조화(Distill/Evaluate)를 수행하려면 지능이 필요합니다. 프로바이더는 스폰 시점에 **자신의 API 키(인증 권한)를 넘겨주거나**, 백그라운드 프로세스가 내뿜는 프롬프트를 **비동기로 다중화(Multiplexing)하여 대신 처리**함으로써 자신의 추론 자원을 반드시 빌려주어야(Lease) 합니다.



### 생산 파이프라인 — 역할 가변 추론 임대 실행체 (목표 설계: Target Architecture)

> **[⚠️ 미완성/설계 상태]** 현재 런타임 코드는 `thin_worker_chain.py` 기반의 결정론적(Deterministic) 파이프라인으로 작동하고 있습니다. 아래 설명된 오퍼레이터 세션이 SKILL 어포던스 아래에서 PTC primitive를 자유롭게 조합하는 구조는 9차 로드맵의 **목표 아키텍처**입니다. POC 30/30 PASS 검증 완료.

캡처 신호가 시스템에 들어오면, 이를 단순히 자동화된 블랙박스에 넘기지 않습니다. 이 과정은 프로바이더 세션과 오퍼레이터 세션의 명확한 역할 분담을 통해 이루어집니다:

1. **초기 맥락 인지 (프로바이더 에이전트):** 프로바이더 에이전트가 `SKILL.md`를 참고하여 대화 중 기억해야 할 맥락을 인지하고, `surface_reason`과 `source_ref`가 포함된 초기 신호(Session Structure Signal)를 구성해 OpenYggdrasil 런타임에 주입합니다.
2. **심층 구조화 (오퍼레이터 세션):** 런타임은 이 의뢰를 받아 프로바이더의 추론 자원(Reasoning Lease)을 빌려 오퍼레이터 세션을 스폰합니다. 오퍼레이터 세션은 고정된 파이프라인이나 단일 모듈이 아닌, **부여된 작업 계약(Task Contract)에 따라 역할을 바꾸는 다면기(Role-Polymorphic Leased Executor)**입니다.

오퍼레이터 세션은 PTC(Programmatic Tool Calling) 본질에 맞게, 부여된 생산 역할(Distiller, Evaluator, Amundsen, Gardener 등)을 수행하기 위해 **필요한 코드를 직접 작성하여 허용된 OpenYggdrasil의 도구를 호출**합니다. (8개 도구를 기계적으로 순차 호출하는 것이 아닙니다.)

이 체인을 구성하는 OpenYggdrasil의 생산/기록 도구들은 두 가지 성격으로 나뉩니다:

- **계약 가드레일 (추론 요구):** 오퍼레이터 세션의 추론 토큰을 소비하여 심층 의사결정(증류, 가치 평가, 분류 등)을 수행하도록 유도하되, 출력 형태를 엄격히 제약합니다.
- **작업 도구 (추론 불필요):** 오퍼레이터 세션이 가드레일을 통과한 결과물을 정규화, 기록, 포장할 수 있게 돕는 순수 Python 유틸리티입니다.

```text
  Session Structure Signal (프로바이더 에이전트가 맥락을 인지하여 주입)
       │
       ▼
  🌳 PTC 오퍼레이터 세션 (지식 생산/기록을 담당하는 역할 가변 백그라운드 주체)
       │
       │  ① OpenYggdrasil이 Task Contract (Distiller/Amundsen/Gardener 등) 부여
       │  ② 오퍼레이터 세션이 부여된 역할에 맞춰 코드를 작성하여 생산 도구 호출
       │
       ▼
  ┌─ PTC Engine (실행 환경) — Allowlisted 도구 풀 ──────────────────┐
  │                                                              │
  │  [계약 가드레일 — 오퍼레이터 세션의 자체 추론을 유도 및 제약]          │
  │                                                              │
  │  ┌─ distill_signal (가드레일 — 어포던스 계약 참조) ─────────┐   │
  │  │  얕은 초기 신호를 깊이 있는 의사결정 후보로 심층 증류    │   │
  │  │  역할: 가드레일 (추론 토큰 소비)                       │   │
  │  └─────────────────────────────────────────────────────────┘   │
  │                      ▼                                   │
  │  ┌─ evaluate_candidate (가드레일) ───────────────────┐    │
  │  │  승격 가치 평가, 중복 제거, 임계값 게이트            │    │
  │  │  역할: 가드레일 (추론 토큰 소비)                       │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ classify_novelty (가드레일) ─────────────────────┐    │
  │  │  카테고리 & 신대륙(새로움) 분류                      │    │
  │  │  역할: 가드레일 (추론 토큰 소비)                       │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  [작업 도구 — 반죽·굽기·포장을 돕는 Python 유틸리티]       │
  │                                                          │
  │  ┌─ stamp_provenance (유틸리티) ─────────────────────┐    │
  │  │  나이테(출처 고리) 부착: source_ref, origin_locator  │    │
  │  │  역할: 유틸리티 (결정론적 Python)                    │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ compose_seed (유틸리티) ─────────────────────────┐    │
  │  │  상류 산출물 → 최종 각인 씨앗(Seed) 조합            │    │
  │  │  역할: 유틸리티 (결정론적 Python)                    │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ plant_to_vault (유틸리티) ───────────────────────┐    │
  │  │  Vault에 물리적 식재, 생명주기 전환                  │    │
  │  │  역할: 유틸리티 (결정론적 Python)                    │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ update_topology (유틸리티) ──────────────────────┐    │
  │  │  대륙/토픽/에피소드 위상 갱신                        │    │
  │  │  역할: 유틸리티 (결정론적 Python)                    │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ deliver_receipt (유틸리티) ──────────────────────┐    │
  │  │  Mailbox 수신증 발행                               │    │
  │  │  역할: 유틸리티 (결정론적 Python)                    │    │
  │  └──────────────────────────────────────────────────┘    │
  └──────────────────────────────────────────────────────────┘
       │
       ▼
  오퍼레이터 세션이 수신증(Receipt)을 Mailbox에 남기고 종료 (생산 및 기록 완료)
```

### PTC 실행 계획 — 기본 전략 예시 (캡처)

아래 JSON Tool Plan은 생산면의 **기본 전략 예시**입니다. `←distill` 같은 데이터 의존성은
자연스럽지만, SKILL은 상황에 따라 단계를 생략하거나 순서를 변경할 수 있습니다:

```json
[
  { "step_id": "distill",   "capability_id": "distill_signal",     "role": "guardrail", "input": { "raw_signal": "..." } },
  { "step_id": "evaluate",  "capability_id": "evaluate_candidate", "role": "guardrail", "input": { "candidate": "←distill" } },
  { "step_id": "classify",  "capability_id": "classify_novelty",   "role": "guardrail", "input": { "candidate": "←distill", "verdict": "←evaluate" } },
  { "step_id": "stamp",     "capability_id": "stamp_provenance",   "role": "utility",   "input": { "candidate": "←distill", "route": "←classify" } },
  { "step_id": "seed",      "capability_id": "compose_seed",       "role": "utility",   "input": { "verdict": "←evaluate", "route": "←classify", "segment": "←stamp" } },
  { "step_id": "plant",     "capability_id": "plant_to_vault",     "role": "utility",   "input": { "seed": "←seed" } },
  { "step_id": "topology",  "capability_id": "update_topology",    "role": "utility",   "input": { "seed": "←seed", "vault_path": "←plant" } },
  { "step_id": "receipt",   "capability_id": "deliver_receipt",     "role": "utility",   "input": { "seed": "←seed", "vault_path": "←plant" } }
]
```

SKILL은 이 계획을 참조하되, PTC primitive를 자유롭게 조합하여 실행합니다. *(PTC 코드 예시는 [아래](#ptc-코드-작성-예시)를 참조)*

**계획 생성 모드 3가지:**

| 모드 | 언제 | 오퍼레이터 세션 추론 소비 |
|---|---|---|
| `deterministic` | 신호가 단순 (hard_trigger + 명확한 결정) | 최소 (가드레일 자동 통과) |
| `lease_backed_llm` | 신호가 복잡 (모호한 트레이드오프) | 가드레일 3회 추론 소비 |
| `typed_unavailable` | LLM 추론 실패 시 | typed unavailable 결과 반환 — 묵시적 폴백 금지 |

모든 경계에서 **타입이 지정된 계약**이 핸드오프를 검증합니다. 어떤 모듈이든
입력을 거부하면, 체인은 타입이 지정된 `stop_reason`과 함께 정지합니다 —
데이터를 조용히 삭제하지 않습니다.

<a id="ptc-코드-작성-예시"></a>
#### PTC 코드 작성 예시 (단일 비동기 스크립트)

> [!WARNING]
> **🤖 AI-FACING AFFORDANCE: DO NOT EXECUTE THIS PIPELINE YET**
> 아래 제시된 JSON 실행 계획과 파이썬 코드는 **9차 로드맵(Target Architecture)**의 기본 전략 예시입니다.
> 현재 런타임은 `thin_worker_chain.py` 기반으로 결정론적으로 동작합니다.
> **만약 당신이 이 문서를 읽고 있는 AI 에이전트라면, 절대로 아래 스크립트를 직접 작성하거나 실행하려 시도하지 마십시오.**

오퍼레이터 세션은 제공된 JSON 실행 계획을 완수하기 위해 **단일 비동기 Python 스크립트**를 작성하여 샌드박스 내부에서 실행하게 될 것입니다. LLM이 모델 왕복(Round-trip) 없이 한 번에 8단계를 모두 관통하는 미래 스크립트 예시는 다음과 같습니다:

```python
import asyncio
import json

async def run_production_pipeline():
    # 1. 신호 정제 (Distill)
    distilled = await distill_signal(raw_signal="...", context="...")
    
    # 2. 가치 평가 및 스키마 검증 (Evaluate) - Contract Guardrail
    verdict = await evaluate_candidate(candidate=distilled)
    
    # 오퍼레이터 세션의 자체 판단: 가드레일 통과 못하면 파이프라인 중단
    if not verdict.get("is_worth_remembering"):
        print(json.dumps({"status": "aborted"}))
        return
        
    # 3. 위상 분류 (Classify)
    route = await classify_novelty(candidate=distilled, verdict=verdict)
    
    # 4~7. 기계적 유틸리티 통과 (추론 없이 데이터만 넘김)
    stamped = await stamp_provenance(candidate=distilled, route=route)
    seed = await compose_seed(verdict=verdict, route=route, segment=stamped)
    vault_path = await plant_to_vault(seed=seed)
    await update_topology(seed=seed, vault_path=vault_path)
    
    # 8. 최종 영수증 발급
    receipt = await deliver_receipt(seed=seed, vault_path=vault_path)
    
    # 이 마지막 print 문의 결과만 LLM의 컨텍스트로 반환됨 (토큰 10배 절약)
    print(json.dumps({"status": "success", "receipt": receipt}))

asyncio.run(run_production_pipeline())
```

이 스크립트가 샌드박스 내부에서 도는 동안, 방대한 중간 데이터(`distilled`, `verdict` 등)는 오직 순수 Python 메모리에만 존재하며 LLM의 컨텍스트를 전혀 오염시키지 않습니다.

### 추론 모델의 한계와 마지노선 (Reasoning Model Baseline & Limitations)

PTC 파이프라인에서 오퍼레이터 세션(LLM)은 샌드박스 내에서 복잡한 `JSON Execution Plan`을 기억하고, 8단계의 도구를 순서대로 호출하며, 각 도구의 엄격한 JSON 스키마 제약을 오차 없이 통과해야 합니다. 이를 강제하는 것이 openyggdrasil의 **계약 가드레일(Contract Guardrails)**입니다.

이러한 고도의 제약 환경을 완주하기 위한 **추론 모델의 마지노선(Baseline)은 Claude 3.5 Sonnet 또는 GPT-4o 등급의 프론티어 모델**입니다. 

**성능 미달 모델의 전형적인 실패(LLM Failure) 사례:**
- **Execution Plan 무시:** 강제된 도구 호출 순서를 무시하고 임의의 스크립트를 작성하여 샌드박스를 우회하려 시도.
- **가드레일 검증 실패:** 엄격한 JSON 스키마를 준수하지 못해 `evaluate` 도구에서 에러를 반환받았을 때, 스스로 코드를 수정하지 못하고 에러 루프에 빠져 타임아웃(Lease Failed) 발생.
- **환각 및 단계 건너뛰기:** 데이터 처리 단계를 임의로 스킵하고, 환각(Hallucination)에 기반한 결과물로 파이프라인을 종료하려 시도.

openyggdrasil은 모델의 선의나 자율성에 기대지 않습니다. 모델이 프롬프트를 무시하고 돌발 행동을 하더라도, 메인 시스템(Vault)은 샌드박스와 타입 검증에 의해 100% 보호받습니다. 위 마지노선을 충족하지 못하는 모델은 사전에 즉각적으로 걸러지며, 프로바이더 영수증(`hermes_routing_receipt`)에 `production_readiness_claimed` 마크를 획득할 수 없습니다.

---

### 소비 트리거 — 프로바이더가 과거 지식을 검색하는 방법

프로바이더 세션이 과거 의사결정의 맥락이 필요할 때 — "게이트웨이 패턴에 대해
뭘 결정했었지?" — 프로바이더의 에이전트가 **openyggdrasil의 오퍼레이터 세션을
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
       │  ④ openyggdrasil이 Pathfinder를 콜드스타트
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

### 소비 파이프라인 — 오퍼레이터 세션이 Vault를 검색하는 과정

여기서 핵심을 이해해야 합니다: **Consumer 오퍼레이터 세션 = Pathfinder입니다.**
별도의 검색 시스템이 존재하는 게 아닙니다. 프로바이더가 빌려준 오퍼레이터 세션이
자기 추론 토큰으로 Python 스크립트를 실행하고, 그 결과를 자기가 가져갑니다.

```
  Consumer 오퍼레이터 세션 (프로바이더가 빌려준 LLM)
       │
       │  ① SKILL.md에서 검색 진입점 확인
       │
       │  ② PTC 엔진에 질의 전달
       │     → PTC가 질의를 분석하여 실행 계획(JSON Tool Plan) 생성
       │
       │  ③ 오퍼레이터 세션이 PTC 계획에 따라 도구를 순서대로 호출
       │     (오퍼레이터 세션의 추론 토큰으로 실행)
       │
       ▼
  ┌─ PTC Engine ─────────────────────────────────────────────┐
  │                                                          │
  │  PTC는 오퍼레이터 세션에게 9개의 도구(capability)를 제공:    │
  │                                                          │
  │  ┌─ qmd_search ─────────────────────────────────────┐    │
  │  │  BM25 키워드 검색으로 vault 후보 추림              │    │
  │  └──────────────────────────────────────────────────┘    │
  │                      ▼                                   │
  │  ┌─ locate_region ──────────────────────────────────┐    │
  │  │  검색 결과에서 대륙/지역 식별                       │    │
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
  오퍼레이터 세션이 결과를 받아 프로바이더 세션으로 복귀
```

### PTC 실행 계획 — 오퍼레이터 세션이 받는 것

PTC 엔진은 오퍼레이터 세션에게 JSON Tool Plan을 제공합니다. 오퍼레이터 세션은
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

| 모드 | 언제 | 오퍼레이터 세션 추론 소비 |
|---|---|---|
| `deterministic` | 질의 신호만으로 계획 결정 가능 | 없음 (순수 Python) |
| `lease_backed_llm` | Reasoning Lease로 LLM이 계획 생성 | 오퍼레이터 세션 토큰 소비 |
| `typed_unavailable` | LLM 추론 실패 시 | typed unavailable 결과 반환 — 묵시적 폴백 금지 |

### 오퍼레이터 세션 시점의 전체 검색 여정

```
  프로바이더 에이전트
  "게이트웨이 패턴에 대해 뭘 결정했었지?"
       │
       ▼
  Consumer 오퍼레이터 세션 스폰 (프로바이더의 추론 토큰 차용)
       │
       │  ① SKILL.md 읽기 → 검색 진입점 확인
       │  ② Provider Capability 선언 (자기 모델 추론 능력)
       │  ③ 어포던스 계약 확인 (도구별 Use/Do NOT use 조건)
       │
       ▼
  PTC 엔진에 질의 전달
       │
       │  ④ 질의 분석 → 실행 계획(JSON Tool Plan) 생성
       │  ⑤ 3계층 검색 파이프라인 실행 (도구 9개)
       │
       │     [1계층 — QMD BM25 키워드 검색]
       │     qmd_search → vault 전체에서 BM25 후보 추림 (밀리초)
       │
       │     [2계층 — 구조적 위상 탐색]
       │     locate_region → 후보에서 대륙/지역 식별
       │     select_topic_anchor → 지역 내 토픽 앵커 선택
       │        ↑ Graphify 힌트: graph.json에서 관련 노드/클러스터 참조
       │
       │     [3계층 — 출처 추적 번들 조립]
       │     read_origin_claims → read_recent_claims
       │     → collect_claim_ids → read_source_paths
       │        ↑ Semantic Edge: supports/supersedes/contradicts 관계 확장
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
  오퍼레이터 세션이 결과를 갖고 프로바이더 세션으로 복귀
  → 프로바이더는 출처와 생명주기가 증명된 맥락을 받음
```

소비면은 **절대 맥락을 조작하지 않습니다.** Vault가 비어있으면 Pathfinder는
정직하게 `anchor_type: "none"` 결과를 리턴합니다. 출처를 검증할 수 없으면
`origin_shortcut_missing`으로 정지합니다. 오퍼레이터 세션은 항상 자신이 무엇을
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

## Reasoning Lease

일부 복잡한 신호나 모호한 트레이드오프는 단순한 PTC 도구 호출을 넘어섭니다 —
시간 예산과 격리 보장이 있는 확장된 LLM 추론이 필요합니다.

openyggdrasil은 이를 **Reasoning Lease** 계층으로 처리합니다. PTC 엔진의
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
실행되어, 오퍼레이터 세션의 복잡한 자율 루프가 메인 시스템을 오염시키지 않도록
안전하게 격리합니다.

---

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
└── vault/              # 정규 프로젝트 메모리
```

---

## 영감 & 감사

openyggdrasil은 다음 오픈소스 프로젝트들의 아이디어 위에 서 있습니다.

### [Andrej Karpathy의 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

openyggdrasil의 가장 근본적인 영감입니다. "매번 RAG로 컨텍스트를 주입하는
대신, LLM이 스스로 영속적인 위키를 구축하고 큐레이션하게 하라"는 인사이트가
Vault SOT 아키텍처의 토대입니다:

| LLM Wiki 개념 | openyggdrasil 흡수 |
|---|---|
| 마크다운 기반 영속 위키 | → Vault (YAML 프론트매터 + 생명주기 상태) |
| `index.md` / `log.md` 카탈로그 | → `vault/index.md` / `vault/log.md` |
| 소스 큐레이션 → LLM이 나머지 | → 생산 파이프라인 (Signal → Distill → Evaluate → Plant) |
| 점진적 지식 축적 | → Cross-Provider Pollination |

### [Graphify](https://github.com/safishamsi/graphify) (v5)

Graphify는 구조 분석 계층을 제공합니다 — 코드베이스와 지식을
탐색 가능한 그래프로 변환:

| Graphify 개념 | openyggdrasil 흡수 |
|---|---|
| `detect → extract → build_graph → cluster → analyze → report → export` 파이프라인 | → `common/graphify/` 파생 뷰 엔진 |
| NetworkX Louvain 커뮤니티 탐지 | → Map Maker를 위한 토픽/커뮤니티 구조 |
| 신뢰도 라벨 (EXTRACTED / INFERRED / AMBIGUOUS) | → 검색 결과의 출처 신뢰도 |
| 순수 Python, 로컬, 오프라인 | → **외부 인프라 의존성 없음** |

### [QMD](https://github.com/nicobailey/qmd)

QMD는 on-device 마크다운 검색엔진입니다. openyggdrasil은 QMD의 BM25
(SQLite FTS5) 키워드 검색만을 PTC 도구로 사용합니다:

| QMD 개념 | openyggdrasil 흡수 |
|---|---|
| SQLite FTS5 기반 BM25 검색 | → `qmd_search` PTC 도구 (소비면 1단계) |
| CLI: `qmd search "query" --json` | → `subprocess` 래퍼로 PTC 핸들러 구현 |
| 밀리초 단위 응답 | → `select_topic_anchor` 전 후보 추림으로 토큰 절감 |
| 벡터/리랭킹 기능 | → **사용하지 않음** (BM25만 사용) |

### [Language Server Protocol](https://github.com/microsoft/language-server-protocol) (LSP)

Microsoft의 LSP는 에디터와 언어 서버 사이의 표준 통신 프로토콜입니다.
openyggdrasil은 LSP를 직접 사용하지 않지만, 그 **capability negotiation
패턴**을 PTC 어포던스 설계의 참조 아키텍처로 채택했습니다:

| LSP 패턴 | openyggdrasil 적용 |
|---|---|
| `ServerCapabilities` — "나는 이걸 할 수 있다" 선언 | → PTC `Capability` + 어포던스 문구 |
| Progressive Enhancement — 필수만 구현, 나머지 선택 | → `typed_unavailable` 안전 거부 |
| M×N → M+N — 공통 프로토콜로 조합 폭발 해소 | → 프로바이더×도구를 공통 계약으로 통합 |

---

## 설계 원칙

1. **메모리는 엔진이지, 텍스트 더미가 아닙니다.** 모든 메모리 조각에는 출처,
   생명주기 상태, 타입 계약이 있습니다.

2. **기계적 기반, 필수적 추론.** 파이프라인의 구조적 뼈대(스키마 검증, AST 추출,
   위상 클러스터링)는 결정론적으로 작동하지만, 의미 있는 지식 생산(Distill,
   Semantic Edge)에는 Reasoning Lease를 통한 LLM 추론이 필수입니다.

3. **기본적으로 프로바이더 중립.** 어떤 프로바이더도 Vault에 특별한 접근권을
   갖지 않습니다. Hermes, Codex, Claude Code, 미래의 프로바이더가 동일한
   계약을 공유합니다.

4. **외부 인프라 없음.** 순수 Python, 그래프에는 NetworkX, 저장에는 파일시스템.
   기본 파이프라인에 데이터베이스, 벡터 스토어, Docker 불필요.

5. **Fail-closed, not fail-open.** 증거가 없으면 시스템은 타입이 지정된
   불가용성을 보고합니다 — 절대 준비 상태를 조작하지 않습니다.

6. **파생 뷰는 절대 진실 원천이 아닙니다.** Graphify 인덱스, 그래프 뷰,
   위키 페이지는 파생 표면입니다. Vault만이 유일한 정규 표면입니다.

7. **Schema validates, Persona persuades, Runtime enforces.** 추론 품질은
   JSON 스키마 강제만으로 달성되지 않습니다. LLM에게 행위의 이유와 경계를
   자연어로 설득하고(Persona), 시스템이 안전 경계를 집행합니다(Runtime).



## 기여

기여를 환영합니다. 새 모듈 인터페이스를 제안하기 전에 기존 `contracts/`
스키마를 읽어주세요 — 타입 계약 경계가 프로젝트에서 가장 중요한
아키텍처 결정입니다.

## 라이선스 & 브랜드 가이드라인

이 프로젝트는 오픈소스이며 [Apache License 2.0](./LICENSE) 하에 배포됩니다.
이 라이선스 조건에 따라 코드를 자유롭게 사용, 수정, 배포할 수 있습니다.

**상표 & 브랜드 보호 (제6조):**
코드는 오픈소스이지만, 브랜드명 **"openyggdrasil"** 과 **"INTEGRITY2077"**,
그리고 관련 로고와 트레이드 드레스는 엄격히 보호됩니다. Apache 2.0
라이선스는 이러한 상표의 사용 권한을 명시적으로 **부여하지 않습니다**.

이 프로젝트를 포크하거나 수정된 버전을 배포하는 경우, 이름을 변경해야 하며
openyggdrasil 또는 INTEGRITY2077 브랜딩을 사용하여 해당 버전을 식별할 수 없습니다.

동반 의존성 고지는 [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)를 참조하세요.
