# Lore Wiki — 설계 스펙 (ingest)

- **날짜**: 2026-06-01
- **상태**: 설계 승인 대기 → 구현 플랜
- **원본 아이디어**: `obsidian/메모/2026-06-01 claude-세션-분석-툴-아이디어.md`
- **레퍼런스**: `obsidian/참고자료/2026-06-01 Karpathy LLM Wiki 개념.md`

---

## 1. 목표 / 범위

Claude Code 대화 세션(JSONL)을 raw source로 읽어, Karpathy의 LLM Wiki 모델대로 **지속 누적·갱신되는 지식저장소**를 마크다운 위키로 구축한다. 검색용 verbatim 아카이브가 아니라 **LLM으로 증류된 지식노트**(도메인 사실 · 결정/근거 · 해법/How-to)를 쌓는다.

**이번 스펙의 범위 = `ingest` 한 연산뿐.** `query`·`lint`는 별도 스펙으로 후속한다. 위키·세션 모두 로컬 전용(동기화/공유 안 함)이라 민감정보 마스킹은 불필요.

### 3-레이어 매핑 (Karpathy → 이 프로젝트)

| Karpathy 레이어 | 이 프로젝트 |
| --- | --- |
| Raw sources (불변, 읽기만) | Claude Code 세션 JSONL (`~/.claude/projects/**`) |
| The wiki (LLM 생성 md) | 출력 디렉토리의 entity/decision/how-to 페이지 + `index.md` + `log.md` |
| The schema | 출력 디렉토리의 `CLAUDE.md` (위키 규약 + ingest 규칙, prose) |

`/lore-wiki ingest`를 **출력 디렉토리에서** 실행하면 그곳 `CLAUDE.md`(schema)가 Claude Code에 자동 로드되어 LLM이 규약을 따른다. schema는 **무엇을 어떻게 쓰나**를, config는 **어디서 읽고 어디에 쓰나**를 정의한다(별개 레이어).

### 지식 종류 → 페이지 타입

| 지식 종류 | 페이지 타입 |
| --- | --- |
| 도메인 사실 | entity 페이지 |
| 결정/근거 | decision 페이지 |
| 해법/How-to | how-to 페이지 |

세그멘테이션 · dedup/병합 · 노이즈 필터 · 페이지 네이밍/링크 규약 · frontmatter 필드는 **schema(`CLAUDE.md`)에 위임**한다. 도구 코드/명령에 박지 않는다. 단, 첫 실행을 위해 **최소 시드 schema**를 스캐폴딩한다(아래 §6).

---

## 2. 핵심 결정 (브레인스토밍 확정)

| 항목 | 결정 | 이유 |
| --- | --- | --- |
| 범위 | `ingest`만 (query/lint 후속) | 메모 우선순위, 단일 플랜에 적정 |
| 배포 형태 | **Claude Code 플러그인** | 플러그인 디렉토리 고정 → 헬퍼 경로 안정 탐색 + 표준 설치/공유 |
| 헬퍼 언어 | **Python3 stdlib only** (외부 의존 0) | macOS·Linux 기본 탑재, JSON/stat/seek 모두 stdlib, py3.9+ 호환 |
| config | **JSON, 헬퍼가 직접 읽음** | 결정적 경계 유지(LLM 미개입), stdlib `json`으로 전 버전 작동, glob 리스트 native |
| schema CLAUDE.md | **최소 시드로 스캐폴딩** 후 co-development | 빈 파일이면 첫 ingest에 따를 규약이 0 → 일관성 붕괴. 시드에서 출발해 진화 |
| 파이프라인 흐름 | **세션별 유닛 루프** + 소형 세션 묶음(bin-packing) | 비용 통제·resumability, 컨텍스트 bound, dedup 타깃=기존 페이지 |
| 명령 호출 | `/lore-wiki` = `/lore-wiki ingest` | 인자 없으면 ingest 기본 |

---

## 3. 아키텍처

### 플러그인 레이아웃 (`lore-wiki/`)

```
lore-wiki/
├─ .claude-plugin/plugin.json     # 플러그인 매니페스트
├─ commands/lore-wiki.md          # /lore-wiki [ingest] 오케스트레이션 (LLM)
├─ scripts/
│  ├─ select.py                   # 결정적: 선별 · 증분추출 · 신호필터 · 유닛 bin-packing
│  └─ commit_cursor.py            # 결정적: cursor.json 갱신
├─ templates/
│  └─ schema.CLAUDE.md            # 스캐폴딩용 최소 시드 schema
├─ config.example.json            # config 템플릿 (개인 경로 없음)
├─ docs/superpowers/specs/        # 설계 스펙
└─ README.md
```

