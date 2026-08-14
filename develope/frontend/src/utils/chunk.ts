export function chunk<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size));
  }
  return chunks;
}

/** items를 최대 maxSize개씩 담되, 필요한 페이지 수(ceil(n/maxSize))에 최대한
 * 고르게 나눠 담는다. 예: 5개를 4개씩 담으면 chunk()는 [4,1]이 되어 마지막
 * 페이지가 거의 빈 것처럼 보이는데, 이 함수는 [3,2]로 나눠서 페이지마다
 * 알차게 채워지게 한다. */
export function chunkBalanced<T>(items: T[], maxSize: number): T[][] {
  if (items.length === 0) return [];
  const pageCount = Math.ceil(items.length / maxSize);
  const baseSize = Math.floor(items.length / pageCount);
  const remainder = items.length % pageCount;

  const chunks: T[][] = [];
  let offset = 0;
  for (let i = 0; i < pageCount; i++) {
    const size = baseSize + (i < remainder ? 1 : 0);
    chunks.push(items.slice(offset, offset + size));
    offset += size;
  }
  return chunks;
}
