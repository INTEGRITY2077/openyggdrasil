# OpenYggdrasil

OpenYggdrasil은 여러 LLM 프로바이더가 같은 프로젝트 기억을 안전하게 이어서 사용할 수 있게 만드는 외부 기억 계층입니다.

이 프로젝트가 하려는 일은 단순합니다.

- 새 세션이 열려도 이전 의사결정과 맥락을 다시 찾을 수 있어야 한다
- 프로바이더별 세션 경계와 provenance는 무너지면 안 된다
- 기억은 프롬프트 감이나 벡터 유사도 추측이 아니라 명시적 계약과 정본 구조 위에 있어야 한다

## 핵심 목적

OpenYggdrasil은 프로바이더를 대체하지 않습니다.

- 프로바이더는 인증, 추론, 네이티브 세션, 도구 실행을 계속 책임진다
- OpenYggdrasil은 계약, 기억 구조, provenance, retrieval, session-bound delivery를 책임진다

즉 이 프로젝트는 또 하나의 채팅 앱이 아니라, 여러 프로바이더가 같은 기억 숲에 붙을 수 있게 만드는 공용 기억 런타임입니다.

```text
여러 프로바이더
-> 하나의 공유 기억 숲
-> 명시적 attachment 계약
-> bounded retrieval
-> 회수 가능한 과거 맥락
```

## 어떻게 동작하는가

1. 프로바이더는 현재 워크스페이스에 `.yggdrasil/` attachment artifact를 만든다.
2. OpenYggdrasil은 그 artifact를 읽어 현재 세션을 식별한다.
3. 가치 있는 결정과 지식만 `vault/`에 정본으로 승격한다.
4. 과거 맥락이 필요할 때는 mailbox와 retrieval chain을 통해 필요한 힌트와 support bundle만 다시 전달한다.

여기서 중요한 원칙은 두 가지입니다.

- raw session은 provider 쪽 경계를 유지한다
- durable knowledge만 canonical memory에 남긴다

## 무엇이 정본인가

- `vault/`
  - 장기적으로 남겨야 할 지식과 provenance의 정본
- `.yggdrasil/`
  - attachment, inbox, mailbox, queue, telemetry 같은 live runtime surface
- `contracts/`
  - attachment, inbox, retrieval, support delivery의 명시적 스키마
- `runtime/`
  - provider-neutral runtime implementation
- `providers/`
  - provider adapter와 provider-specific bootstrap 표면

## 무엇을 하지 않는가

OpenYggdrasil은 아래 방향을 지향하지 않습니다.

- 모든 live conversation을 한 세션으로 섞는 전역 세션 블렌더
- provider-specific proxy에 모든 걸 몰아넣는 구조
- vector-first memory
- 자유형 프롬프트 캐시
- provenance가 사라진 요약 저장소

## 현재 배포 관점

배포와 운영의 중심은 코어 런타임입니다.

- `contracts/`
- `runtime/`
- `vault/`
- `providers/`
- `projects/` 중 실제 파생 런타임에 필요한 부분

문서 작업용 `doc/`, 테스트 표면, 로컬 runtime state, generated provider output은 배포 정본이 아닙니다.

## 현재 릴리스 스모크

새 clone 기준 최소 릴리스 스모크는 코어 런타임 import, provider packaging/bootstrap baseline, runner fallback, Graphify derived snapshot/query guard, typed unavailable path, ignored runtime surface policy를 함께 확인합니다.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; py -3 -m pytest -p no:cacheprovider tests\test_runtime_import_smoke.py tests\test_hermes_provider_packaging_baseline.py tests\test_codex_provider_packaging_baseline.py tests\test_claude_code_provider_packaging_baseline.py tests\test_antigravity_provider_packaging_baseline.py tests\test_provider_packaging_known_limitations_matrix.py tests\test_graphify_snapshot_rebuild.py tests\test_graph_output_guard.py tests\test_graph_snapshot_replacement_guard.py tests\test_graph_query_support_bundle.py tests\test_hermes_foreground_unavailable_contract.py tests\test_hermes_background_unavailable_contract.py tests\test_no_credential_prompt_regression.py tests\test_provider_declined_visibility.py tests\test_dot_runtime_surface_policy.py
```

현재 릴리스 현실은 아래와 같습니다.

- Hermes live foreground는 아직 실제 live proof가 아니라 `hermes_foreground_unavailable_contract.v1` typed unavailable/fallback으로 노출된다.
- Graphify/Graphiti 및 graph/wiki/index 출력은 canonical SOT가 아니며, freshness/source-ref guard를 통과한 support hint로만 사용된다.
- Graphify snapshot output이 없으면 release blocker가 아니라 `graphify_snapshot_rebuild_result.v1` typed unavailable/non-SOT 상태로 처리된다.
- `.runtime/`, `.yggdrasil/`, `_tmp`는 generated local artifact이며 tracked release evidence가 아니다.
- `doc/`와 provider raw session output은 배포 정본이 아니다.

## 왜 중요한가

이 프로젝트가 해결하려는 문제는 “이전 세션이 있었는지”가 아니라 “새로운 세션이 이전 프로젝트 결정을 다시 회수할 수 있는지”입니다.

즉 OpenYggdrasil의 성공 조건은 아래입니다.

- 다른 프로바이더에서 남긴 결정과 지식을
- 새로운 세션이
- provenance를 잃지 않고
- bounded하게 다시 회수할 수 있다

이게 OpenYggdrasil이 진짜로 하려는 일입니다.

## 시작점

- skill/bootstrap entry: [SKILL.md](./SKILL.md)
- graph companion policy: [POLICY_GRAPHIFY_COMPANION.md](./POLICY_GRAPHIFY_COMPANION.md)
- third-party notice: [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)
