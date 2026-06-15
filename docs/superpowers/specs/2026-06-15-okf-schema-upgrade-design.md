# OKF v0.1 스키마 격상 설계

- **날짜**: 2026-06-15
- **상태**: 설계 승인 대기
- **브랜치**: `okf-schema-upgrade`
- **범위**: Approach A (필드 정합) — 내부 스키마를 OKF v0.1 스펙으로 격상

## 1. 배경·목적

lore-wiki 는 Claude Code 세션을 증류해 마크다운 지식 위키(entity/decision/how-to 페이지 +
`index.md` + `log.md`)로 쌓는다. 증류 규약은 코드가 아니라 출력 디렉토리의 `CLAUDE.md`(schema)에
prose 로 정의되며 쓰면서 공동 진화한다.

[Open Knowledge Format (OKF) v0.1](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/)
은 조직 지식을 공유하기 위한 오픈 스펙으로, **마크다운 + YAML frontmatter / 파일 경로 = 정체성 /
`index.md`·`log.md` / 링크 = 지식 그래프 / `type` 단일 필수 필드**를 핵심으로 한다. lore-wiki 의
현재 산출물은 이미 OKF 와 구조적으로 거의 동일하다.

**목적**: OKF 를 외부 상호운용 대상이 아니라 *잘 정의된 모델*로 삼아, 지금의 ad-hoc 스키마를
OKF 스펙에 맞춰 격상한다(②). 우리가 스키마의 주인이며, OKF 와 충돌하는 lore-wiki 고유 강점
(tight 한 `type` enum, 세션 provenance)은 "확장"으로 명시하고 유지한다. **외부 OKF 도구 호환을
검증·보장하지는 않는다.**

### 현황 사실 (설계 근거)

- 스키마 파일이 둘로 분기: 플러그인 시드 `templates/schema.CLAUDE.md` ↔ 실제 위키
  `<output_dir>/CLAUDE.md`. 후자는 시드에서 진화해 "나무위키식 구조형" 섹션이 추가됨.
- 실제 위키(`/Users/gglee/workspace/obsidian/지식위키`, Obsidian vault, wikilink on)에 **269개
  페이지**가 운영 중. 모두 `type`/`tags`/`created`/`updated`/`sessions[]` frontmatter 보유,
  `title`·`description` 만 없음.
- **모든 페이지가 `# ` H1 로 시작** → `title` 의 결정적 소스.
- 한 줄 요약이 이미 `index.md` 의 `- [[페이지]] — 요약` 에 존재 → `description` 의 결정적 소스.

## 2. 범위와 비목표

### 범위 (Approach A)

1. frontmatter 에 OKF 표준 필드 `title`·`description` 추가 (둘 다 필수).
2. `type` enum·`sessions[]` provenance 유지하되 "lore-wiki 확장"으로 명시.
3. 스키마 문서(시드 + 실제 위키)에 "OKF 계보" 단락 신설 — OKF 표준 필드와 lore-wiki 확장을 구분.
4. `description` 을 한 줄 요약의 단일 출처로, `index.md` 항목은 이를 반영(DRY).
5. 기존 269개 페이지를 결정적 백필 스크립트로 마이그레이션.

### 비목표 (YAGNI)

- OKF 식 중첩 디렉토리 구조(Approach B) — 위키가 더 커지면 재검토.
- 외부 OKF 도구(시각화 그래프 뷰·검색 인덱스) 호환 검증(Approach ①).
- `resource` 필드 도입 / `type` 자유 문자열 개방 / provenance → `resource` 매핑(Approach C).
- `select.py`·`commit_cursor.py` 변경 — 이들은 페이지 frontmatter 를 쓰지 않으므로 무관.

## 3. 목표 frontmatter 스키마

