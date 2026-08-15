# openORBItal
내 orbi.kr 계정의 글을 목록으로 보고, 체크박스로 골라 백업하거나 삭제하는 데스크톱 도구.
- 당신의 디지털 풋프린트를 안전하게 지우세요!
- QT 프레임워크로 시스템 테마에 맞춰 theming 이 가능!
- secure & safe !

[![](https://github.com/fr0mhe11/openORBItal/blob/main/logo.png?raw=truehttps://github.com/fr0mhe11/openORBItal/blob/main/logo.png?raw=true)](https://github.com/fr0mhe11/openORBItal/blob/main/logo.png)






## 설치

Releases 에서 appimage 으로 실행하거나 
.rpm .deb 으로 설치



로그인은 아이디/비밀번호로 사이트에 직접 POST하는 방식 한 가지뿐입니다. 소셜 로그인·캡차·
2단계 인증이 걸린 계정은 지원하지 않습니다.

아이디/비밀번호도, 세션 쿠키도 디스크에 저장하지 않습니다. 로그인 정보는 프로세스가
살아 있는 동안 메모리에만 있고 창을 닫으면 사라지므로, 실행할 때마다 다시 로그인해야
합니다.



# 빌드
프로젝트 디렉토리에서 
```bash
bash packaging/build.sh
```

`dist_pkgs/`에 세 개가 생깁니다.

| 파일 | 형식 |
|------|------|
| `openorbital-<버전>-x86_64.AppImage` | AppImage |
| `openorbital_<버전>_amd64.deb` | Debian/Ubuntu 계열 |
| `openorbital-<버전>-1.<distro태그>.x86_64.rpm` | Fedora/RHEL 계열 |

아이콘은 저장소 루트의 `logo.png`를 128/256/512px로 리사이즈해서 씁니다. 첫 실행 때
`appimagetool`을 GitHub에서 받아 `packaging/tools/`에 캐시해 두고 다음부터는 재사용합니다
(인터넷 연결 필요). `dpkg-deb`가 없는 환경(Fedora 등)을 기준으로 `.deb`는 `ar`로 직접
조립하고, `.rpm`은 시스템 `rpmbuild`로 만듭니다.

버전은 `pyproject.toml`의 `version` 값을 그대로 읽어 파일명에 씁니다. 버전을 올렸으면
`packaging/build.sh`를 다시 실행하기 전에 `pyproject.toml`부터 고치세요.
