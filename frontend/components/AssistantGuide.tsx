import Image from "next/image";

export function AssistantGuide({
  title,
  message,
  compact = false,
  testId,
}: {
  title: string;
  message: string;
  compact?: boolean;
  testId?: string;
}) {
  return (
    <div
      className={`assistant-guide${compact ? " is-compact" : ""}`}
      role="note"
      data-testid={testId}
    >
      <Image
        src="/pets/blue-friend-walk.gif"
        alt="QA 안내 캐릭터"
        width={58}
        height={58}
        unoptimized
        priority
      />
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
      </div>
    </div>
  );
}