```yaml
---
type: entity                                          # entity|decision|how-to — lore-wiki 어휘. OKF "type 필수" 원칙 채택
title: ScreenPOP API                                  # 신규 (OKF 표준): 사람용 이름
description: 삼성 ScreenPOP NestJS+TypeORM 백엔드, flat 도메인 모듈   # 신규 (OKF 표준): 한 줄 요약 — index 단일 출처
tags: [samsung, screenpop, nestjs, backend]           # OKF 표준
created: 2026-06-01                                   # lore-wiki 확장 (최초 생성일)
updated: 2026-06-01                                   # lore-wiki 확장 (최종 수정일, 사람용)
timestamp: 2026-06-01                                 # 신규 (OKF 표준): 최종 수정 — updated 값 미러링(날짜형)
sessions:                                             # lore-wiki 확장 — OKF `resource` 보다 풍부한 provenance
  - { sessionId: "...", timestamp: "..." }
---
```

### 필드 결정

| 필드 | 분류 | 결정 |
|---|---|---|
| `type` | OKF 표준(필수) | enum `entity\|decision\|how-to` 유지. OKF 의 "type 필수" 원칙만 채택 |
| `title` | OKF 표준 | **신규·필수**. 사람용 이름. 페이지 H1 과 일치 |
| `description` | OKF 표준 | **신규·필수**. 한 줄 요약. `index.md` 항목의 정본 |
| `tags` | OKF 표준 | 유지 |
| `timestamp` | OKF 표준 | **신규**. 최종 수정 시각. `updated` 값을 미러링(날짜형, 무손실) |
| `updated` | lore-wiki 확장 | 유지(최종 수정일, 사람용). `timestamp` 와 값 동일·필드명만 다름 |
| `created` | lore-wiki 확장 | 유지(최초 생성일). OKF 엔 없으나 minimally-opinionated 라 허용 |
| `sessions[]` | lore-wiki 확장 | 유지. OKF `resource` 단일 링크보다 풍부한 세션 단위 provenance |

`title`·`description` 을 필수로 둔다 — OKF 는 `type` 만 필수지만, 우리는 더 엄격하게 가도 OKF 호환
(상위집합)이며 조회·index 품질에 핵심이다.

`timestamp` 는 **별도 필드로 추가**한다(개명 아님). OKF 도구가 표준 필드명 `timestamp` 를 그대로 읽을 수
있어 호환성이 오른다. 값은 `updated` 를 날짜형 그대로 미러링한다 — 없는 시·분·초를 만들지 않고 무손실·결정적.
`updated`(사람용)와 `timestamp`(OKF 표준)는 값이 같고 필드명만 다르며, 둘 다 유지한다.

## 4. 스키마 문서 격상

대상: `templates/schema.CLAUDE.md`(시드) + `<output_dir>/CLAUDE.md`(실제 위키).

- frontmatter 섹션을 §3 목표 스키마로 교체.
- **"## OKF 계보" 단락 신설**: 본 스키마가 OKF v0.1 기반임을 명시하고 필드를 두 갈래로 구분해
  표로 정리 — ① OKF 표준(`type`/`title`/`description`/`tags`/`timestamp`), ② lore-wiki 확장
  (`created`/`updated`/`sessions`, 단 `updated` 는 `timestamp` 와 값 동일). OKF 의 구조 원칙
  (파일 경로 = 정체성, `index.md`/`log.md`, 링크 = 그래프)이 우리 규약과 대응함을 한 단락으로 서술.
- 실제 위키 `CLAUDE.md` 의 진화분("문서 스타일 (나무위키식 구조형)" + "타입별 권장 구조")은
  **그대로 보존**하고 frontmatter 섹션만 교체.

## 5. `description` 단일 출처 (DRY)

- 현재 한 줄 요약은 `index.md` 에만 존재. 격상 후 **`description` 이 정본**.
- `index.md` 의 `- [[페이지]] — 요약` 의 "요약"은 해당 페이지 frontmatter 의 `description` 과 일치시킨다.
- `commands/lore-wiki.md` 의 증류 절차(2단계)에 반영: 페이지를 쓸 때 `title`·`description` 을 먼저
  정하고, `index.md` 항목은 그 `description` 문구를 사용.

## 6. 마이그레이션 스크립트

`scripts/migrate_okf_frontmatter.py` (stdlib only — 프로젝트 규약 준수, 결정적·idempotent).

### 인터페이스

