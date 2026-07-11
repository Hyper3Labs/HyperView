import { MetadataTileContent } from "./MetadataTileContent";

interface VideoTileContentProps {
  posterSrc: string | null;
  filename: string | null | undefined;
  id: string;
  failed: boolean;
  onError: () => void;
}

export function VideoTileContent({
  posterSrc,
  filename,
  id,
  failed,
  onError,
}: VideoTileContentProps) {
  if (!posterSrc || failed) {
    return <MetadataTileContent filename={filename} id={id} kind="video" />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={posterSrc}
      alt={filename || id}
      className="block h-full w-full object-contain"
      loading="lazy"
      onError={onError}
    />
  );
}
