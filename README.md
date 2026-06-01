# Lore Wiki

Claude Code 대화 세션(JSONL)을 LLM 으로 증류해, 지속 누적·갱신되는 **마크다운 지식 위키**로
쌓는 Claude Code 플러그인. [Karpathy 의 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
모델을 차용했다.

- **Raw sources**: `~/.claude/projects/**/*.jsonl` (불변, 읽기만)
- **Wiki**: 출력 디렉토리의 entity/decision/how-to 페이지 + `index.md` + `log.md`
- **Schema**: 출력 디렉토리의 `CLAUDE.md` (규약 — 쓰면서 공동 진화)

현재 범위는 **ingest** 연산. `query`·`lint` 는 후속.

## 설치

Claude Code 플러그인으로 이 디렉토리를 등록한다(플러그인 매니페스트: `.claude-plugin/plugin.json`).
명령 `/lore-wiki` 가 추가된다.

요구사항: **Python 3.9+** (외부 의존 없음 — stdlib 만 사용).

## 설정

`config.example.json` 을 `~/.claude/lore-wiki/config.json` 으로 복사해 편집한다.
(첫 실행 시 `/lore-wiki` 가 출력 디렉토리를 물어 자동 생성도 해 준다.)

| 키 | 기본값 | 의미 |
|---|---|---|
| `session_root` | `~/.claude/projects` | 세션 JSONL 루트 |
| `output_dir` | (필수) | 위키 md 저장 위치 |
| `include` / `exclude` | `["*"]` / `[]` | 세션 `cwd` 기준 프로젝트 glob 필터 |
| `cursor_path` | `~/.claude/lore-wiki/cursor.json` | 증분 커서(출력 dir 밖 — git 노이즈 회피) |
| `obsidian` | `false` | Obsidian vault 전용 기능 사용 |
| `wikilink` | `false` | `[[..]]` wikilink vs 표준 md 링크 |
| `batch_max_bytes` | `40000` | 소형 세션 묶음 유닛 cap(추출 바이트) |

다중 위키는 `--config <경로>` 로 분리(각각 `cursor_path` 도 다르게).

## 사용

위키 디렉토리(`output_dir`)에서:

```
/lore-wiki            # = /lore-wiki ingest
/lore-wiki ingest     # 새 세션 증분 ingest
```

## 동작 개요

```
select.py (결정적): 파일 나열 → stat 비교 → byteOffset 증분 → 신호 추출 → 유닛 bin-packing
        → run_dir/{manifest.json, unit-NN.md}
명령 (LLM): 유닛별 증류 → index.md 로 기존 페이지 찾아 병합/신규 → log.md → commit_cursor.py
commit_cursor.py (결정적): 유닛 단위 cursor.json 갱신
```

증류 *규약*(페이지 타입·네이밍·dedup·세그멘테이션)은 코드가 아니라 출력 디렉토리
`CLAUDE.md`(schema)에 prose 로 정의되며, 쓰면서 공동 진화한다.

## 테스트

```bash
python3 tests/test_select.py -v
python3 tests/test_commit_cursor.py -v
```
