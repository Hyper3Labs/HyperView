interface TextTileContentProps {
  text: string | null | undefined;
}

export function TextTileContent({ text }: TextTileContentProps) {
  return (
    <div className="flex h-full w-full bg-muted/40 px-3 pb-7 pt-3">
      <p
        className="overflow-hidden whitespace-pre-wrap break-words font-mono text-[11px] leading-4 text-foreground/80"
        style={{
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: 7,
        }}
        title={text ?? undefined}
      >
        {text || <span className="text-muted-foreground">Empty text</span>}
      </p>
    </div>
  );
}
