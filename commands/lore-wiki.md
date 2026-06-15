---
name: lore-wiki
description: Claude Code 세션을 증류해 마크다운 지식 위키로 ingest 한다 (기본 서브커맨드 ingest)
disable-model-invocation: true
---

Claude Code 세션 JSONL 을 raw source 로 읽어 지식노트(entity/decision/how-to)로 증류·누적한다. 결정적 선별·증분추출은 플러그인 헬퍼(`scripts/select.py`, `scripts/commit_cursor.py`)가, 증류는 이 명령(LLM)이 담당한다.

## 호출 인터페이스

| 인자 | 의미 |
|---|---|
| (없음) | `ingest` 와 동일 (기본) |
| `ingest` | 새 세션 증분 ingest |

`query`·`lint` 는 후속 스펙. 현재는 ingest 만.

## 경로

- 헬퍼: `${CLAUDE_PLUGIN_ROOT}/scripts/select.py`, `${CLAUDE_PLUGIN_ROOT}/scripts/commit_cursor.py` (플러그인 번들 파일은 `${CLAUDE_PLUGIN_ROOT}` 로 참조)
- config: `~/.claude/lore-wiki/config.json` (없으면 첫 실행 플로우)
- 이 명령은 **출력 디렉토리(위키)에서** 실행되는 것을 전제 — 그곳 `CLAUDE.md`(schema)가 자동 로드되어 증류 규약을 제공한다.
- **위키 쓰기 경로 = 절대 경로 고정.** 위키 파일(`index.md`·`log.md`·페이지)은 항상 `manifest.json` 의 `output_dir` 절대 경로 하위로만 쓴다. **cwd 가 출력 디렉토리라고 가정하지 말 것** — 셸 cwd 는 위키가 아닐 수 있다. 상대 경로 쓰기(예: `cat >> log.md`)는 엉뚱한 위치에 파일을 만드므로 **금지**한다.

## 절차

### 0. config 확인 / 첫 실행 스캐폴딩

1. `~/.claude/lore-wiki/config.json` 존재 확인.
2. **없으면 첫 실행**:
   - 사용자에게 **출력 디렉토리(위키 저장 위치)** 를 묻는다.
   - `${CLAUDE_PLUGIN_ROOT}/config.example.json` 을 복사해 `output_dir` 를 채운 `~/.claude/lore-wiki/config.json` 작성. (`session_root`·`include` 등은 기본값 유지, 사용자가 조정 원하면 안내)
   - 출력 디렉토리에 스캐폴딩: `${CLAUDE_PLUGIN_ROOT}/templates/schema.CLAUDE.md` → `<output_dir>/CLAUDE.md` 복사, 빈 `<output_dir>/index.md`·`<output_dir>/log.md` 생성. (이미 있으면 덮어쓰지 않음)
3. config 의 `output_dir` 가 비었거나 경로가 없으면 명확히 에러 보고 후 중단(파괴적 동작 금지).

### 1. 선별 (결정적)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/select.py --config ~/.claude/lore-wiki/config.json
```
- **stdout** = `run_dir` 한 줄(기계용). **stderr** = 사람용 선별 요약(총계 + 프로젝트별 신규 세션 수).
- **stderr 요약을 그대로 사용자에게 보여준다.** `manifest.json` 원본을 통째로 출력/덤프하지 말 것 — 유닛이 수백 개일 수 있어 검토 불가. 개별 유닛 메타는 증류 단계에서 그 유닛만 본다.
- `<run_dir>/manifest.json` 을 읽고 그 **`output_dir`(절대 경로) 를 위키 기준 경로로 고정**한다. 이후 모든 위키 쓰기는 이 절대 경로 하위(`<output_dir>/index.md`·`<output_dir>/log.md`·`<output_dir>/<page>.md`)로만 한다.
- `<run_dir>/manifest.json` 의 `units` 가 비었으면 **"위키 최신 — ingest 할 새 세션 없음"** 보고 후 종료.
- **신규 세션이 많으면**(수십~수백) 한 번에 전부 증류하는 건 큰 작업이다. 사용자에게 규모를 알리고, 좁히려면 config 의 `include`(cwd glob, 예 `["*/wafl_console"]`)로 프로젝트를 한정해 재실행하도록 안내한다.

### 2. 유닛 루프 (각 unit)

`manifest.units` 를 순서대로:

1. `<run_dir>/<unit.file>` 를 Read. (세션 헤더 + 증류용 텍스트)
2. **증류** — 출력 디렉토리 `CLAUDE.md`(schema) 규약을 따른다. **모든 위키 파일은 `<output_dir>/...` 절대 경로로 읽고 쓴다:**
   - `<output_dir>/index.md` 를 읽어 관련 기존 페이지를 찾는다.
   - 같은 사실/엔티티/결정/해법이 기존 페이지에 있으면 **그 페이지에 병합**(read-modify-write). 없으면 schema 의 페이지 타입·네이밍·frontmatter 규약대로 `<output_dir>/<page>.md` 신규 생성.
   - frontmatter 필수 필드를 채운다: `type`·`title`(본문 H1 과 일치)·`description`(한 줄 요약)·`tags`·`created`·`updated`·`timestamp`(OKF 표준, `updated` 값 미러링). provenance 는 `sessions` 에 `unit.sessions[*]` 의 `sessionId`·`lastTimestamp` 를 기록.
   - 새/갱신 페이지를 `<output_dir>/index.md` 에 반영하되, **index 항목의 한 줄 요약은 그 페이지 frontmatter 의 `description` 과 동일하게** 한다(단일 출처).
3. **`<output_dir>/log.md` append** — schema 의 log 포맷(일관 prefix)으로 한 항목: 어느 세션(들)에서 어느 페이지를 만들었/갱신했는지 + provenance. **반드시 절대 경로 `<output_dir>/log.md`** 에 쓴다 — Write/Edit 도구(절대 경로)를 쓰거나, Bash append 가 불가피하면 `>> "<output_dir>/log.md"` 처럼 절대 경로를 명시한다. 상대 `log.md` 금지.
4. **커서 커밋** (결정적):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/commit_cursor.py \
     --config ~/.claude/lore-wiki/config.json \
     --manifest <run_dir>/manifest.json --unit <unit.unit_id>
   ```
5. **진행 보고**: 유닛 처리 후 `유닛 N/총M: <unit.file> → 생성 [[A]] · 갱신 [[B]]` 식 **한 줄**로만 보고. 유닛 파일이나 페이지 본문을 덤프하지 말 것.

### 3. 정리 / 보고

- 처리한 유닛 수·생성/갱신 페이지 수·스캔/스킵 세션 수를 **간결히** 요약 보고. raw manifest·유닛 파일·페이지 본문을 덤프하지 말 것.
- (선택) `run_dir` 정리. 다음 실행이 어차피 덮어쓰므로 실패해도 무방.

## 원칙

- **결정적 경계 침범 금지**: 파일 선별·증분·커서 갱신은 헬퍼에 위임. 이 명령은 증류·병합·log 작성만.
- **위키 쓰기는 절대 경로**: `index.md`·`log.md`·페이지는 manifest 의 `output_dir` 하위 절대 경로로만 쓴다. cwd 가정·상대 경로 append(`cat >> log.md`) 금지 — 위키 밖에 파일이 새는 주된 원인.
- **병합 우선(dedup)**: 같은 지식의 중복 페이지를 만들지 않는다. 항상 `<output_dir>/index.md` → 기존 페이지 확인 후 병합.
- **schema 준수**: 페이지 타입·네이밍·링크·frontmatter 는 출력 디렉토리 `CLAUDE.md` 를 단일 출처로 삼는다.
