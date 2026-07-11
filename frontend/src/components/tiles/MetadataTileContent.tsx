interface MetadataTileContentProps {
  filename: string | null | undefined;
  id: string;
  kind?: string | null;
}

export function MetadataTileContent({ filename, id, kind }: MetadataTileContentProps) {
  const identifier = filename?.trim() || id;

  return (
    <div className="flex h-full w-full flex-col justify-center gap-1 bg-muted/40 px-3 pb-7 pt-3 font-mono">
      {kind ? (
        <span className="truncate text-[9px] uppercase tracking-[0.12em] text-muted-foreground/70">
          {kind}
        </span>
      ) : null}
      <span className="truncate text-[11px] text-foreground/80" title={identifier}>
        {identifier}
      </span>
      {filename ? (
        <span className="truncate text-[9px] text-muted-foreground/70" title={id}>
          {id}
        </span>
      ) : null}
    </div>
  );
}
