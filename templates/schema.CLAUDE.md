# Lore Wiki Schema

> 이 파일은 위키의 **규약(schema)** 이다. `/lore-wiki ingest` 가 이 디렉토리에서 실행될 때
> 자동 로드되어 증류 규칙을 제공한다. **최소 시드** 상태이며, 쓰면서 본인 도메인에 맞게
> 자유롭게 고쳐나가라(co-development).

## 페이지 타입 (3종)

- **entity** — 도메인 사실. 시스템·API·개념·용어 등 "무엇"에 대한 지속적 사실.
  예: `wafl-console`, `screenpop-api`.
- **decision** — 결정과 근거. "왜 X 대신 Y 를 골랐나" + 검토한 대안.
- **how-to** — 해법/절차. "X 문제 → Y 절차로 해결".

## 네이밍

- 파일명: `kebab-case.md` (소문자, 공백→하이픈).
- 타입은 frontmatter `type` 으로 구분(접두사 불필요). 충돌 시 짧은 한정어 추가.

## frontmatter (필수 필드)

```yaml
---
type: entity        # entity | decision | how-to
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
sessions:           # provenance — 이 지식이 나온 세션
  - { sessionId: "...", timestamp: "..." }
---
```

## index.md

콘텐츠 카탈로그. 카테고리(Entities / Decisions / How-tos)별로:
- `- [[페이지]] — 한 줄 요약` (wikilink off 면 `- [한 줄 요약](상대경로.md)`).

## log.md

append-only 이력. 항목마다 일관 prefix:
```
## [YYYY-MM-DD] ingest | <요지>
- sessions: <sessionId> (<timestamp>)
- pages: [[페이지A]] 생성, [[페이지B]] 갱신
```

## 링크 규약

- config `wikilink: true` → `[[페이지]]`. `false` → 표준 상대경로 md 링크.
- 페이지 간 상호참조를 적극적으로 건다(관련 entity/decision/how-to).

## 증류 지침 (채워나갈 영역)

> 아래는 출발점 가이드. 본인 세션 패턴에 맞게 구체화하라.

- **세그멘테이션**: 한 세션에서 여러 지식 단위가 나올 수 있다. Q→A 흐름·주제 전환을 경계로 본다.
- **dedup/병합**: 같은 사실이 여러 세션에 나오면 기존 페이지에 병합. 중복 페이지 금지.
- **노이즈 필터**: 삽질·왕복·실패한 시도에서 *결과적으로 통한 지식*만 남긴다.
- **무엇을 남길까**: 도메인 사실·결정 근거·해법. 일회성 잡담·진행 로그는 제외.