### 결정적 / LLM 경계 (핵심 철학)

- **결정적 (Python 헬퍼)**: 파일 나열 → stat 비교 → byteOffset seek → JSONL 파싱 → 신호 추출(노이즈 제거) → 유닛 bin-packing → cursor.json 갱신. config(JSON)를 직접 읽음. **LLM 미개입.**
- **LLM (Claude, 명령 내)**: 추출된 깨끗한 유닛을 증류 → `index.md`로 관련 기존 페이지 탐색 → **기존 페이지 병합**/신규 생성 → schema(`CLAUDE.md`) 규약 준수 → `log.md` append.

`select.py`/`commit_cursor.py`로 나눈 이유: 선별과 커서 커밋이 **증류 단계를 사이에 두고** 분리돼야 한다(추출 → [LLM 증류] → 커밋).

---

## 4. 컴포넌트 & 인터페이스

### 4.1 config (`~/.claude/lore-wiki/config.json`)

플러그인은 `config.example.json`만 동봉(개인 경로 미포함). 첫 실행 시 도구가 실 config를 작성.

```jsonc
{
  "session_root": "~/.claude/projects",          // 기본값
  "output_dir":   "/path/to/wiki",               // 필수, 첫 실행 시 입력받아 기록
  "include":      ["*"],                          // cwd 기준 glob, 기본 전체
  "exclude":      [],                             //   예: ["*/sandbox"]
  "cursor_path":  "~/.claude/lore-wiki/cursor.json", // 출력 dir 밖 (git 노이즈 회피)
  "obsidian":     false,                          // 독립 토글
  "wikilink":     false,                          // 독립 토글 (Obsidian on → 보통 wikilink on)
  "batch_max_bytes": 40000                        // 소형 세션 묶음 유닛 cap
}
```

- v1은 **config 1개 = 위키 1개**. 다중 위키는 `--config <경로>` 오버라이드 — 이때 각 config의 `cursor_path`도 **서로 다르게** 지정해야 충돌하지 않는다(기본 `cursor_path`는 단일 위키 전제).
- `include`/`exclude` 매칭 기준은 **세션 안의 `cwd`**(원본 프로젝트 경로). `~/.claude/projects/`의 디렉토리명은 `/`→`-` 치환형이라 역변환이 모호하므로 쓰지 않는다.

### 4.2 cursor.json (기계용 상태)

세션별 1엔트리 + 전역 `lastRun`. 출력 dir **밖**에 둔다(매 실행 변경 = git 노이즈 회피).

```jsonc
{
  "lastRun": "2026-06-01T12:00:00+09:00",
  "sessions": {
    "<sessionId>": {
      "mtime": 1717200000.0,   // 빠른 변화 감지
      "size": 373706,          //   (mtime+size 동일 → skip)
      "byteOffset": 373706,    // append-only 파일 O(1) 재개
      "lastUuid": "…",         // 재개 지점 검증 + offset fallback 앵커
      "lastTimestamp": "…"     // 진행 표시
    }
  }
}
```

### 4.3 `scripts/select.py` — 결정적: 선별 → 증분추출 → bin-packing

- **입력**: `--config <path>` (모든 설정 직접 읽음). 기본 경로 `~/.claude/lore-wiki/config.json`.
- **동작**:
  1. `session_root/**/*.jsonl` 전부 나열(하위 sidechain 포함).
  2. 각 파일 `stat` → cursor의 `(mtime, size)` 비교(§5 분기표).
  3. 신규/증가분만 `byteOffset` seek로 파싱.
  4. **신호만 추출**: user 프롬프트 · assistant `text` 블록 · `tool_use` 요약(Bash 명령/편집 대상). thinking · 토큰/비용/모델/캐시/도구분포 등 대시보드성 신호 **제거**.
  5. 세션의 `cwd` 기준 include/exclude glob 필터.
  6. 추출 크기로 **bin-packing**: 추출 크기 ≤ `batch_max_bytes`인 소형 세션들을 합산 cap 한도 내 한 유닛으로 묶음. cap 초과 세션은 단독 유닛.
- **출력**: `<run_dir>/manifest.json`(유닛 목록 + 세션별 커서 메타) + `<run_dir>/unit-NN.md`(증류용 깨끗한 텍스트, 유닛당 1파일). **stdout에 `run_dir` 경로** 출력.
- `run_dir`은 고정 경로(예: `~/.claude/lore-wiki/run/`)를 실행마다 초기화.

