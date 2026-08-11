import { useState } from "react";

interface PlaceholderImageProps {
  src?: string;
  alt?: string;
  width?: string;
  height?: string;
}

export function PlaceholderImage({ src, alt = "", width = "100%", height = "100%" }: PlaceholderImageProps) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return <div className="placeholder-image" style={{ width, height }} />;
  }

  return (
    <img
      src={src}
      alt={alt}
      onError={() => setFailed(true)}
      style={{ width, height, objectFit: "cover", display: "block" }}
    />
  );
}