```bash
python3 scripts/migrate_okf_frontmatter.py --config ~/.claude/lore-wiki/config.json [--dry-run]
```

- `--config` 로 `output_dir`·`wikilink` 를 읽는다(절대 경로 해석). `--dry-run` 은 변경 없이 계획만 출력.

### 동작

각 페이지(`*.md`, 단 `index.md`/`log.md`/`CLAUDE.md` 제외):

1. frontmatter 블록(첫 `---` … `---`)을 라인 기반으로 파싱(YAML 라이브러리 미사용).
2. 이미 `title`·`description`·`timestamp` 가 모두 있으면 **스킵**(idempotent).
3. `title` ← 본문 첫 H1(`# ...`)에서 `# ` 제거한 텍스트.
4. `description` ← `index.md` 에서 이 페이지를 가리키는 항목의 `— ` 뒤 요약.
   - wikilink on: `[[<basename>]]` 매칭. off: `](<상대경로>)` 매칭.
5. `timestamp` ← 기존 `updated` 값(날짜형 그대로 미러링).
6. 삽입: `title`·`description` 은 `type` 라인 아래에(YAML 특수문자 `:`·`"` 등 포함 시 큰따옴표
   인용·이스케이프), `timestamp` 는 `updated` 라인 아래에(날짜 스칼라라 인용 없음).
7. **폴백·플래그**: H1 부재 시 `title` ← 파일명 휴머나이즈(kebab→공백). `index.md` 에 항목 부재 시
   `description` 을 비워 두고 stderr 에 `FLAG` 로 보고. `updated` 부재 시 `timestamp` 생략.

### 출력·검증

- stdout: 처리/스킵/플래그 건수 요약. stderr: 플래그된 페이지 목록(`FLAG: ...`, 사람이 검토).
- 적용 후 `git diff` 로 269개 변경을 검토. 본문·기존 필드는 불변, frontmatter `title`·`description`·
  `timestamp` 삽입만 발생해야 함.

## 7. 변경 / 무변경 파일

### 변경

- `templates/schema.CLAUDE.md` — frontmatter 섹션 교체 + "OKF 계보" 단락 추가.
- `commands/lore-wiki.md` — 2단계 증류 지침에 `title`/`description`/`timestamp`·index DRY 반영.
- `scripts/migrate_okf_frontmatter.py` — **신규**.
- `tests/test_migrate_okf.py` — **신규**(아래 §8).
- `<output_dir>/CLAUDE.md` (실제 위키, repo 밖) — frontmatter 섹션 교체, 진화분 보존.
- `README.md` — (선택) 스키마가 OKF v0.1 기반임을 한 줄 명시.

### 무변경

- `scripts/select.py`·`scripts/commit_cursor.py` — 페이지 frontmatter 를 쓰지 않음. provenance 메타는
  manifest → LLM 경로 그대로.

## 8. 테스트

`tests/test_migrate_okf.py` (기존 `tests/test_select.py` 패턴 따름, stdlib `unittest`):

- 표준 페이지: H1 → `title`, index 요약 → `description` 정확 삽입.
- `timestamp`: `updated` 값 미러링·인용 없음(`updated` 아래 삽입). `updated` 부재 시 생략.
- idempotent: 두 번 실행 시 2회차는 변경 0(세 필드 모두 존재 시 스킵).
- 인용: `title`/`description` 에 `:`·따옴표 포함 시 유효 YAML 로 인용.
- 폴백: H1 부재 → 파일명 휴머나이즈. index 항목 부재 → description 공란 + 플래그.
- wikilink on/off 두 매칭 경로.
- `--dry-run`: 파일 불변.

## 9. 위험·롤백

- **위험**: 269개 일괄 frontmatter 수정. → `--dry-run` 선실행 + `git diff` 검토 + 실제 위키가 git
  vault 라 롤백 가능.
- **위험**: YAML 인용 누락으로 frontmatter 깨짐. → §8 인용 테스트로 차단, dry-run 으로 사전 확인.
- **순서**: 스키마 문서·명령 변경 → 마이그레이션 스크립트 + 테스트 → dry-run 검토 → 실제 백필 실행.