`manifest.json` 개략:
```jsonc
{
  "run_dir": "…",
  "scanned": 42, "skipped": 38,
  "units": [
    {
      "unit_id": 1, "file": "unit-01.md", "extracted_bytes": 3500,
      "sessions": [
        { "sessionId": "…", "path": "…/<id>.jsonl", "cwd": "…", "gitBranch": "…",
          "mtime": …, "size": …, "byteOffset": …, "lastUuid": "…", "lastTimestamp": "…" }
      ]
    }
  ]
}
```

### 4.4 `scripts/commit_cursor.py` — 결정적: 커서 갱신

- **입력**: `--config <path> --manifest <run_dir>/manifest.json --unit <N>`
- **동작**: 유닛 N에 속한 세션들의 cursor 엔트리(`mtime`/`size`/`byteOffset`/`lastUuid`/`lastTimestamp`) 갱신. **cursor.json만** 책임.
- 전역 `lastRun`은 **매 호출마다** 현재 시각으로 갱신(Python `datetime`). 별도 호출 불필요 — 마지막 유닛 커밋이 자연히 최신 `lastRun`을 남긴다.

### 4.5 `commands/lore-wiki.md` — 오케스트레이션 (LLM)

1. **서브커맨드 파싱**: 인자 없음 또는 `ingest` → ingest. (`query`/`lint`는 후속.)
2. **config 탐색**: 없으면 **첫 실행** — output_dir 입력받아 `config.json` 작성 + 출력 dir 스캐폴딩(`templates/schema.CLAUDE.md` → `<output_dir>/CLAUDE.md`, 빈 `index.md`·`log.md` 생성).
3. `select.py --config` 실행 → `run_dir` 획득. **유닛 0개면 "위키 최신" 보고 후 종료.**
4. **유닛 루프** (각 유닛):
   - `run_dir/unit-NN.md` Read.
   - **증류**: schema 규약대로 → `index.md`로 관련 기존 페이지 탐색 → **기존 페이지 병합** 또는 신규 생성(read-modify-write).
   - **`log.md` append**: provenance(manifest의 `sessionId`·`timestamp`) + 어느 페이지를 건드렸나. 일관된 prefix(예: `## [2026-06-01] ingest | …`).
   - `commit_cursor.py --unit N` 실행(cursor.json 갱신).
5. `run_dir` 정리 + 요약 보고.

**역할 분담 요지**: `log.md`(사람용·의미 정보 = 어느 세션 → 어느 페이지)는 **Claude 작성**, `cursor.json`(기계용 상태)은 **헬퍼 작성**.

---

## 5. 데이터 흐름 & 증분 엣지케이스

### 실행 흐름

```
/lore-wiki [ingest]   (출력 dir에서 실행 → 그곳 CLAUDE.md=schema 자동 로드)
  │
  ├─ config 탐색 ── 없음 ──▶ 첫 실행: output_dir 입력 → config 작성 → 스캐폴딩
  │
  ├─ select.py --config ───────────────────────────┐ (결정적)
  │    1. session_root/**/*.jsonl 나열               │
  │    2. stat vs cursor(mtime,size)                 │
  │    3. 증분 추출 + 신호 필터 + glob 필터          │
  │    4. 유닛 bin-packing                           │
  │    └▶ run_dir/{manifest.json, unit-NN.md} ───────┘
  │
  ├─ units==0 ──▶ "위키 최신" 보고 후 종료
  │
  └─ 유닛 루프:
       Read unit-NN.md
       → 증류: index.md 탐색 → 기존 페이지 병합 / 신규 생성    (LLM)
       → log.md append (provenance)                          (LLM)
       → commit_cursor.py --unit N                           (결정적)
     → run_dir 정리 → 요약 보고
```

### select.py stat 비교 분기

| cursor 상태 | 판정 | 동작 |
| --- | --- | --- |
| 엔트리 없음 | 신규 세션 | 처음부터 추출 |
| mtime·size 동일 | 변화 없음 | **skip** (파일 안 엶) |
| size 증가 | append | `byteOffset` seek → 증가분만 추출 |
| size 감소/불일치 | 재작성 의심 | 해당 파일 **전체 재스캔** + 커서 리셋 |

### 안전장치

