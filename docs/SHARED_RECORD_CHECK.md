# 공통 공개 기록 비교 운영

공식 저장소에서만 검증기를 운영하며 상세 참고 저장소에는 GET 읽기만 수행합니다.
홈페이지 내용을 수정하거나 자동으로 동기화하지 않습니다. 외부 Python 패키지는 필요하지 않습니다.

## 범위와 추출 계약

- 특허: `registry-table`의 행 순서, 표시 번호, 제목, KO/EN 법적 상태, 출원·공개·등록 식별자. 표시 번호와 `data-application-number`, `data-publication-number`, `data-registration-number`를 모두 읽습니다. 같은 필드의 표시값과 속성값이 충돌하면 추출 오류입니다. 알려지지 않은 번호를 만들지 않습니다.
- 논문: `publication-list` 안의 제목과 순서만 비교합니다.
- 센터: `profile-facts`의 CURRENT APPOINTMENT/현재 소속 제목으로 블록을 찾고, 제목 요소와 값 요소를 분리합니다. 각 언어 값의 첫 줄은 직위·기관, `<br>` 다음 두 번째 줄은 센터입니다. 센터 이름을 검색하거나 고정 문자열과 대조하지 않습니다. 값이 없거나 여러 개이거나 줄 구조가 바뀌면 안전하게 실패합니다.
- 디자인, 안내문, 과거 경력, 특허군 카드, 분야/비고, 날짜 속성, 저자·DOI·연도, 검색 정책은 비교하지 않습니다.

HTML entity, Unicode 표시형, 대시 종류, 공백·줄바꿈은 정규화합니다. 제목의 문자·문장부호·대소문자는 보존하며 영문 센터명·상태의 대소문자 차이는 표시 차이로 허용합니다. 식별자의 표시 접두사/공백/하이픈과 선택적인 KR 표기는 정규화하지만 다른 국가 코드와 종류 코드는 보존합니다. 공백을 제외한 실제 단어·번호·상태 변경은 탐지합니다.

23건/13편은 2026-10-14의 최소 fixture 회귀 기준일 뿐입니다. 비교기와 로컬 추출 검사는 실제 HTML을 읽고 건수를 고정하지 않으므로 양쪽에 같은 순서로 같은 새 기록이 추가되면 일치합니다. 기존 사이트 validator의 건수 정책은 약화하거나 변경하지 않았습니다. 향후 기록 추가 시 기존 사이트 validator의 별도 정책도 함께 검토해야 합니다.

기존 validator는 링크·자산·메타·개수 등을 검사하지만 이 공통 필드의 구조적 추출기는 제공하지 않습니다. 기존 검사를 그대로 두고, 새 단일 추출 함수를 로컬 PR 검사와 온라인 비교에서 함께 사용합니다.

## 실행과 결과 확인

Actions → **Compare shared public records** → 실행 → **Summary**와 작업 로그에서 상태, 두 저장소의 비교 SHA, 건수, 다른 필드와 양쪽 값을 확인합니다. 결과 artifact `shared-public-records-<run_id>-<attempt>` 안의 JSON에는 정규화된 기록과 오류도 들어 있으며 30일 보관됩니다. 워크플로우 실행 SHA와 비교 SHA는 별개입니다. 실행 중 각 저장소 main을 한 번씩 확정한 뒤 모든 HTML은 그 SHA에서만 읽습니다. 한쪽 SHA를 확인할 수 없으면 `UNRESOLVED`로 표시합니다.

| 판정 | 종료 코드 | 의미 |
| --- | --- | --- |
| MATCH | 0 | 두 원격 스냅샷의 비교 대상이 일치 |
| MISMATCH | 1 | 실제 필드/행/순서 불일치; 양쪽 값을 확인 |
| EXTRACTION_ERROR | 2 | 구조 또는 필드 해석 실패; 기록 불일치와 구분 |
| DEFERRED | 3 | 원격 접근 장애로 비교 보류; 일치로 취급하지 않음 |

접근 장애는 요청당 최대 3회, 각 15초 제한, 재시도 전 1초/2초 대기로 한정합니다. 403/404/429, 일시 장애, DNS/timeout을 실제 기록 불일치라고 단정하지 않습니다. 비교 보류도 Actions는 실패로 표시하여 확인이 필요함을 드러내며 Summary/JSON의 `DEFERRED`로 구분합니다. 한쪽에 추출 오류와 다른 쪽에 접근 장애가 함께 있으면 대표 상태는 EXTRACTION_ERROR이고 두 오류를 모두 보존합니다. 예기치 않은 프로그램 오류도 숨기지 않습니다. `continue-on-error`를 사용하지 않으며 결과 업로드만 `always()`로 실행합니다.

수동 실행: Actions에서 **Run workflow** → `main`, 또는:

```sh
gh workflow run compare-shared-records.yml --ref main --repo p2e-research-group/p2e-research-group.github.io
gh run list --workflow compare-shared-records.yml --repo p2e-research-group/p2e-research-group.github.io
```

PR의 기존 필수 `validate`에는 아래 오프라인 검사만 추가됩니다. 토큰·외부 접속·과거 값과의 동등성을 요구하지 않습니다.

```sh
python -B -m unittest discover -s tools/tests -v
python -B tools/compare_shared_records.py extract --root .
```

로컬 온라인 점검은 명시적으로 실행하며 결과는 저장소 밖에 둡니다:

```sh
python -B tools/compare_shared_records.py online --output ../shared-records.json --summary ../shared-records-summary.md
```

## 예약과 재활성화

- 매주 월요일 **09:17 KST** = 월요일 **00:17 UTC**, cron `17 0 * * 1`.
- 온라인 workflow는 `schedule`/`workflow_dispatch`로만 동작합니다. PR/push 트리거나 필수 온라인 검사를 추가하지 않습니다. 권한은 `contents: read`뿐입니다.
- GitHub 예약 실행은 정확한 시각을 보장하지 않습니다. 부하에 따라 늦어지거나 큐의 실행이 누락될 수 있으므로 최근 실행 시각을 확인합니다. 예약 workflow 파일은 기본 브랜치에 있어야 합니다.
- 공개 저장소에 60일간 활동이 없으면 GitHub가 예약 workflow를 자동 비활성화할 수 있습니다. Actions에서 해당 workflow의 **Enable workflow**를 선택하거나 아래 명령을 사용하고, 이어서 수동 실행 결과와 다음 예약 실행을 확인합니다. cron이나 보호 규칙을 변경할 필요는 없습니다.

```sh
gh workflow enable compare-shared-records.yml --repo p2e-research-group/p2e-research-group.github.io
```

근거: [GitHub 예약 이벤트](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [workflow 비활성화·재활성화](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows).
