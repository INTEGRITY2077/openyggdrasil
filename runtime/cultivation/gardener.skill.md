---
name: gardener
description: >
  vault 내 stale/superseded/orphan 지식을 자율적으로 탐지하고
  정리 후보를 제안한다. Maintenance Chain에서 주기적 순찰 시 활성화.
  lint 3종(stale, superseded, orphan) 감지가 필요할 때 트리거.
chain_position: maintenance
effort_class: low
requires_reasoning: false
bundle_eligible: false
output_contract: gardener_lint_report.v1
---

# Gardener Module Skill

## 역할

vault에 축적된 지식의 신선도와 구조적 정합성을 유지한다.

## 활성화 조건

- 자율 순찰 주기 도달 (cron 또는 event trigger)
- vault에 새 지식이 적재된 후 일정 시간 경과
- 수동 요청: "stale 지식 점검"

## 실행 절차

1. vault 전체 또는 지정 구간의 지식 항목 스캔
2. lint 3종 감지:
   - **stale**: 마지막 갱신 이후 기준 기간 초과
   - **superseded**: 같은 주제에 더 최신 항목 존재
   - **orphan**: 참조하는 상위 항목이 삭제됨
3. 감지 결과를 `gardener_lint_report.v1` 형식으로 출력
4. soft-delete 후보를 Gardener routing에 전달

## 공유 컨텍스트

- vault/ 디렉토리 전체 (읽기 전용)
- graphify community index (있을 경우)

## 성공 조건

- lint 3종 각각에 대해 감지/미감지를 명시적으로 보고
- false positive rate 추적 가능한 형태로 출력
- 실행 후 vault에 대한 쓰기 작업 없음 (보고만)

## 실패 모드

- vault 접근 불가 시: typed_unavailable artifact 생성
- lint 기준 설정 누락 시: 기본값(30일/stale) 적용 + WARNING 로그
