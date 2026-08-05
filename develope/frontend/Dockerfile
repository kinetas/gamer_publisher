# 프론트엔드 기술스택 미정 상태의 placeholder 컨테이너.
# 실제 프레임워크(React 등)가 정해지면 이 Dockerfile을 빌드 스테이지가 있는
# 구성(예: node:20 빌드 -> nginx로 정적 파일 서빙)으로 교체한다.
FROM nginx:1.27-alpine

COPY public /usr/share/nginx/html

EXPOSE 80
