# Engine Nonclaims — 14차 Axis 3 S2

engine.py (runtime/ptc/engine.py, ~10,000 lines)에 인라인 포함된
hard nonclaim 선언들을 이 문서로 격리. engine.py의 L115, L331, L379,
L410, L441-443, L491-493 등에 분산된 nonclaim 블록은 이 문서를
단일 진실 공급원(Single Source of Truth)으로 참조한다.

## 핵심 비주장

```text
- engine.py는 PTC 체인의 실행 엔진이지만, LLM 판단을 포함하지 않는다.
- 모든 nonclaim은 additive-only. 하위 패킷이 상위 nonclaim을 제거/약화할 수 없다.
- Schema validates. Persona persuades. Runtime enforces.
- engine.py의 토큰/effort/depth 토큰은 기계-대면 메타데이터이며,
  LLM 판단의 주요 입력으로 사용해서는 안 된다.
```

## 참조

engine.py 상단에 `# Nonclaims: see contracts/engine_nonclaims.md` 주석 추가.
