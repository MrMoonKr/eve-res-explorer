# EVE Resource Explorer

This document serves as a reverse-engineering planning document (역기획서) based on the current implementation of the EVE Resource Explorer utility. It describes the application's architecture, features, and how the pieces fit together.

---

## 🧩 목적 (Purpose)

EVE Resource Explorer는 EVE Online 게임 클라이언트의 리소스 인덱스(`index_tranquility.txt` 및 `tq/resfileindex.txt`)와 관련된 파일을 분석, 로컬/원격에서 데이터를 읽고 헥스 뷰어로 표시하기 위한 도구입니다. 주요 목표는 논리 경로 계층을 트리 뷰로 탐색하고, 파일의 실제 데이터를 확인하며, 없으면 원격 서버에서 다운로드하여 캐싱하는 것입니다.

## 📁 주요 구성 요소 (Components)

| 클래스/모듈 | 역할 요약 |
|-------------|-----------|
| `ResourceEntry` | 인덱스 항목에 대한 데이터 구조 (logical/physical path, hash, offset, size) |
| `LoadedIndexes` | 인덱스에서 로드된 경로 목록과 맵을 보관 |
| `IndexLoader` | EVE 루트 유효성 검사, 인덱스 파싱, 경로 정규화 및 물리적 위치 계산 |
| `EVEApp` | 애플리케이션의 GUI 및 동작 제어기, 이벤트 처리, 파일 로드 및 뷰어 업데이트 |
| `Toolbar`, `StatusBar`, `TreePanel`, `HexViewer` | Tkinter 기반 UI 위젯.  

## 🖥 UI 흐름

1. **Root 디렉터리 선택**: 사용자가 툴바에서 디렉터리를 선택하거나 텍스트 입력 후 `Enter` -> `IndexLoader.validate_root()` 호출
2. **인덱스 로드**: `IndexLoader.load()`가 두 인덱스 파일을 파싱하고 `LoadedIndexes` 생성
3. **트리 구성**: `TreePanel.populate()`는 `tq` 및 `res` 경로를 간결/정렬하여 트리를 빌드
4. **항목 선택**: 트리 선택 시 `EVEApp._on_tree_selected()`가 호출되고
   - `resource_map`에서 `ResourceEntry` 조회
   - 로컬, 캐시, 원격 순으로 데이터 검색 (`_load_resource_bytes`)
   - 10MB 이상 파일 경고 및 `HexViewer.render()` 호출
   - 상태 표시줄 업데이트

## 🧠 핵심 기능

- **경로 정규화**: `IndexLoader.logical_to_parts()` 및 `_normalize_logical()`로 경로를 파싱하고 트리 계층 구축
- **물리 경로 해결**: `resolve_physical_relative()`와 `resolve_physical_path()`로 로컬/원격 파일 위치 도출
- **인덱스 파싱**: `_parse_index_file`/`_parse_line`에서 CSV 형식 변종을 처리하고 유효 데이터 추출
- **원격 다운로드 및 캐시**:
   - `REMOTE_BASE_URL` 사용
   - `urlopen` 사용자-에이전트 프로필 변경
   - `cache` 폴더에 저장
   - 네트워크 오류 및 HTTP 오류 처리
- **대형 파일 감지**: 10MB 임계값에 따른 사용자 경고
- **헥스 뷰어 하이라이트**: 선택된 리소스의 오프셋/크기를 강조 표시

## 🛠 예외 및 오류 처리

- 유효하지 않은 루트 또는 읽기 실패 시 `messagebox.showerror`
- 다운로드 실패(HTTP/URLError) 시 사용자에게 알림
- 캐시 쓰기 불가 시 경고
- 진행 상태는 상태 표시줄을 통해 실시간 업데이트

## 🧷 확장 가능성 및 제약

- 현재 트리 뷰는 인덱스에 포함된 모든 경로를 메모리에 올림; 매우 큰 인덱스에서 성능 고려 필요
- 다운로드 프로필은 두 가지만 정의, 더 세분화 가능
- 오프셋/크기 정보가 없는 경우 헥스 하이라이트는 비활성
- 원격 URL 베이스는 하드코딩; 설정 가능성 없음

## 🚀 향후 개선 제안

1. **검색 기능**: 트리 또는 전체 경로 텍스트 검색
2. **디코더 플러그인**: 특정 파일 형식(예: 그래픽, XML 등)을 자동 디코딩
3. **멀티 스레딩**: 큰 트리를 빌드하거나 다운로드 시 UI 차단 최소화
4. **설정 저장**: 마지막 사용한 경로, 사용자 지정 URL 등
5. **로그 기록**: 진단을 위한 파일 및 다운로드 기록

## 📦 파일/디렉터리 구조

```
/ (workspace root)
├─ eve_explorer.py       # 애플리케이션 진입점 및 구현 전체
├─ cache/                # 원격에서 받아온 파일 저장소
└─ CODEX.md              # 역기획서 (이 문서)
```

---

이 문서는 지금까지 작성된 소스 코드를 기반으로 작성된 역기획서입니다. 추가 기능이나 구조 변경이 발생하면 업데이트가 필요합니다.