- **offset 검증**: `byteOffset` seek 후 첫 파싱 라인의 `parentUuid`(또는 직전 라인 uuid)가 cursor의 `lastUuid`와 불일치 → offset 깨짐 → 그 파일 전체 재스캔 fallback.
- **스키마 관용성**: 파서는 모르는 `type`/필드에 관대(메모 2번: `ai-title`·`mode` 등 버전마다 늘어남). 알 수 없는 type skip, 깨진 JSON 라인도 skip하고 계속.

### 중단/재개 (resumability)

커서는 **유닛 커밋 시점**에만 전진. 유닛 도중(페이지 작성 전/중) 중단되면 그 유닛 세션들은 커서 미전진 → 다음 실행에 재추출 → 증류 단계의 **기존 페이지 병합 dedup**이 중복을 흡수. 즉 재실행 안전.

---

## 6. 시드 schema (`templates/schema.CLAUDE.md`)

스캐폴딩 시 출력 dir에 복사되는 **최소 골격**. 사용자가 쓰면서 고쳐나간다(co-development).

담을 최소 항목(주석과 함께):
- **페이지 타입 3종**: entity / decision / how-to — 각각의 목적과 1줄 정의.
- **네이밍 규약**: 파일명 컨벤션(예: kebab-case, 타입 접두 여부).
- **frontmatter 필드**: `type`, `tags`, `created`/`updated`, **provenance**(`sessions: [{sessionId, timestamp}]`).
- **index.md 포맷**: 카테고리(entities/decisions/how-tos)별, 페이지 링크 + 한 줄 요약.
- **log.md 포맷**: append-only, 일관 prefix `## [YYYY-MM-DD] ingest | …`.
- **링크 규약**: wikilink vs 표준 md 링크는 config 토글(`wikilink`)에 따름.
- **dedup/병합·세그멘테이션·노이즈 필터 지침**: "여기서 채워나가라"는 프레임 + 출발점 가이드.

---

## 7. 에러 처리 & 견고성

- **config 누락/필드 오류**: 첫 실행은 정상 플로우. 기존 config인데 `output_dir` 없거나 경로 부재 → 명확한 에러로 중단(파괴적 동작 금지).
- **session_root 부재/빈 디렉토리**: "ingest할 세션 없음"으로 정상 종료(에러 아님).
- **깨진 JSONL / 모르는 type**: skip하고 계속. select.py는 부분 실패해도 추출 가능한 유닛은 내보냄.
- **offset 깨짐 / size 감소**: §5 fallback(전체 재스캔 + 커서 리셋).
- **유닛 중간 중단**: §5 resumability(커서 미전진 → 재실행 안전).
- **run_dir 정리 실패**: 경고만, 다음 실행이 stale run_dir 덮어씀(고정 경로 + 실행마다 초기화).
- **출력 dir 쓰기**: 페이지 병합은 항상 read-modify-write. 덮어쓰기 전 read 우선.

---

## 8. 테스트 전략

### 결정적 헬퍼 (단위 테스트 대상)

`select.py`/`commit_cursor.py`는 순수 CLI-인자/파일 함수라 검증이 쉽다(컴포넌트 분리의 이유). fixture JSONL로:

- 신규 세션 / mtime·size 동일 skip / size 증가 append / size 감소 재스캔
- offset + lastUuid 불일치 fallback
- 모르는 type · 깨진 라인 관용 처리
- bin-packing: 소형 다수 묶음, cap 초과 단독, 경계값
- 신호 추출: thinking/토큰/비용 잡음 제거, user·assistant text·tool_use 보존
- cursor 갱신 round-trip(commit 후 재실행 시 skip 확인)
- include/exclude glob 필터(cwd 기준)

픽스처는 `참고자료/`의 실제 샘플 2개(작업형 209934bb · 대화형 08731532)에서 축약 발췌해 구성.

### LLM 증류 (수동 스모크)

자동 단위테스트 부적합. 실제 세션으로: 첫 실행 스캐폴딩 → 1유닛 ingest → 페이지/index/log/cursor 산출 육안 확인 → 재실행 시 dedup·skip 동작 확인.

---

## 9. 후속 (이번 스펙 범위 밖)

- `query`: 위키 검색 → 인용과 함께 답 합성 → 좋은 답 환류.
- `lint`: 모순/낡은 주장/고아 페이지/누락 상호참조/데이터 공백 점검.
- 자동화: 세션 종료 hook · 주기 배치(현재는 수동 `/lore-wiki` 호출).
- 세션↔커밋 연결: `cwd`/`gitBranch` + 시간 근접 매칭으로 "이 지식 → 이 커밋" 근거 링크.
- 초대형 단일 세션의 유닛 내 청킹(현재 v1은 단독 유닛으로 처리).
