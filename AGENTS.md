# 패치와 공개 자료를 함께 유지

사용자는 게임 수정 시 이 저장소의 자동 업데이트 배포도 함께 갱신하도록 요청했습니다.

- `release/payload/client`, `release/payload/server`에는 검증된 관리 대상 파일만 반영합니다. 월드·개인 빌드·로그·계정·실행 환경 파일은 올리지 않습니다.
- 공통 수정 모드 JAR은 양쪽이 같아야 합니다. GitHub 작업이 같은 배포 ID를 넣고 새 Release를 만듭니다.
- `docs`는 공개 자료실입니다. 웹 Build Lab 계산 소스나 데이터가 바뀌면 `../CTE2_BuildLab/export_public.py --output ../CTE2_Patcher/docs/build-lab`으로 갱신하고 기능을 확인합니다. 개인 저장 파일과 `저장한 빌드` 폴더를 내보내지 않습니다.
- GitHub에 반영한 뒤 Release 및 Pages 상태와 실제 공개 주소를 확인합니다. 단순히 업로드 명령을 실행한 것으로 완료 보고하지 않습니다.
