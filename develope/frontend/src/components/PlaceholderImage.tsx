interface PlaceholderImageProps {
  width?: string;
  height?: string;
}

export function PlaceholderImage({ width = "100%", height = "100%" }: PlaceholderImageProps) {
  return <div className="placeholder-image" style={{ width, height }} />;
}
