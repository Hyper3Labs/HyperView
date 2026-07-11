interface ImageTileContentProps {
  src: string | null;
  alt: string;
  failed: boolean;
  onError: () => void;
}

export function ImageTileContent({ src, alt, failed, onError }: ImageTileContentProps) {
  const showImage = Boolean(src) && !failed;

  if (!showImage) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-muted">
        <span className="text-xs text-muted-foreground">No image</span>
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src ?? undefined}
      alt={alt}
      className="block h-full w-full object-contain"
      loading="lazy"
      onError={onError}
    />
  );
}
